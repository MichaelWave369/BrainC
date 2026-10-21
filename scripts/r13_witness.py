#!/usr/bin/env python3
"""PhiLearn R13 passive Ed25519 witness verifier. Never authorizes any action."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from typing import Any
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat, load_der_public_key,
)
from r12_governance import verify_ledger, checkpoint_matches, SCOPE

WITNESS_FORMAT = "philearn.r13.witness-receipt.v1"
TRUST_FORMAT = "philearn.r13.witness-trust.v1"
DOMAIN = "PHILEARN-R13-CHECKPOINT-WITNESS-V1"
CHECKPOINT_FORMAT = "philearn.r12.checkpoint.v1"


def compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def exact(value: Any, names: set[str]) -> bool:
    return type(value) is dict and set(value) == names


def label(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", value) is not None


def key_id(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"sha256:[a-f0-9]{64}", value) is not None


def digest(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def decode_b64(value: Any) -> bytes | None:
    if type(value) is not str or len(value) >= 1200 or \
            re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", value) is None:
        return None
    try:
        raw = base64.b64decode(value, validate=True)
        return raw if base64.b64encode(raw).decode("ascii") == value else None
    except (ValueError, binascii.Error):
        return None


def fingerprint(public: Ed25519PublicKey) -> str:
    return "sha256:" + hashlib.sha256(
        public.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    ).hexdigest()


def witness_record(witness_id: str, public: Ed25519PublicKey) -> dict:
    if not label(witness_id) or not isinstance(public, Ed25519PublicKey):
        raise ValueError("Bounded witness ID and Ed25519 public key required.")
    return {
        "witnessId": witness_id,
        "keyId": fingerprint(public),
        "publicKeySpkiBase64": base64.b64encode(
            public.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        ).decode("ascii"),
        "active": True,
    }


def validate_witness_trust(store: Any, operator_store: Any = None) -> bool:
    if not exact(store, {"format", "witnesses"}) or store["format"] != TRUST_FORMAT or \
            type(store["witnesses"]) is not list or len(store["witnesses"]) > 32:
        return False
    try:
        if len(compact(store).encode("utf-8")) > 14000:
            return False
    except (TypeError, ValueError, RecursionError):
        return False
    used = set()
    operator_keys = {
        value["keyId"] for value in (operator_store or {}).get("operators", [])
        if type(value) is dict and "keyId" in value
    }
    for witness in store["witnesses"]:
        if not exact(witness, {"witnessId", "keyId", "publicKeySpkiBase64", "active"}) or \
                not label(witness["witnessId"]) or not key_id(witness["keyId"]) or \
                type(witness["active"]) is not bool or witness["keyId"] in operator_keys:
            return False
        der = decode_b64(witness["publicKeySpkiBase64"])
        if der is None:
            return False
        try:
            public = load_der_public_key(der)
            if not isinstance(public, Ed25519PublicKey) or \
                    fingerprint(public) != witness["keyId"]:
                return False
        except (ValueError, TypeError):
            return False
        identifier = (witness["witnessId"], witness["keyId"])
        if identifier in used:
            return False
        used.add(identifier)
    return True


def message(body: dict) -> bytes:
    return (DOMAIN + "\n" + compact(body) + "\n").encode("utf-8")


def witness_checkpoint(ledger: dict, operator_store: dict, witness_store: dict,
                       private: Ed25519PrivateKey, witness_id: str, signed_at: str) -> dict:
    from r12_governance import iso, utc
    if not iso(signed_at):
        raise ValueError("Invalid witness timestamp.")
    chain = verify_ledger(ledger, operator_store)
    if not chain["chainValid"]:
        raise ValueError("R12 chain invalid: " + chain["reason"])
    if not isinstance(private, Ed25519PrivateKey) or not \
            validate_witness_trust(witness_store, operator_store):
        raise ValueError("Separate Ed25519 witness and pinned trust required.")
    key = fingerprint(private.public_key())
    if len([record for record in witness_store["witnesses"]
            if record["active"] and record["witnessId"] == witness_id and
            record["keyId"] == key]) != 1:
        raise ValueError("Unknown witness private key or inactive pin.")
    final = ledger["entries"][-1]["event"]["at"] if ledger["entries"] else None
    if final and utc(signed_at) < utc(final):
        raise ValueError("Witness timestamp predates final operator event.")
    body = {
        "format": WITNESS_FORMAT,
        "witnessId": witness_id,
        "keyId": key,
        "signedAt": signed_at,
        "scope": SCOPE,
        "count": chain["eventCount"],
        "headHash": chain["headHash"],
    }
    return {
        **body,
        "signature": base64.b64encode(private.sign(message(body))).decode("ascii"),
    }


def deny(status: str, reason: str) -> dict:
    return {
        "status": status, "reason": reason, "witnessValid": False,
        "chainValid": False, "headAnchored": False,
        "authority": "NONE", "permissions": [], "actionAllowed": False,
    }


def verify_witness(ledger: Any, operators: Any, receipt: Any, witnesses: Any,
                   minimum_count: int = 0) -> dict:
    from r12_governance import iso, utc
    if type(minimum_count) is not int or minimum_count < 0:
        return deny("INVALID_FLOOR", "Receiver-protected minimum count invalid.")
    chain = verify_ledger(ledger, operators)
    if not chain["chainValid"]:
        return deny("CHAIN_INVALID", chain["reason"])
    if not validate_witness_trust(witnesses, operators):
        return deny("WITNESS_TRUST_INVALID", "Independent witness pins invalid.")
    if not exact(receipt, {"format", "witnessId", "keyId", "signedAt", "scope",
                           "count", "headHash", "signature"}) or \
            receipt["format"] != WITNESS_FORMAT or \
            not label(receipt["witnessId"]) or not key_id(receipt["keyId"]) or \
            not iso(receipt["signedAt"]) or receipt["scope"] != SCOPE or \
            type(receipt["count"]) is not int or receipt["count"] < 0 or \
            not digest(receipt["headHash"]):
        return deny("RECEIPT_INVALID", "Malformed witness receipt.")
    signature = decode_b64(receipt["signature"])
    if signature is None or len(signature) != 64:
        return deny("RECEIPT_INVALID", "Malformed Ed25519 witness signature.")
    matching = [w for w in witnesses["witnesses"] if w["active"] and
                w["witnessId"] == receipt["witnessId"] and w["keyId"] == receipt["keyId"]]
    if len(matching) != 1:
        return deny("WITNESS_UNPINNED", "Unknown or revoked witness signer.")
    body = {
        "format": receipt["format"], "witnessId": receipt["witnessId"],
        "keyId": receipt["keyId"], "signedAt": receipt["signedAt"],
        "scope": receipt["scope"], "count": receipt["count"],
        "headHash": receipt["headHash"],
    }
    try:
        public = load_der_public_key(decode_b64(matching[0]["publicKeySpkiBase64"]))
        public.verify(signature, message(body))
    except (TypeError, ValueError, InvalidSignature):
        return deny("SIGNATURE_INVALID", "Ed25519 witness signature invalid.")
    checkpoint = {
        "format": CHECKPOINT_FORMAT,
        "count": receipt["count"],
        "headHash": receipt["headHash"],
    }
    if not checkpoint_matches(checkpoint, chain):
        return deny("HEAD_MISMATCH", "Signed witness checkpoint disagrees with full chain.")
    if receipt["count"] < minimum_count:
        return deny("ROLLBACK_BELOW_FLOOR", "Witnessed count below separately retained minimum.")
    last = ledger["entries"][-1]["event"]["at"] if ledger["entries"] else None
    if last and utc(receipt["signedAt"]) < utc(last):
        return deny("WITNESS_BEFORE_LAST_EVENT", "Witness timestamp predates final event.")
    return {
        "status": "WITNESSED_HISTORY_NO_AUTHORITY",
        "reason": "Pinned operator-signed events, independently pinned witness and full history match. No action permission.",
        "witnessValid": True, "chainValid": True, "headAnchored": True,
        "count": receipt["count"], "headHash": receipt["headHash"],
        "authority": "NONE", "permissions": [], "actionAllowed": False,
    }
