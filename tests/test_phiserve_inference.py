"""PhiServe transport tests. HTTP is simulated; no real weights are executed."""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from api.core.inference import (
    InferenceError, InferenceRuntime, PHISERVE_DEFAULT_URL,
    _strict_loopback, build_chat_messages, complete_chat, initial_model_name,
    list_model_aliases, preferred_chat_model, request_headers, runtime_from_env,
    stream_chat,
)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.token_path = Path(self.tmp.name) / "local-token.txt"
        self.token = "example-local-only-phi369-token-value-1234567890"
        self.token_path.write_text(self.token + "\n", encoding="utf-8")
        os.chmod(self.token_path, 0o600)

    def env(self, **overrides):
        defaults = {
            "BRAINC_INFERENCE_BACKEND": "phiserve",
            "PHISERVE_BASE_URL": PHISERVE_DEFAULT_URL,
            "PHISERVE_TOKEN_FILE": str(self.token_path),
            "PHISERVE_MODEL": "registered-qwen",
        }
        return patch.dict(os.environ, {**defaults, **overrides})

    def test_ollama_default_preserved_and_no_phi_secret_needed(self):
        with patch.dict(os.environ, {
            "BRAINC_INFERENCE_BACKEND": "ollama",
            "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        }):
            runtime = runtime_from_env()
            self.assertEqual(runtime.backend, "ollama")
            self.assertEqual(runtime.url, "http://127.0.0.1:11434")
            self.assertNotIn("Authorization", request_headers(runtime))
            self.assertEqual(initial_model_name(), os.environ.get("ACTIVE_MODEL", "braincbrain"))

    def test_opt_in_phi_runtime_binds_to_explicit_loopback(self):
        with self.env():
            runtime = runtime_from_env()
            self.assertTrue(runtime.is_phiserve)
            self.assertEqual(runtime.url, PHISERVE_DEFAULT_URL)
            self.assertEqual(initial_model_name(), "registered-qwen")
            self.assertEqual(request_headers(runtime)["Authorization"], "Bearer " + self.token)
            self.assertEqual(request_headers(runtime, json_body=True)["Content-Type"], "application/json")

    def test_remote_https_credentials_query_and_paths_rejected(self):
        for bad in (
            "https://127.0.0.1:11435",
            "http://192.168.1.15:11435",
            "http://example.com:11435",
            "http://127.0.0.1.evil.test:11435",
            "http://user:pass@localhost:11435",
            "http://localhost:11435/api/chat",
            "http://localhost:11435/?token=secret",
            "http://localhost:11435/#frag",
            "http://localhost",
            "http://[::2]:11435",
            "file:///etc/passwd",
            "garbage",
        ):
            with self.subTest(bad=bad), self.assertRaises(InferenceError):
                _strict_loopback(bad)
        self.assertEqual(_strict_loopback("http://[::1]:11435"), "http://[::1]:11435")

    def test_no_unrequested_backend_fallback(self):
        with self.env(BRAINC_INFERENCE_BACKEND="phi-stream"):
            with self.assertRaisesRegex(InferenceError, "must be ollama or phiserve"):
                runtime_from_env()
        with self.env(PHISERVE_MODEL=""):
            with self.assertRaisesRegex(InferenceError, "registered local GGUF"):
                initial_model_name()

    def test_missing_or_insecure_token_never_exposed(self):
        with self.env(PHISERVE_TOKEN_FILE=str(self.token_path) + ".missing"):
            with self.assertRaises(InferenceError) as failure:
                request_headers(runtime_from_env())
            self.assertNotIn(str(self.token_path), str(failure.exception))
            self.assertNotIn(self.token, str(failure.exception))
        with self.env():
            os.chmod(self.token_path, 0o644)
            if os.name == "posix":
                with self.assertRaisesRegex(InferenceError, "insecure"):
                    request_headers(runtime_from_env())
            os.chmod(self.token_path, 0o600)

    def test_phi_persona_and_optional_user_override_are_explicit_system_messages(self):
        with self.env():
            runtime = runtime_from_env()
            original = [{"role": "user", "content": "Hello"}]
            value = build_chat_messages(
                runtime, original, with_identity=True,
                user_override="Answer concisely.",
            )
            self.assertEqual(value[0]["role"], "system")
            self.assertIn("You are BrainC", value[0]["content"])
            self.assertEqual(value[1]["content"], "Answer concisely.")
            self.assertEqual(value[-1], original[0])
            self.assertEqual(original, [{"role": "user", "content": "Hello"}])
            self.assertNotIn("Bearer", value[0]["content"])

    def test_user_preference_falls_back_to_correct_phi_alias_not_modelfile_alias(self):
        with self.env():
            self.assertEqual(preferred_chat_model("braincbrain", "registered-qwen"), "registered-qwen")
            self.assertEqual(preferred_chat_model(None, "registered-qwen"), "registered-qwen")
            self.assertEqual(preferred_chat_model("my-explicit-local-alias", "registered-qwen"),
                             "my-explicit-local-alias")

    def test_tool_messages_rejected_as_inference_authority(self):
        with self.env():
            with self.assertRaisesRegex(InferenceError, "text system/user/assistant"):
                build_chat_messages(runtime_from_env(), [{"role": "tool", "content": "execute now"}])


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "local-secret.txt"
        self.path.write_text("phi-token-test-abcdefghijklmnopqrstuvwxyz-1234567\n")
        os.chmod(self.path, 0o600)
        self.runtime = InferenceRuntime("phiserve", PHISERVE_DEFAULT_URL, self.path)

    async def connect(self, handler):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
        self.addAsyncCleanup(client.aclose)
        return client

    async def test_model_list_uses_only_authenticated_phi_endpoint(self):
        def handler(request):
            self.assertEqual(str(request.url), PHISERVE_DEFAULT_URL + "/api/tags")
            self.assertEqual(request.headers["authorization"], "Bearer phi-token-test-abcdefghijklmnopqrstuvwxyz-1234567")
            return httpx.Response(200, json={"models": [{"name": "registered-qwen"}]})
        result = await list_model_aliases(self.runtime, client=await self.connect(handler))
        self.assertEqual(result, ["registered-qwen"])

    async def test_nonstreaming_summary_uses_selected_backend_not_ollama(self):
        def handler(request):
            self.assertEqual(str(request.url), PHISERVE_DEFAULT_URL + "/api/chat")
            body = __import__("json").loads(request.content)
            self.assertEqual(body["model"], "registered-qwen")
            self.assertFalse(body["stream"])
            self.assertNotIn("think", body)
            self.assertEqual(body["messages"], [{"role": "system", "content": "Summarize a local note."}])
            return httpx.Response(200, json={
                "done": True, "message": {"role": "assistant", "content": "Summary complete."},
            })
        answer = await complete_chat("registered-qwen",
                                     [{"role": "system", "content": "Summarize a local note."}],
                                     self.runtime, client=await self.connect(handler))
        self.assertEqual(answer, "Summary complete.")

    async def test_realistic_ndjson_stream_only_yields_completed_assistant_text(self):
        def handler(request):
            import json
            body = json.loads(request.content)
            self.assertEqual(body["model"], "registered-qwen")
            self.assertTrue(body["stream"])
            self.assertNotIn("think", body)
            return httpx.Response(200, content=(
                b'{"done":false,"message":{"role":"assistant","content":"Hello "}}\n'
                b'{"done":false,"message":{"role":"assistant","content":"world"}}\n'
                b'{"done":true,"message":{"role":"assistant","content":""}}\n'
            ))
        content = []
        async for text in stream_chat(
            "registered-qwen", [{"role": "user", "content": "hello"}],
            self.runtime, client=await self.connect(handler),
        ):
            content.append(text)
        self.assertEqual("".join(content), "Hello world")

    async def test_missing_done_does_not_forge_completed_answer(self):
        def handler(_):
            return httpx.Response(200, content=
                b'{"done":false,"message":{"role":"assistant","content":"partial"}}\n')
        with self.assertRaisesRegex(InferenceError, "without completion"):
            async for _ in stream_chat("registered-qwen",
                [{"role": "user", "content": "hello"}],
                self.runtime, client=await self.connect(handler)):
                pass

    async def test_malformed_nonassistant_and_empty_stream_rejected(self):
        for payload in (
            b'not-json\n',
            b'{"done":true,"message":{"role":"tool","content":"run code"}}\n',
            b'{"done":true,"message":{"role":"assistant","content":""}}\n',
        ):
            with self.subTest(payload=payload):
                def handler(_):
                    return httpx.Response(200, content=payload)
                with self.assertRaises(InferenceError):
                    async for _ in stream_chat("registered-qwen",
                        [{"role": "user", "content": "hello"}],
                        self.runtime, client=await self.connect(handler)):
                        pass

    async def test_unauthorized_or_busy_never_falls_back_or_reveals_bearer_secret(self):
        for status in (401, 409, 503):
            calls = []
            def handler(request):
                calls.append(str(request.url))
                return httpx.Response(status, text="secret-the-model-refused")
            with self.subTest(status=status):
                with self.assertRaises(InferenceError) as err:
                    await complete_chat("registered-qwen",
                        [{"role": "user", "content": "hello"}],
                        self.runtime, client=await self.connect(handler))
                self.assertEqual(calls, [PHISERVE_DEFAULT_URL + "/api/chat"])
                self.assertNotIn("secret-the-model-refused", str(err.exception))
                self.assertNotIn("phi-token-test", str(err.exception))
                calls.clear()

    async def test_no_hidden_redirect_fallback(self):
        def handler(_):
            return httpx.Response(302, headers={"location": "https://api.example.com"})
        with self.assertRaises(InferenceError):
            await list_model_aliases(self.runtime, client=await self.connect(handler))


if __name__ == "__main__":
    unittest.main()
