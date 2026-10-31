"""Explicit local inference transport for BrainC (Ollama default, PhiServe opt-in).

The client never grants tool rights, writes app memory, downloads weights, or
switches providers after an error. PhiServe must already be running on the
same computer with its token-authenticated browser bridge enabled.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlsplit

import httpx

from api import config  # Loads optional root .env; does not connect to a model.

PHISERVE_DEFAULT_URL = "http://127.0.0.1:11435"
IDENTITY_PATH = Path(__file__).resolve().parents[2] / "model" / "system_prompt.md"
SUPPORTED_ROLES = frozenset({"system", "user", "assistant"})
MAX_REPLY_CHARS = 100_000


class InferenceError(Exception):
    """Local model transport failed. Never contains credentials or raw model text."""


@dataclass(frozen=True)
class InferenceRuntime:
    backend: str
    url: str
    token_file: Path | None = None

    @property
    def provider(self) -> str:
        return "PhiServe" if self.backend == "phiserve" else "Ollama"

    @property
    def is_phiserve(self) -> bool:
        return self.backend == "phiserve"


def _strict_loopback(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise InferenceError("PhiServe requires a valid local loopback URL.") from exc
    if (
        parsed.scheme != "http" or host not in {"localhost", "127.0.0.1", "::1"}
        or port is None or port < 1 or parsed.username or parsed.password
        or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
        or parsed.netloc.endswith(":")
    ):
        raise InferenceError(
            "PhiServe URL must be an HTTP loopback host with an explicit port, no credentials or path."
        )
    # Preserve canonical IPv6 brackets and the selected port.
    return f"http://[{host}]:{port}" if host == "::1" else f"http://{host}:{port}"


def runtime_from_env() -> InferenceRuntime:
    backend = os.environ.get("BRAINC_INFERENCE_BACKEND", "ollama").strip().lower()
    if backend == "ollama":
        return InferenceRuntime(
            backend="ollama",
            url=os.getenv("OLLAMA_BASE_URL", config.OLLAMA_BASE_URL).rstrip("/"),
        )
    if backend != "phiserve":
        raise InferenceError("BRAINC_INFERENCE_BACKEND must be ollama or phiserve.")
    url = _strict_loopback(os.getenv("PHISERVE_BASE_URL", PHISERVE_DEFAULT_URL).strip())
    path = os.environ.get("PHISERVE_TOKEN_FILE", "").strip()
    if not path:
        raise InferenceError("PHISERVE_TOKEN_FILE is required for the explicit PhiServe backend.")
    return InferenceRuntime(backend="phiserve", url=url, token_file=Path(path).expanduser())


def _token(path: Path | None) -> str:
    if path is None:
        raise InferenceError("PhiServe bearer-token file is not configured.")
    try:
        if path.is_symlink():
            raise ValueError("symlink")
        info = path.stat()
        if not path.is_file() or info.st_size < 32 or info.st_size > 512:
            raise ValueError("size")
        if os.name == "posix" and info.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise ValueError("permissions")
        token = path.read_text(encoding="utf-8").strip()
        if not (32 <= len(token) <= 511) or any(c.isspace() for c in token):
            raise ValueError("format")
        return token
    except (OSError, UnicodeError, ValueError) as exc:
        # Never include path, token contents, exception repr, or system output.
        raise InferenceError("Private PhiServe token file is missing, insecure, or invalid.") from exc


def request_headers(runtime: InferenceRuntime, *, json_body: bool = False) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if json_body:
        headers["Content-Type"] = "application/json"
    if runtime.is_phiserve:
        headers["Authorization"] = f"Bearer {_token(runtime.token_file)}"
    return headers


def _client(timeout: float) -> httpx.AsyncClient:
    # Ignore HTTP[S]_PROXY and do not follow redirects for local credentials.
    return httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False)


def _status_error(runtime: InferenceRuntime, status: int) -> InferenceError:
    return InferenceError(f"{runtime.provider} local inference unavailable (HTTP {status}).")


def _check_status(runtime: InferenceRuntime, response: httpx.Response) -> None:
    if response.status_code != 200:
        raise _status_error(runtime, response.status_code)


def build_chat_messages(
    runtime: InferenceRuntime, messages: list[dict],
    *, with_identity: bool = False, user_override: str | None = None,
) -> list[dict]:
    if not isinstance(messages, list) or not messages:
        raise InferenceError("Chat requires at least one message.")
    clean = []
    for item in messages:
        if not isinstance(item, dict) or item.get("role") not in SUPPORTED_ROLES or not isinstance(item.get("content"), str):
            raise InferenceError("Only text system/user/assistant messages are supported.")
        clean.append({"role": item["role"], "content": item["content"]})
    if runtime.is_phiserve and with_identity:
        try:
            identity = IDENTITY_PATH.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise InferenceError("BrainC identity prompt is unavailable locally.") from exc
        if not identity:
            raise InferenceError("BrainC identity prompt is empty.")
        prefix = [{"role": "system", "content": identity}]
        if isinstance(user_override, str) and user_override.strip():
            prefix.append({"role": "system", "content": user_override.strip()})
        return prefix + clean
    return clean


def _payload(runtime: InferenceRuntime, model: str, messages: list[dict], streaming: bool) -> dict:
    if not isinstance(model, str) or not model.strip():
        raise InferenceError("An explicit local model alias is required.")
    payload = {"model": model, "messages": messages, "stream": streaming}
    # PhiServe rejects unsupported Ollama knobs. Do not send think/tool/images.
    return payload


async def list_model_aliases(
    runtime: InferenceRuntime | None = None,
    *, client: httpx.AsyncClient | None = None,
) -> list[str]:
    runtime = runtime or runtime_from_env()
    async def fetch(active: httpx.AsyncClient) -> list[str]:
        try:
            response = await active.get(runtime.url + "/api/tags", headers=request_headers(runtime))
            _check_status(runtime, response)
            body = response.json()
            models = body.get("models")
            if not isinstance(models, list):
                raise ValueError("models")
            aliases = [m.get("name") for m in models]
            if not all(isinstance(alias, str) and alias for alias in aliases):
                raise ValueError("model alias")
            return aliases
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise InferenceError(f"{runtime.provider} model catalog unavailable or malformed.") from exc
    if client is not None:
        return await fetch(client)
    async with _client(10.0) as connected:
        return await fetch(connected)


async def complete_chat(
    model: str, messages: list[dict], runtime: InferenceRuntime | None = None,
    *, client: httpx.AsyncClient | None = None,
) -> str:
    runtime = runtime or runtime_from_env()
    payload = _payload(runtime, model, build_chat_messages(runtime, messages), False)
    async def fetch(active: httpx.AsyncClient) -> str:
        try:
            response = await active.post(
                runtime.url + "/api/chat", headers=request_headers(runtime, json_body=True),
                json=payload,
            )
            _check_status(runtime, response)
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("message"), dict):
                raise ValueError("response")
            answer = body["message"].get("content")
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("missing final text")
            if runtime.is_phiserve and body.get("done") is not True:
                raise ValueError("incomplete PhiServe response")
            return answer.strip()
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise InferenceError(f"{runtime.provider} returned no valid completed assistant text.") from exc
    if client is not None:
        return await fetch(client)
    async with _client(120.0) as connected:
        return await fetch(connected)


async def _stream(
    client: httpx.AsyncClient, runtime: InferenceRuntime, payload: dict,
) -> AsyncIterator[str]:
    total = 0
    completed = False
    try:
        async with client.stream(
            "POST", runtime.url + "/api/chat",
            headers=request_headers(runtime, json_body=True), json=payload,
        ) as response:
            _check_status(runtime, response)
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    frame = json.loads(line)
                except (ValueError, UnicodeError) as exc:
                    raise InferenceError("Model stream returned malformed JSON.") from exc
                if not isinstance(frame, dict) or frame.get("error"):
                    raise InferenceError("Local model stream reported an error.")
                message = frame.get("message") or {}
                if not isinstance(message, dict):
                    raise InferenceError("Non-text model stream frame.")
                text = message.get("content", "")
                if not isinstance(text, str) or message.get("role", "assistant") != "assistant":
                    raise InferenceError("Non-assistant model stream frame.")
                total += len(text)
                if total > MAX_REPLY_CHARS:
                    raise InferenceError("Model stream exceeded bounded response size.")
                if text:
                    yield text
                if frame.get("done") is True:
                    completed = True
                    break
            if not completed:
                raise InferenceError("Local model stream ended without completion.")
            if total == 0:
                raise InferenceError("Local model produced no final answer.")
    except httpx.HTTPError as exc:
        raise InferenceError(f"{runtime.provider} streaming transport failed.") from exc


async def stream_chat(
    model: str, messages: list[dict], runtime: InferenceRuntime | None = None,
    *, client: httpx.AsyncClient | None = None,
) -> AsyncIterator[str]:
    runtime = runtime or runtime_from_env()
    payload = _payload(runtime, model, build_chat_messages(runtime, messages), True)
    if client is not None:
        async for part in _stream(client, runtime, payload):
            yield part
    else:
        async with _client(180.0) as connected:
            async for part in _stream(connected, runtime, payload):
                yield part


def preferred_chat_model(user_preference: str | None, active: str) -> str:
    runtime = runtime_from_env()
    if runtime.is_phiserve:
        # The existing BrainC preference defaults to Ollama's name `braincbrain`;
        # never silently use that as a PhiServe alias.
        if not user_preference or user_preference == "braincbrain":
            return active
    return user_preference or active


def initial_model_name() -> str:
    runtime = runtime_from_env()
    if runtime.is_phiserve:
        selected = os.environ.get("PHISERVE_MODEL", "").strip()
        if not selected:
            raise InferenceError("PHISERVE_MODEL must be a registered local GGUF alias.")
        return selected
    return os.environ.get("ACTIVE_MODEL", "braincbrain")
