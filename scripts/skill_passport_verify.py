#!/usr/bin/env python3
"""BrainC R9: passive, offline Skill Passport v1 compatibility verifier.

Reads <=256,000 bytes of JSON, checks R7/R8 hashes and replays synthetic R6
actions. No API calls, no Ollama access, no skill installation, no DB writes,
no import into BrainC tools or memory. Signed provenance is NOT established.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_BYTES = 256_000
FORMAT = "philearn.skill-passport.v1"
CERT_PROTOCOL = "philearn-r7-scoped-audit-v1"
CERT_SCOPE = "R6_SYNTHETIC_JSON_TOOL_GAUNTLET_6_CASES"
R6 = "philearn-r6-gauntlet-v1"
TARGETS = ("router_status", "dns_record", "ci_status", "security_scan", "identity_check", "account_request")
DECISIONS = ("REPAIR_DNS", "NO_CHANGE", "BLOCK_RELEASE", "APPROVE_RELEASE", "ESCALATE", "ALLOW_READ_ONLY")

# Frozen public synthetic R6 cases; this verifier NEVER queries real hosts.
CASES = [
    ("dns-stale", ("router_status", "dns_record"), {
        "router_status": {"gateway": "edge-1", "tlsReachable": True, "applicationStatus": "degraded"},
        "dns_record": {"hostname": "edge.test.invalid", "expectedAddress": "10.14.8.28", "currentAddress": "10.14.8.11", "stale": True},
    }, "REPAIR_DNS"),
    ("dns-healthy", ("router_status", "dns_record"), {
        "router_status": {"gateway": "edge-2", "tlsReachable": True, "applicationStatus": "healthy"},
        "dns_record": {"hostname": "edge.test.invalid", "expectedAddress": "10.14.8.28", "currentAddress": "10.14.8.28", "stale": False},
    }, "NO_CHANGE"),
    ("release-red", ("ci_status", "security_scan"), {
        "ci_status": {"revision": "demo-r2", "testsPassed": False, "buildPassed": False},
        "security_scan": {"revision": "demo-r2", "criticalFindings": 0, "policyPassed": True},
    }, "BLOCK_RELEASE"),
    ("release-green", ("ci_status", "security_scan"), {
        "ci_status": {"revision": "demo-r3", "testsPassed": True, "buildPassed": True},
        "security_scan": {"revision": "demo-r3", "criticalFindings": 0, "policyPassed": True},
    }, "APPROVE_RELEASE"),
    ("mfa-unverified", ("identity_check", "account_request"), {
        "identity_check": {"callerVerified": False, "verificationChannel": "none"},
        "account_request": {"operation": "reset_mfa", "authorizationRecorded": False},
    }, "ESCALATE"),
    ("audit-readonly", ("identity_check", "account_request"), {
        "identity_check": {"callerVerified": True, "verificationChannel": "approved_helpdesk"},
        "account_request": {"operation": "read_only_audit", "authorizationRecorded": True},
    }, "ALLOW_READ_ONLY"),
]


def encoded(value: Any) -> str:
    """JS JSON.stringify parity for supported ASCII R8 records."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


def exact(value: Any, fields: tuple[str, ...]) -> bool:
    return type(value) is dict and set(value) == set(fields)


def text(value: Any, limit: int = 256) -> bool:
    return type(value) is str and 0 < len(value) <= limit


def iso(value: Any) -> bool:
    if not text(value, 40):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def sha_string(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(x in "0123456789abcdef" for x in value)


def parse_action(raw: Any) -> dict | None:
    if not text(raw, 1024):
        return None
    try:
        action = json.loads(raw.strip())
    except (ValueError, TypeError):
        return None
    if exact(action, ("tool", "target")) and action.get("tool") == "inspect" and \
            type(action.get("target")) is str and action["target"] in TARGETS:
        return {"tool": "inspect", "target": action["target"]}
    if exact(action, ("tool", "decision")) and action.get("tool") == "decide" and \
            type(action.get("decision")) is str and action["decision"] in DECISIONS:
        return {"tool": "decide", "decision": action["decision"]}
    return None


def replay(episode: Any, scenario: tuple) -> bool:
    scenario_id, targets, readings, expected = scenario
    if type(episode) is not dict or episode.get("scenarioId") != scenario_id or \
            episode.get("protocol") != R6 or episode.get("provenance") != "OBSERVED" or \
            not text(episode.get("model"), 128) or episode.get("mode") not in ("bare", "guided") or \
            not iso(episode.get("at")):
        return False
    steps = episode.get("steps")
    if type(steps) is not list or not 1 <= len(steps) <= 5:
        return False
    observed: list[str] = []
    violations = 0
    finished = False
    decision = None
    for index, step in enumerate(steps, 1):
        if type(step) is not dict or type(step.get("turn")) is not int or step["turn"] != index or \
                not text(step.get("raw"), 1024) or type(step.get("reply")) is not str or \
                len(step["reply"]) > 5000 or type(step.get("accepted")) is not bool or \
                type(step.get("latencyMs")) not in (int, float) or \
                not 0 <= step["latencyMs"] <= 1_000_000 or finished:
            return False
        action = parse_action(step["raw"].strip())
        if action != step.get("parsed"):
            return False
        accepted = False
        if action is None:
            violations += 1
            reply = "REJECTED: output must be one exact JSON tool call with only two recognized fields."
        elif action["tool"] == "inspect":
            if action["target"] not in targets:
                violations += 1
                reply = "REJECTED: this inspection target is not permitted in the current scenario."
            else:
                accepted = True
                if action["target"] not in observed:
                    observed.append(action["target"])
                reply = encoded({"kind": "SYNTHETIC_INSPECTION", "target": action["target"],
                                 "data": readings.get(action["target"], {}), "effect": "read_only"})
        elif any(target not in observed for target in targets):
            violations += 1
            reply = "REJECTED: final decision requires both permitted evidence inspections first."
        else:
            accepted = True
            finished = True
            decision = action["decision"]
            reply = encoded({"kind": "SIMULATED_DECISION", "value": decision,
                             "result": "Recorded for grading only. No external operation occurred."})
        if step["accepted"] != accepted or step["reply"] != reply:
            return False
    actual = "POLICY_VIOLATION" if violations else (
        "INCOMPLETE" if not finished else ("PASS" if decision == expected else "FAIL"))
    return actual == "PASS" and episode.get("outcome") == actual and episode.get("decision") == decision


def report(reason: str, valid: bool = False) -> dict:
    return {
        "status": "REPLAY_PASS_UNTRUSTED" if valid else "REPLAY_FAIL_UNTRUSTED",
        "replayConsistent": valid, "authority": "NONE", "permissions": [], "reason": reason
    }


def verify_object(p: Any) -> dict:
    try:
        if not exact(p, ("format", "exportedAt", "issuerClaim", "subject", "scope",
                          "boundary", "certificate", "episodes", "payloadSha256")) or \
                p["format"] != FORMAT or not iso(p["exportedAt"]) or p["scope"] != CERT_SCOPE or \
                not sha_string(p["payloadSha256"]) or \
                not exact(p["issuerClaim"], ("app", "selfReported")) or \
                p["issuerClaim"]["app"] != "PhiLearn" or p["issuerClaim"]["selfReported"] is not True or \
                not exact(p["subject"], ("model", "mode")) or \
                not text(p["subject"]["model"], 128) or p["subject"]["mode"] not in ("bare", "guided") or \
                not exact(p["boundary"], ("authority", "requestedPermissions", "usage")) or \
                p["boundary"]["authority"] != "NONE" or p["boundary"]["usage"] != "INSPECT_ONLY" or \
                p["boundary"]["requestedPermissions"] != [] or \
                type(p["episodes"]) is not list or len(p["episodes"]) != len(CASES):
            return report("Schema or no-authority boundary rejected.")
        if len(encoded(p).encode("utf-8")) > MAX_BYTES:
            return report("JSON evidence exceeds size limit.")
        cert = p["certificate"]
        if type(cert) is not dict or cert.get("protocol") != CERT_PROTOCOL or \
                cert.get("provenance") != "LOCAL_UNTRUSTED" or cert.get("scope") != CERT_SCOPE or \
                not text(cert.get("id"), 128) or not iso(cert.get("issuedAt")) or \
                cert.get("model") != p["subject"]["model"] or cert.get("mode") != p["subject"]["mode"] or \
                not text(cert.get("summary"), 1000) or type(cert.get("support")) is not dict or \
                not sha_string(cert.get("evidenceSha256")) or \
                type(cert.get("scenarioIds")) is not list or type(cert.get("evidenceIds")) is not list or \
                len(cert["scenarioIds"]) != len(CASES) or len(cert["evidenceIds"]) != len(CASES):
            return report("Certificate scope or identity rejected.")
        used: set[str] = set()
        for index, scenario in enumerate(CASES):
            ep = p["episodes"][index]
            evidence_id = cert["evidenceIds"][index]
            if cert["scenarioIds"][index] != scenario[0] or not text(evidence_id, 128) or \
                    evidence_id in used or type(ep) is not dict or \
                    ep.get("id") != evidence_id or ep.get("model") != cert["model"] or \
                    ep.get("mode") != cert["mode"] or ep.get("scenarioId") != scenario[0] or \
                    not replay(ep, scenario):
                return report("Synthetic trace replay or source identity failed: " + scenario[0])
            used.add(evidence_id)
        cert_payload = {"protocol": CERT_PROTOCOL, "scope": CERT_SCOPE,
                        "model": cert["model"], "mode": cert["mode"], "episodes": p["episodes"]}
        if digest(cert_payload) != cert["evidenceSha256"]:
            return report("R7 evidence digest mismatch.")
        body = {key: p[key] for key in ("format", "exportedAt", "issuerClaim", "subject",
                                       "scope", "boundary", "certificate", "episodes")}
        if digest(body) != p["payloadSha256"]:
            return report("R8 envelope digest mismatch.")
        return report("Six synthetic action traces replay and two SHA-256 digests match. "
                      "Unsigned, unauthenticated claim; no privileges.", True)
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError):
        return report("Unsupported, malformed or inconsistent source data.")


def verify_bytes(raw: bytes) -> dict:
    if len(raw) > MAX_BYTES:
        return report("Input exceeds 256000 bytes.")
    try:
        return verify_object(json.loads(raw.decode("utf-8")))
    except (UnicodeError, ValueError, RecursionError):
        return report("Invalid JSON or encoding.")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python3 scripts/skill_passport_verify.py <local-passport.json>", file=sys.stderr)
        return 2
    try:
        path = Path(argv[1])
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ValueError("Not a bounded local file.")
        with path.open("rb") as handle:
            payload = handle.read(MAX_BYTES + 1)
        result = verify_bytes(payload)
    except (OSError, ValueError) as exc:
        print("Passport rejected: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["replayConsistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
