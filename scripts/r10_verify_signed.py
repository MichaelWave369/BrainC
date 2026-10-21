#!/usr/bin/env python3
"""BrainC R10: optional Ed25519 provenance consumer, OFFLINE / READ-ONLY.

No API route, memory changes, model routing, permissions, system tool calls,
network access or implicit public-key onboarding. Requires operator-pinned
out-of-band trust file, cryptography Ed25519, and valid R9 R8-source replay.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from skill_passport_verify import verify_object as verify_r8_object

SIGNED_FORMAT = "philearn.signed-skill-passport.v1"
TRUST_FORMAT = "philearn.r10.trust-store.v1"
SCOPE = "R6_SYNTHETIC_JSON_TOOL_GAUNTLET_6_CASES"
DOMAIN = "PHILEARN-R10-ED25519-SKILL-PASSPORT-V1"
MAX_BYTES = 320_000


def result(status: str, reason: str, *,
           source: bool = False, pinned: bool = False,
           signature: bool = False, reviewed: bool = False) -> dict:
    return {
        "status": status,
        "signatureValid": signature,
        "sourceReplayConsistent": source,
        "keyPinned": pinned,
        "operatorReview": "ACKNOWLEDGED_FOR_INSPECTION" if signature and reviewed else "NOT_GRANTED",
        "authority": "NONE",
        "permissions": [],
        "actionAllowed": False,
        "reason": reason,
    }


def exact(value: Any, names: tuple[str, ...]) -> bool:
    return type(value) is dict and set(value) == set(names)


def label(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", value) is not None


def digest(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"sha256:[a-f0-9]{64}", value) is not None


def timestamp(value: Any) -> bool:
    if type(value) is not str or len(value) > 40 or not re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        return False
    from datetime import datetime
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def b64(value: Any) -> bytes | None:
    if type(value) is not str or len(value) > 1200 or not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", value):
        return None
    try:
        raw = base64.b64decode(value, validate=True)
        return raw if base64.b64encode(raw).decode("ascii") == value else None
    except (binascii.Error, ValueError):
        return None


def check_trust(store: Any) -> bool:
    if not exact(store, ("format", "keys")) or store["format"] != TRUST_FORMAT or \
            type(store["keys"]) is not list or len(store["keys"]) > 40:
        return False
    try:
        from cryptography.hazmat.primitives.serialization import load_der_public_key, Encoding, PublicFormat
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return False
    seen: set[tuple[str, str]] = set()
    for key in store["keys"]:
        if not exact(key, ("issuerId", "keyId", "publicKeySpkiBase64", "allowedScope", "active")) or \
                not label(key["issuerId"]) or not digest(key["keyId"]) or \
                key["allowedScope"] != SCOPE or type(key["active"]) is not bool:
            return False
        der = b64(key["publicKeySpkiBase64"])
        if der is None:
            return False
        try:
            public_key = load_der_public_key(der)
            if not isinstance(public_key, Ed25519PublicKey):
                return False
            canonical = public_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        except (ValueError, TypeError):
            return False
        if "sha256:" + hashlib.sha256(canonical).hexdigest() != key["keyId"]:
            return False
        identity = (key["issuerId"], key["keyId"])
        if identity in seen:
            return False
        seen.add(identity)
    return True


def verify_signed_object(signed: Any, store: Any = None,
                         reviewed: bool = False) -> dict:
    if not exact(signed, ("format", "algorithm", "issuerId", "keyId", "signedAt",
                          "passport", "signature")) or \
            signed["format"] != SIGNED_FORMAT or signed["algorithm"] != "Ed25519" or \
            not label(signed["issuerId"]) or not digest(signed["keyId"]) or \
            not timestamp(signed["signedAt"]):
        return result("REJECTED_SCHEMA", "Unrecognized signed-envelope schema.")
    raw_sig = b64(signed["signature"])
    if raw_sig is None or len(raw_sig) != 64:
        return result("REJECTED_SCHEMA", "Invalid detached Ed25519 signature encoding.")
    try:
        raw = json.dumps(signed, separators=(",", ":"), ensure_ascii=False)
        if len(raw.encode("utf-8")) > MAX_BYTES:
            return result("REJECTED_SIZE", "Signed envelope too large.")
        base = verify_r8_object(signed["passport"])
        if not base["replayConsistent"]:
            return result("REJECTED_REPLAY", "R8 source evidence not replayable: " + base["reason"])
    except (ValueError, TypeError, KeyError, RecursionError):
        return result("REJECTED_REPLAY", "Malformed or unsupported R8 evidence.")
    if store is None:
        return result("UNPINNED_SIGNATURE", "No receiver-controlled pinned key; signature unverified.", source=True)
    if not check_trust(store):
        return result("REJECTED_TRUST_STORE", "Invalid local public-key trust store.")
    matches = [
        key for key in store["keys"]
        if key["active"] and key["issuerId"] == signed["issuerId"] and
        key["keyId"] == signed["keyId"] and key["allowedScope"] == signed["passport"]["scope"]
    ]
    if len(matches) != 1:
        return result("UNPINNED_SIGNATURE", "No active pinned signer for the fixed scope.", source=True)
    try:
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        from cryptography.exceptions import InvalidSignature
        public_key = load_der_public_key(b64(matches[0]["publicKeySpkiBase64"]))
        message = "\n".join((
            DOMAIN, signed["issuerId"], signed["keyId"], signed["signedAt"],
            signed["passport"]["payloadSha256"], ""
        )).encode("utf-8")
        public_key.verify(raw_sig, message)
    except (InvalidSignature, ValueError, TypeError):
        return result("SIGNATURE_INVALID", "Signature does not match pinned key and content.",
                      source=True, pinned=True)
    return result("SIGNATURE_VALID_PINNED_NO_AUTHORITY",
                  "Signed by the pinned key; synthetic traces replay. No operational permissions.",
                  source=True, pinned=True, signature=True, reviewed=reviewed)


def verify_signed_bytes(raw: bytes, store: Any = None, reviewed: bool = False) -> dict:
    if len(raw) > MAX_BYTES:
        return result("REJECTED_SIZE", "Input exceeds signed-envelope size limit.")
    try:
        return verify_signed_object(json.loads(raw.decode("utf-8")), store, reviewed)
    except (UnicodeError, ValueError, TypeError, RecursionError):
        return result("REJECTED_JSON", "Malformed JSON or encoding.")


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3, 4) or (len(argv) == 4 and argv[3] != "--review"):
        print("Usage: python3 scripts/r10_verify_signed.py <signed.json> [operator-trust.json] [--review]",
              file=sys.stderr)
        return 2
    if len(argv) == 3 and argv[2] == "--review":
        print("Review requires an operator-pinned public key file.", file=sys.stderr)
        return 2
    try:
        path = Path(argv[1])
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ValueError("Not a bounded local signed evidence file.")
        signed_bytes = path.read_bytes()
        store = None
        if len(argv) >= 3:
            trust_path = Path(argv[2])
            if not trust_path.is_file() or trust_path.stat().st_size > 16_000:
                raise ValueError("Trust store must be a bounded local JSON file.")
            store = json.loads(trust_path.read_text(encoding="utf-8"))
        checked = verify_signed_bytes(signed_bytes, store, len(argv) == 4)
        print(json.dumps(checked, indent=2))
        return 0 if checked["signatureValid"] else 1
    except (OSError, ValueError) as exc:
        print("R10 rejected: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
