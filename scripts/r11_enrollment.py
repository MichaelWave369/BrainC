#!/usr/bin/env python3
"""R11: offline, receiver-controlled INSPECTION-ONLY enrollment.

No FastAPI route, DB write, live tools, model routing, or new authority.
Valid R10 pinned signing-key proof, explicit operator review, and a bounded
local lease are independent gates. All verdicts deny operational actions.
Registry records are LOCAL and EDITABLE: not signed policy credentials.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from r10_verify_signed import verify_signed_object

FORMAT = "philearn.r11.inspection-enrollment.v1"
SCOPE = "R6_SYNTHETIC_JSON_TOOL_GAUNTLET_6_CASES"
MAX_BYTES = 48_000
MAX_ENTRIES = 64


def json_compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(json_compact(value).encode("utf-8")).hexdigest()


def label(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", value) is not None


def sha(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def datetime_utc(value: Any) -> datetime:
    if type(value) is not str or len(value) > 40 or not re.match(r"^\d{4}-\d\d-\d\dT", value):
        raise ValueError("Invalid ISO datetime.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone required.")
    return parsed.astimezone(timezone.utc)


def iso(value: Any) -> bool:
    try:
        datetime_utc(value)
        return True
    except (TypeError, ValueError, OverflowError):
        return False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def empty_registry() -> dict:
    return {"format": FORMAT, "entries": []}


def validate_registry(registry: Any) -> bool:
    if type(registry) is not dict or set(registry) != {"format", "entries"} or \
            registry.get("format") != FORMAT or type(registry.get("entries")) is not list or \
            len(registry["entries"]) > MAX_ENTRIES:
        return False
    try:
        if len(json_compact(registry).encode("utf-8")) > MAX_BYTES:
            return False
    except (ValueError, TypeError, RecursionError):
        return False
    seen = set()
    fields = {"enrollmentId", "envelopeSha256", "issuerId", "keyId", "model",
              "scope", "operatorId", "reviewedAt", "expiresAt", "state"}
    for entry in registry["entries"]:
        if type(entry) is not dict or set(entry) != fields or \
                not sha(entry["enrollmentId"]) or not sha(entry["envelopeSha256"]) or \
                not label(entry["issuerId"]) or type(entry["keyId"]) is not str or \
                re.fullmatch(r"sha256:[a-f0-9]{64}", entry["keyId"]) is None or \
                type(entry["model"]) is not str or not 1 <= len(entry["model"]) <= 128 or \
                entry["scope"] != SCOPE or not label(entry["operatorId"]) or \
                not iso(entry["reviewedAt"]) or not iso(entry["expiresAt"]) or \
                entry["state"] not in ("APPROVED_INSPECTION", "REVOKED"):
            return False
        reviewed = datetime_utc(entry["reviewedAt"])
        until = datetime_utc(entry["expiresAt"])
        if until <= reviewed or until-reviewed > timedelta(days=7) or \
                entry["enrollmentId"] in seen:
            return False
        seen.add(entry["enrollmentId"])
    return True


def envelope_hash(signed: Any) -> str:
    return digest(signed)


def enrollment_id(signed: dict) -> str:
    return digest({
        "issuerId": signed["issuerId"], "keyId": signed["keyId"],
        "envelopeSha256": envelope_hash(signed),
        "scope": signed["passport"]["scope"],
    })


def approve_for_inspection(signed: Any, trust: Any, registry: Any,
                           operator: str, reviewed_at: str | None = None,
                           lease_hours: int = 24, confirmed: bool = False) -> dict:
    if confirmed is not True:
        raise ValueError("Explicit operator approval required.")
    reviewed_at = reviewed_at or utc_now()
    if not label(operator) or not iso(reviewed_at) or type(lease_hours) is not int or \
            not 1 <= lease_hours <= 168:
        raise ValueError("Invalid operator, date, or bounded inspection lease.")
    if not validate_registry(registry):
        raise ValueError("Invalid local receiver registry.")
    checked = verify_signed_object(signed, trust)
    if checked["signatureValid"] is not True or \
            checked["sourceReplayConsistent"] is not True or checked["keyPinned"] is not True:
        raise ValueError("Signer or R6 replay was not verified with an operator-pinned key.")
    id_ = enrollment_id(signed)
    if any(e["enrollmentId"] == id_ for e in registry["entries"]):
        raise ValueError("Duplicate enrollment; never renew a revoked envelope.")
    if len(registry["entries"]) >= MAX_ENTRIES:
        raise ValueError("Registry full.")
    expires_at = (datetime_utc(reviewed_at) + timedelta(hours=lease_hours)).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")
    entry = {
        "enrollmentId": id_, "envelopeSha256": envelope_hash(signed),
        "issuerId": signed["issuerId"], "keyId": signed["keyId"],
        "model": signed["passport"]["subject"]["model"],
        "scope": signed["passport"]["scope"], "operatorId": operator,
        "reviewedAt": reviewed_at, "expiresAt": expires_at,
        "state": "APPROVED_INSPECTION",
    }
    updated = {"format": FORMAT, "entries": [*registry["entries"], entry]}
    if not validate_registry(updated):
        raise ValueError("Generated enrollment registry failed validation.")
    return updated


def revoke(registry: Any, id_: str, operator: str, confirmed: bool = False) -> dict:
    if confirmed is not True or not label(operator) or not sha(id_):
        raise ValueError("Operator confirmation and enrollment ID required.")
    if not validate_registry(registry):
        raise ValueError("Invalid local registry.")
    entries = [dict(e) for e in registry["entries"]]
    matches = [entry for entry in entries if entry["enrollmentId"] == id_]
    if len(matches) != 1 or matches[0]["state"] == "REVOKED":
        raise ValueError("Enrollment absent or already revoked.")
    matches[0]["state"] = "REVOKED"
    updated = {"format": FORMAT, "entries": entries}
    if not validate_registry(updated):
        raise ValueError("Revocation failed validation.")
    return updated


def decision(status: str, reason: str, signature: bool = False,
             approved: bool = False) -> dict:
    return {"status": status, "reason": reason, "signatureValid": signature,
            "reviewApproved": approved, "inspectionOnly": approved,
            "authority": "NONE", "permissions": [], "actionAllowed": False}


def evaluate(signed: Any, trust: Any, registry: Any, now: str | None = None) -> dict:
    now = now or utc_now()
    if not iso(now):
        return decision("INVALID_CLOCK", "Valid receiver-local ISO clock required.")
    try:
        checked = verify_signed_object(signed, trust)
    except (TypeError, ValueError, KeyError):
        return decision("SIGNATURE_REJECTED", "Signed source could not be verified.")
    if not checked["signatureValid"] or not checked["keyPinned"] or \
            not checked["sourceReplayConsistent"]:
        return decision("SIGNATURE_REJECTED", checked["reason"])
    if not validate_registry(registry):
        return decision("REGISTRY_REJECTED", "No valid receiver-local enrollment registry.", True)
    id_ = enrollment_id(signed)
    matches = [entry for entry in registry["entries"] if entry["enrollmentId"] == id_]
    if not matches:
        return decision("NOT_ENROLLED", "The receiver has not explicitly approved inspection.", True)
    entry = matches[0]
    if entry["state"] == "REVOKED":
        return decision("REVOKED", "Operator revoked this envelope enrollment.", True)
    if entry["envelopeSha256"] != envelope_hash(signed) or \
            entry["issuerId"] != signed["issuerId"] or \
            entry["keyId"] != signed["keyId"] or \
            entry["model"] != signed["passport"]["subject"]["model"] or \
            entry["scope"] != signed["passport"]["scope"]:
        return decision("REGISTRY_REJECTED", "Enrollment binding mismatch.", True)
    at = datetime_utc(now)
    if at < datetime_utc(entry["reviewedAt"]):
        return decision("NOT_YET_VALID", "Review timestamp is in the future.", True)
    if at >= datetime_utc(entry["expiresAt"]):
        return decision("EXPIRED", "Inspection enrollment lease expired.", True)
    return decision("APPROVED_FOR_INSPECTION_ONLY",
                    "Pinned signature and replay verified; manual approval for evidence inspection only.",
                    True, True)


def read_json(filename: str, max_bytes: int) -> Any:
    path = Path(filename)
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("Not a bounded local input file.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_new(filename: str, data: Any):
    with Path(filename).open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def main(argv: list[str]) -> int:
    args = argv[1:]
    try:
        if len(args) == 2 and args[0] == "init":
            save_new(args[1], empty_registry())
            print("Created an empty receiver-controlled enrollment registry.")
        elif len(args) == 7 and args[0] == "approve":
            _, signed_name, trust_name, registry_name, operator, hours, output = args
            value = approve_for_inspection(read_json(signed_name, 320_000),
                 read_json(trust_name, 16_000), read_json(registry_name, MAX_BYTES),
                 operator, utc_now(), int(hours), True)
            save_new(output, value)
            print("Wrote new inspection-only approval registry; manually replace the local registry.")
        elif len(args) == 5 and args[0] == "revoke":
            _, registry_name, id_, operator, output = args
            value = revoke(read_json(registry_name, MAX_BYTES), id_, operator, True)
            save_new(output, value)
            print("Wrote revocation; manually replace receiver registry.")
        elif len(args) == 4 and args[0] == "check":
            _, signed_name, trust_name, registry_name = args
            report = evaluate(read_json(signed_name, 320_000),
                              read_json(trust_name, 16_000),
                              read_json(registry_name, MAX_BYTES))
            print(json.dumps(report, indent=2))
            return 0 if report["reviewApproved"] else 1
        else:
            print(
                "Usage:\n  python3 scripts/r11_enrollment.py init <new-registry.json>\n"
                "  python3 scripts/r11_enrollment.py approve <signed.json> <pinned-trust.json> "
                "<registry.json> <operator-id> <lease-hours> <new-registry.json>\n"
                "  python3 scripts/r11_enrollment.py revoke <registry.json> <id> <operator-id> "
                "<new-registry.json>\n"
                "  python3 scripts/r11_enrollment.py check <signed.json> "
                "<pinned-trust.json> <registry.json>", file=sys.stderr)
            return 2
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("R11 rejected: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
