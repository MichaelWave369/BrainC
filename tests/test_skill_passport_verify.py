"""R9 BrainC compatibility tests: synthetic fixtures are fabricated solely for testing."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "skill_passport_verify.py"
SPEC = importlib.util.spec_from_file_location("skill_passport_verify", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def fixture():
    model = "unit-test:synthetic"
    mode = "guided"
    episodes = []
    for scenario_id, targets, readings, expected in verifier.CASES:
        steps = []
        for idx, target in enumerate(targets, 1):
            raw = verifier.encoded({"tool": "inspect", "target": target})
            steps.append({
                "turn": idx, "raw": raw, "parsed": verifier.parse_action(raw),
                "accepted": True, "reply": verifier.encoded({
                    "kind": "SYNTHETIC_INSPECTION", "target": target,
                    "data": readings[target], "effect": "read_only"
                }), "latencyMs": 30 + idx,
            })
        raw = verifier.encoded({"tool": "decide", "decision": expected})
        steps.append({
            "turn": 3, "raw": raw, "parsed": verifier.parse_action(raw),
            "accepted": True, "reply": verifier.encoded({
                "kind": "SIMULATED_DECISION", "value": expected,
                "result": "Recorded for grading only. No external operation occurred."
            }), "latencyMs": 33,
        })
        ep = {
            "id": "fixture-" + scenario_id, "at": "2026-10-21T20:00:00Z",
            "protocol": verifier.R6, "provenance": "OBSERVED",
            "scenarioId": scenario_id, "model": model, "mode": mode,
            "steps": steps, "outcome": "PASS", "decision": expected,
        }
        assert verifier.replay(ep, (scenario_id, targets, readings, expected))
        episodes.append(ep)
    certificate = {
        "id": "r7-test", "issuedAt": "2026-10-21T21:00:00Z",
        "protocol": verifier.CERT_PROTOCOL, "scope": verifier.CERT_SCOPE,
        "provenance": "LOCAL_UNTRUSTED", "model": model, "mode": mode,
        "scenarioIds": [case[0] for case in verifier.CASES],
        "evidenceIds": [ep["id"] for ep in episodes],
        "evidenceSha256": verifier.digest({
            "protocol": verifier.CERT_PROTOCOL, "scope": verifier.CERT_SCOPE,
            "model": model, "mode": mode, "episodes": episodes
        }),
        "summary": "TEST-ONLY simulated evidence. No operational authority.",
        "support": {},
    }
    body = {
        "format": verifier.FORMAT, "exportedAt": "2026-10-21T22:00:00Z",
        "issuerClaim": {"app": "PhiLearn", "selfReported": True},
        "subject": {"model": model, "mode": mode}, "scope": verifier.CERT_SCOPE,
        "boundary": {"authority": "NONE", "requestedPermissions": [], "usage": "INSPECT_ONLY"},
        "certificate": certificate, "episodes": episodes,
    }
    return dict(body, payloadSha256=verifier.digest(body))


def reseal(passport):
    cert = passport["certificate"]
    cert["evidenceSha256"] = verifier.digest({
        "protocol": verifier.CERT_PROTOCOL, "scope": verifier.CERT_SCOPE,
        "model": cert["model"], "mode": cert["mode"], "episodes": passport["episodes"],
    })
    passport["payloadSha256"] = verifier.digest({
        name: passport[name] for name in (
            "format", "exportedAt", "issuerClaim", "subject", "scope",
            "boundary", "certificate", "episodes"
        )
    })


class TestPortablePassport(unittest.TestCase):
    def test_synthetic_six_case_replay_and_checksums(self):
        passport = fixture()
        result = verifier.verify_bytes(verifier.encoded(passport).encode("utf-8"))
        self.assertEqual(result["status"], "REPLAY_PASS_UNTRUSTED")
        self.assertTrue(result["replayConsistent"])
        self.assertEqual(result["authority"], "NONE")
        self.assertEqual(result["permissions"], [])

    def test_reseal_cannot_hide_forged_trace(self):
        passport = fixture()
        passport["episodes"][0]["steps"][0]["raw"] = (
            '{"tool":"decide","decision":"REPAIR_DNS"}'
        )
        reseal(passport)
        self.assertFalse(verifier.verify_object(passport)["replayConsistent"])
        passport = fixture()
        passport["episodes"][0]["outcome"] = "INCOMPLETE"
        reseal(passport)
        self.assertFalse(verifier.verify_object(passport)["replayConsistent"])

    def test_permission_scope_and_identity_are_immutable(self):
        passport = fixture()
        passport["boundary"] = {
            "authority": "ADMIN", "requestedPermissions": ["shell"], "usage": "EXECUTE"
        }
        reseal(passport)
        self.assertFalse(verifier.verify_object(passport)["replayConsistent"])
        passport = fixture()
        passport["subject"]["model"] = "attacker"
        reseal(passport)
        self.assertFalse(verifier.verify_object(passport)["replayConsistent"])

    def test_bad_input_and_unlisted_commands_are_rejected(self):
        self.assertFalse(verifier.verify_bytes(b"invalid JSON")["replayConsistent"])
        self.assertFalse(
            verifier.verify_bytes(b"x" * (verifier.MAX_BYTES + 1))["replayConsistent"]
        )
        self.assertIsNone(verifier.parse_action('{"tool":"shell","command":"echo hello"}'))
        self.assertIsNone(
            verifier.parse_action('{"tool":"inspect","target":"dns_record","exec":"true"}')
        )

    def test_test_fixture_is_not_real_model_evidence(self):
        passport = fixture()
        self.assertIn("TEST-ONLY", passport["certificate"]["summary"])
        self.assertEqual(passport["issuerClaim"]["selfReported"], True)
        self.assertEqual(verifier.verify_object(passport)["authority"], "NONE")


if __name__ == "__main__":
    unittest.main()
