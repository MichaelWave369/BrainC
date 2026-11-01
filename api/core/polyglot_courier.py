"""Φ Memory Polyglot R3: authenticated *file* courier for BrainC.

Signed with pinned ECDSA P-256 public key, encrypted with AES-256-GCM and
PBKDF2-SHA256. No HTTP route, database write, prompt insertion or tools.
Only operator-supplied synthetic files until independently security reviewed.
"""
from __future__ import annotations

import base64
import json
import re
import time

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from api.core.polyglot_consumer import UnverifiedMemoryContext, parse_brainc_polyglot

SCHEMA = "phi.memory.polyglot.courier.r3"
_ITERATIONS = 310_000
_FIELDS = {"schema", "reader", "issued_at", "expires_at", "salt", "iv",
           "ciphertext", "signature"}
_DENIED = "memory courier: invalid, untrusted, or expired package"


def _strict_pairs(pairs):
    obj = {}
    for key, val in pairs:
        if key in obj:
            raise ValueError("duplicate field")
        obj[key] = val
    return obj


def _reject_constant(value):
    raise ValueError("nonstandard JSON constant")


def _b64(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch("[A-Za-z0-9_-]+", value):
        raise ValueError("invalid base64")
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != value:
        raise ValueError("noncanonical base64")
    return raw


def _joined(pkg: dict, fields: tuple[str, ...]) -> bytes:
    return "\n".join(str(pkg[k]) for k in fields).encode("ascii")


def _passphrase(passphrase):
    if (not isinstance(passphrase, str) or not 16 <= len(passphrase) <= 1024
            or any(ord(ch) < 32 for ch in passphrase)):
        raise ValueError("invalid passphrase")
    return passphrase.encode("utf-8")


def open_brainc_courier(
    raw: str, *, trusted_signer_public_pem: bytes,
    passphrase: str, now: int | None = None,
) -> UnverifiedMemoryContext:
    """Authenticate a pinned signer, decrypt, then validate unverified R2 data."""
    try:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > 32768:
            raise ValueError("oversized courier")
        pkg = json.loads(raw, object_pairs_hook=_strict_pairs,
                         parse_constant=_reject_constant)
        if not isinstance(pkg, dict) or set(pkg) != _FIELDS:
            raise ValueError("invalid envelope")
        if pkg["schema"] != SCHEMA or pkg["reader"] != "brainc":
            raise ValueError("wrong recipient")
        issued, expires = pkg["issued_at"], pkg["expires_at"]
        timestamp = int(time.time()) if now is None else now
        if (type(issued) is not int or type(expires) is not int
                or type(timestamp) is not int or issued > timestamp
                or expires <= timestamp or not 1 <= expires - issued <= 300):
            raise ValueError("invalid lifetime")
        salt, iv = _b64(pkg["salt"]), _b64(pkg["iv"])
        cipher, signature = _b64(pkg["ciphertext"]), _b64(pkg["signature"])
        if (len(salt) != 16 or len(iv) != 12 or len(signature) != 64
                or not 16 <= len(cipher) <= 16384):
            raise ValueError("invalid field sizes")
        if not isinstance(trusted_signer_public_pem, bytes):
            raise ValueError("missing trusted signer pin")
        pub = serialization.load_pem_public_key(trusted_signer_public_pem)
        if (not isinstance(pub, ec.EllipticCurvePublicKey)
                or not isinstance(pub.curve, ec.SECP256R1)):
            raise ValueError("wrong signer key")
        r, s = (int.from_bytes(signature[:32], "big"),
                int.from_bytes(signature[32:], "big"))
        signed = _joined(pkg, ("schema", "reader", "issued_at", "expires_at",
                               "salt", "iv", "ciphertext"))
        pub.verify(utils.encode_dss_signature(r, s), signed, ec.ECDSA(hashes.SHA256()))
        key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                        iterations=_ITERATIONS).derive(_passphrase(passphrase))
        aad = _joined(pkg, ("schema", "reader", "issued_at", "expires_at"))
        content = AESGCM(key).decrypt(iv, cipher, aad)
        if len(content) > 16384:
            raise ValueError("oversized plaintext")
        return parse_brainc_polyglot(content.decode("utf-8"))
    except (ValueError, TypeError, UnicodeError, KeyError, InvalidSignature,
            InvalidTag, OverflowError) as exc:
        raise PermissionError(_DENIED) from exc
