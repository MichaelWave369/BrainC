#!/usr/bin/env python3
"""R12: offline signed operator governance history for INSPECTION ONLY.

Ed25519 signatures, linked chain hashes, separately retained head checkpoints.
No API routes, tools, model calls, permissions, or automatic skill imports.
An editable local ledger cannot independently prove historical completeness:
persist its checkpoint out of band. Clocks/operators are local claims.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat, load_der_public_key, load_pem_private_key,
)

from r10_verify_signed import verify_signed_object
from r11_enrollment import enrollment_id, envelope_hash

LEDGER_FORMAT = "philearn.r12.governance-ledger.v1"
EVENT_FORMAT = "philearn.r12.operator-event.v1"
TRUST_FORMAT = "philearn.r12.operator-trust.v1"
CHECKPOINT_FORMAT = "philearn.r12.checkpoint.v1"
DOMAIN = "PHILEARN-R12-OPERATOR-EVENT-V1"
SCOPE = "R6_SYNTHETIC_JSON_TOOL_GAUNTLET_6_CASES"
MAX_BYTES = 192_000
MAX_EVENTS = 128
GENESIS = "0" * 64
EVENT_FIELDS = {
    "format", "seq", "prevHash", "type", "enrollmentId", "envelopeSha256",
    "issuerId", "issuerKeyId", "model", "scope", "operatorId", "operatorKeyId",
    "at", "expiresAt",
}


def compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha(value: Any) -> str:
    return hashlib.sha256(compact(value).encode("utf-8")).hexdigest()


def exact(value: Any, fields: set[str]) -> bool:
    return type(value) is dict and set(value) == fields


def label(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", value) is not None


def hexdigest(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def key_id(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"sha256:[a-f0-9]{64}", value) is not None


def utc(value: Any) -> datetime:
    if type(value) is not str or len(value) > 40 or \
            not re.match(r"^\d{4}-\d\d-\d\dT", value):
        raise ValueError("Invalid bounded ISO clock.")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timezone required.")
    return dt.astimezone(timezone.utc)


def iso(value: Any) -> bool:
    try:
        utc(value)
        return True
    except (ValueError, TypeError, OverflowError):
        return False


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def decode_b64(value: Any) -> bytes | None:
    if type(value) is not str or len(value) >= 1200 or \
            re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", value) is None:
        return None
    try:
        raw = base64.b64decode(value, validate=True)
        return raw if base64.b64encode(raw).decode("ascii") == value else None
    except (ValueError, binascii.Error):
        return None


def public_key_id(key: Ed25519PublicKey) -> str:
    return "sha256:" + hashlib.sha256(
        key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    ).hexdigest()


def create_operator_record(operator_id: str, key: Ed25519PublicKey) -> dict:
    if not label(operator_id) or not isinstance(key, Ed25519PublicKey):
        raise ValueError("Operator requires a bounded ID and Ed25519 public key.")
    return {
        "operatorId": operator_id,
        "keyId": public_key_id(key),
        "publicKeySpkiBase64": base64.b64encode(
            key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        ).decode("ascii"),
        "active": True,
    }


def validate_operator_trust(store: Any) -> bool:
    if not exact(store, {"format", "operators"}) or \
            store["format"] != TRUST_FORMAT or type(store["operators"]) is not list or \
            len(store["operators"]) > 40:
        return False
    try:
        if len(compact(store).encode("utf-8")) > 16_000:
            return False
    except (TypeError, ValueError):
        return False
    seen = set()
    for entry in store["operators"]:
        if not exact(entry, {"operatorId", "keyId", "publicKeySpkiBase64", "active"}) or \
                not label(entry["operatorId"]) or not key_id(entry["keyId"]) or \
                type(entry["active"]) is not bool:
            return False
        der = decode_b64(entry["publicKeySpkiBase64"])
        if der is None:
            return False
        try:
            key = load_der_public_key(der)
            if not isinstance(key, Ed25519PublicKey) or \
                    public_key_id(key) != entry["keyId"]:
                return False
        except (ValueError, TypeError):
            return False
        identity = (entry["operatorId"], entry["keyId"])
        if identity in seen:
            return False
        seen.add(identity)
    return True


def empty_ledger() -> dict:
    return {"format": LEDGER_FORMAT, "entries": []}


def empty_checkpoint() -> dict:
    return {"format": CHECKPOINT_FORMAT, "count": 0, "headHash": GENESIS}


def message(event: dict) -> bytes:
    return (DOMAIN + "\n" + compact(event) + "\n").encode("utf-8")


def verdict(status: str, reason: str, head: str = GENESIS,
            count: int = 0, chain: bool = False, approved: bool = False) -> dict:
    return {
        "status": status, "reason": reason, "chainValid": chain,
        "headHash": head, "eventCount": count, "reviewApproved": approved,
        "authority": "NONE", "permissions": [], "actionAllowed": False,
    }


def verify_ledger(ledger: Any, trust: Any) -> dict:
    if not validate_operator_trust(trust):
        return verdict("OPERATOR_TRUST_INVALID", "No valid operator-pinned public keys.")
    if not exact(ledger, {"format", "entries"}) or ledger["format"] != LEDGER_FORMAT or \
            type(ledger["entries"]) is not list or len(ledger["entries"]) > MAX_EVENTS:
        return verdict("LEDGER_INVALID", "Invalid chain envelope.")
    try:
        if len(compact(ledger).encode("utf-8")) > MAX_BYTES:
            return verdict("LEDGER_INVALID", "Oversize chain.")
    except (TypeError, ValueError, RecursionError):
        return verdict("LEDGER_INVALID", "Invalid chain JSON.")
    prev_hash = GENESIS
    prev_time = None
    states: dict[str, dict] = {}
    for i, entry in enumerate(ledger["entries"], 1):
        if not exact(entry, {"event", "signature"}):
            return verdict("ENTRY_INVALID", "Malformed record.", prev_hash, i - 1)
        signature = decode_b64(entry["signature"])
        if signature is None or len(signature) != 64:
            return verdict("ENTRY_INVALID", "Malformed Ed25519 signature.", prev_hash, i - 1)
        event = entry["event"]
        if not exact(event, EVENT_FIELDS) or event["format"] != EVENT_FORMAT or \
                type(event["seq"]) is not int or event["seq"] != i or \
                event["prevHash"] != prev_hash or \
                event["type"] not in ("APPROVE_INSPECTION", "REVOKE_INSPECTION", "EXPIRE_INSPECTION") or \
                not hexdigest(event["enrollmentId"]) or not hexdigest(event["envelopeSha256"]) or \
                not label(event["issuerId"]) or not key_id(event["issuerKeyId"]) or \
                type(event["model"]) is not str or not 1 <= len(event["model"]) <= 128 or \
                event["scope"] != SCOPE or not label(event["operatorId"]) or \
                not key_id(event["operatorKeyId"]) or not iso(event["at"]) or \
                (event["expiresAt"] is not None and not iso(event["expiresAt"])):
            return verdict("ENTRY_INVALID", "Out-of-sequence, out-of-scope, or malformed event.", prev_hash, i - 1)
        at = utc(event["at"])
        if prev_time is not None and at < prev_time:
            return verdict("CLOCK_REGRESSION", "Claimed event clock regressed.", prev_hash, i - 1)
        prev_time = at
        matches = [record for record in trust["operators"] if record["active"] and
                   record["operatorId"] == event["operatorId"] and
                   record["keyId"] == event["operatorKeyId"]]
        if len(matches) != 1:
            return verdict("OPERATOR_NOT_PINNED", "Unknown or revoked signer.", prev_hash, i - 1)
        try:
            public = load_der_public_key(decode_b64(matches[0]["publicKeySpkiBase64"]))
            public.verify(signature, message(event))
        except (InvalidSignature, TypeError, ValueError):
            return verdict("SIGNATURE_INVALID", "Signed event no longer matches.", prev_hash, i - 1)
        previous = states.get(event["enrollmentId"])
        if event["type"] == "APPROVE_INSPECTION":
            if previous or event["expiresAt"] is None:
                return verdict("EVENT_TRANSITION_INVALID", "Duplicate or missing approval lease.", prev_hash, i - 1)
            end = utc(event["expiresAt"])
            if end <= at or end - at > timedelta(days=7):
                return verdict("EVENT_TRANSITION_INVALID", "Approval lease outside bounds.", prev_hash, i - 1)
            states[event["enrollmentId"]] = {"event": event, "closed": False}
        else:
            if not previous or previous["closed"] or event["expiresAt"] is not None or \
                    any(previous["event"][field] != event[field] for field in (
                        "envelopeSha256", "issuerId", "issuerKeyId", "model", "scope")):
                return verdict("EVENT_TRANSITION_INVALID", "Closure lacks matching active approval.", prev_hash, i - 1)
            if event["type"] == "EXPIRE_INSPECTION" and at < utc(previous["event"]["expiresAt"]):
                return verdict("PREMATURE_EXPIRY", "Explicit expiry before stated deadline.", prev_hash, i - 1)
            previous["closed"] = True
            previous["closedType"] = event["type"]
        prev_hash = sha(entry)
    result = verdict("CHAIN_VALID_UNANCHORED",
                     "Operator signatures replay, but an independently retained checkpoint is required.",
                     prev_hash, len(ledger["entries"]), True)
    result["latestStates"] = states
    return result


def create_checkpoint(ledger: dict, trust: dict) -> dict:
    checked = verify_ledger(ledger, trust)
    if not checked["chainValid"]:
        raise ValueError(checked["reason"])
    return {"format": CHECKPOINT_FORMAT, "count": checked["eventCount"],
            "headHash": checked["headHash"]}


def checkpoint_matches(checkpoint: Any, result: dict) -> bool:
    return exact(checkpoint, {"format", "count", "headHash"}) and \
        checkpoint["format"] == CHECKPOINT_FORMAT and \
        type(checkpoint["count"]) is int and checkpoint["count"] >= 0 and \
        hexdigest(checkpoint["headHash"]) and result["chainValid"] and \
        checkpoint["count"] == result["eventCount"] and \
        checkpoint["headHash"] == result["headHash"]


def pinned_private(store: dict, operator_id: str, private_pem: str) -> tuple:
    key = load_pem_private_key(private_pem.encode("utf-8"), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Ed25519 operator signing key required.")
    key_id_ = public_key_id(key.public_key())
    if not validate_operator_trust(store) or \
            sum(1 for rec in store["operators"] if rec["active"] and
                rec["operatorId"] == operator_id and rec["keyId"] == key_id_) != 1:
        raise ValueError("Operator signing key is not active and locally pinned.")
    return key, key_id_


def new_entry(kind: str, base: dict, at: str, expires_at: str | None,
              operator_id: str, op_key_id: str, ledger: dict, key: Ed25519PrivateKey,
              checked: dict) -> dict:
    event = {
        "format": EVENT_FORMAT, "seq": len(ledger["entries"]) + 1,
        "prevHash": checked["headHash"], "type": kind,
        "enrollmentId": base["enrollmentId"], "envelopeSha256": base["envelopeSha256"],
        "issuerId": base["issuerId"], "issuerKeyId": base["issuerKeyId"],
        "model": base["model"], "scope": SCOPE,
        "operatorId": operator_id, "operatorKeyId": op_key_id,
        "at": at, "expiresAt": expires_at,
    }
    return {"event": event, "signature": base64.b64encode(key.sign(message(event))).decode("ascii")}


def append_approval(signed: Any, passport_trust: Any, operator_trust: Any,
                    ledger: Any, private_pem: str, operator_id: str,
                    at: str, lease_hours: int, confirmed: bool = False,
                    checkpoint: Any = None) -> dict:
    if confirmed is not True or not iso(at) or type(lease_hours) is not int or \
            not 1 <= lease_hours <= 168:
        raise ValueError("Explicit confirmation and bounded lease required.")
    checked = verify_ledger(ledger, operator_trust)
    if not checked["chainValid"]:
        raise ValueError(checked["reason"])
    if checkpoint is not None and not checkpoint_matches(checkpoint, checked):
        raise ValueError("Prior independently retained checkpoint mismatch.")
    if len(ledger["entries"]) and checkpoint is None:
        raise ValueError("Existing chain requires prior operator checkpoint.")
    source = verify_signed_object(signed, passport_trust)
    if not source["signatureValid"] or not source["sourceReplayConsistent"] or \
            not source["keyPinned"]:
        raise ValueError("Pinned R10 source evidence must replay first.")
    key, op_key_id = pinned_private(operator_trust, operator_id, private_pem)
    identifier = enrollment_id(signed)
    base = {
        "enrollmentId": identifier, "envelopeSha256": envelope_hash(signed),
        "issuerId": signed["issuerId"], "issuerKeyId": signed["keyId"],
        "model": signed["passport"]["subject"]["model"],
    }
    end = (utc(at) + timedelta(hours=lease_hours)).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")
    entry = new_entry("APPROVE_INSPECTION", base, at, end,
                      operator_id, op_key_id, ledger, key, checked)
    updated = {"format": LEDGER_FORMAT, "entries": [*ledger["entries"], entry]}
    if not verify_ledger(updated, operator_trust)["chainValid"]:
        raise ValueError("Generated chain did not validate.")
    return updated


def append_closure(kind: str, id_: str, operator_trust: Any, ledger: Any,
                   private_pem: str, operator_id: str, at: str,
                   confirmed: bool = False, checkpoint: Any = None) -> dict:
    if confirmed is not True or kind not in ("REVOKE_INSPECTION", "EXPIRE_INSPECTION") or \
            not hexdigest(id_) or not iso(at):
        raise ValueError("Explicit confirmation and valid closure request required.")
    checked = verify_ledger(ledger, operator_trust)
    if not checked["chainValid"]:
        raise ValueError(checked["reason"])
    if not checkpoint_matches(checkpoint, checked):
        raise ValueError("Matching independently retained prior checkpoint required.")
    latest = checked["latestStates"].get(id_)
    if not latest or latest["closed"]:
        raise ValueError("Enrollment missing or already terminally closed.")
    key, op_key_id = pinned_private(operator_trust, operator_id, private_pem)
    prior = latest["event"]
    base = {
        "enrollmentId": id_, "envelopeSha256": prior["envelopeSha256"],
        "issuerId": prior["issuerId"], "issuerKeyId": prior["issuerKeyId"],
        "model": prior["model"],
    }
    event = new_entry(kind, base, at, None, operator_id, op_key_id, ledger, key, checked)
    updated = {"format": LEDGER_FORMAT, "entries": [*ledger["entries"], event]}
    if not verify_ledger(updated, operator_trust)["chainValid"]:
        raise ValueError("Generated closure did not validate.")
    return updated


def evaluate(signed: Any, passport_trust: Any, operator_trust: Any,
             ledger: Any, checkpoint: Any, now: str) -> dict:
    if not iso(now):
        return verdict("INVALID_CLOCK", "Bounded clock required.")
    checked = verify_ledger(ledger, operator_trust)
    if not checked["chainValid"]:
        return checked
    if not checkpoint_matches(checkpoint, checked):
        return verdict("UNANCHORED_OR_CHANGED", "External checkpoint absent or outdated.",
                       checked["headHash"], checked["eventCount"], True)
    source = verify_signed_object(signed, passport_trust)
    if not source["signatureValid"] or not source["sourceReplayConsistent"] or \
            not source["keyPinned"]:
        return verdict("SOURCE_REJECTED", "Pinned signed source or replay rejected.",
                       checked["headHash"], checked["eventCount"], True)
    id_ = enrollment_id(signed)
    state = checked["latestStates"].get(id_)
    if state is None:
        return verdict("NOT_ENROLLED", "No operator-signed approval for this envelope.",
                       checked["headHash"], checked["eventCount"], True)
    prior = state["event"]
    if prior["envelopeSha256"] != envelope_hash(signed) or \
            prior["issuerId"] != signed["issuerId"] or \
            prior["issuerKeyId"] != signed["keyId"] or \
            prior["model"] != signed["passport"]["subject"]["model"] or \
            prior["scope"] != signed["passport"]["scope"]:
        return verdict("SOURCE_MISMATCH", "Review refers to other evidence.",
                       checked["headHash"], checked["eventCount"], True)
    if state["closed"]:
        return verdict("REVOKED" if state["closedType"] == "REVOKE_INSPECTION"
                       else "EXPIRED_EVENT", "Operator signed terminal closure.",
                       checked["headHash"], checked["eventCount"], True)
    at = utc(now)
    if at < utc(prior["at"]):
        return verdict("NOT_YET_VALID", "Approval timestamp in future.",
                       checked["headHash"], checked["eventCount"], True)
    if at >= utc(prior["expiresAt"]):
        return verdict("EXPIRED", "Inspection lease expired.",
                       checked["headHash"], checked["eventCount"], True)
    return verdict("INSPECTION_APPROVED_WITH_SIGNED_HISTORY",
                   "Operator-signed review and external checkpoint match. No operational authority.",
                   checked["headHash"], checked["eventCount"], True, True)


def read_json(path: str, limit: int):
    f = Path(path)
    if not f.is_file() or f.stat().st_size > limit:
        raise ValueError("Input not a bounded local file.")
    return json.loads(f.read_text(encoding="utf-8"))


def save_new(path: str, data: Any):
    with Path(path).open("x", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def main(argv: list[str]) -> int:
    args = argv[1:]
    try:
        if len(args) == 3 and args[0] == "init":
            save_new(args[1], empty_ledger())
            save_new(args[2], empty_checkpoint())
        elif len(args) == 12 and args[0] == "approve" and args[-1] == "--confirm":
            _, signed_path, issuer_keys_path, operator_keys_path, ledger_path, key_path, \
                operator_id, lease, checkpoint_path, out_ledger, out_head, _confirm = args
            next_ = append_approval(
                read_json(signed_path, 320000), read_json(issuer_keys_path, 16000),
                read_json(operator_keys_path, 16000), read_json(ledger_path, MAX_BYTES),
                Path(key_path).read_text(encoding="utf-8"), operator_id,
                now_utc(), int(lease), True, read_json(checkpoint_path, 500))
            trust = read_json(operator_keys_path, 16000)
            save_new(out_ledger, next_)
            save_new(out_head, create_checkpoint(next_, trust))
        elif len(args) == 10 and args[0] in ("revoke", "expire") and args[-1] == "--confirm":
            action, id_, operator_keys_path, ledger_path, key_path, operator_id, \
                checkpoint_path, out_ledger, out_head, _confirm = args
            trust = read_json(operator_keys_path, 16000)
            kind = "REVOKE_INSPECTION" if action == "revoke" else "EXPIRE_INSPECTION"
            next_ = append_closure(kind, id_, trust, read_json(ledger_path, MAX_BYTES),
                                   Path(key_path).read_text(encoding="utf-8"), operator_id,
                                   now_utc(), True, read_json(checkpoint_path, 500))
            save_new(out_ledger, next_)
            save_new(out_head, create_checkpoint(next_, trust))
        elif len(args) == 6 and args[0] == "check":
            _, signed_path, issuer_keys_path, operator_keys_path, ledger_path, checkpoint_path = args
            checked = evaluate(read_json(signed_path, 320000), read_json(issuer_keys_path, 16000),
                               read_json(operator_keys_path, 16000), read_json(ledger_path, MAX_BYTES),
                               read_json(checkpoint_path, 500), now_utc())
            print(json.dumps({key: value for key, value in checked.items()
                              if key != "latestStates"}, indent=2))
            return 0 if checked["reviewApproved"] else 1
        else:
            print(
                "Usage:\n"
                "  python3 scripts/r12_governance.py init <new-ledger> <new-checkpoint>\n"
                "  python3 scripts/r12_governance.py approve <signed> <R10-trust> "
                "<operator-trust> <ledger> <operator-private.pem> <operator-id> <lease-hours> "
                "<prior-checkpoint> <out-ledger> <out-checkpoint> --confirm\n"
                "  python3 scripts/r12_governance.py revoke|expire <enrollment-id> "
                "<operator-trust> <ledger> <operator-private.pem> <operator-id> "
                "<prior-checkpoint> <out-ledger> <out-checkpoint> --confirm\n"
                "  python3 scripts/r12_governance.py check <signed> <R10-trust> "
                "<operator-trust> <ledger> <independent-checkpoint>", file=sys.stderr)
            return 2
        print("R12 recorded local inspection governance only; no permissions granted.")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("R12 refused: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
