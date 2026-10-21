"""R10 offline BrainC signing checks; all keys are ephemeral test-only."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

TEST_DIR = Path(__file__).resolve().parent
SCRIPTS = TEST_DIR.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
from test_skill_passport_verify import fixture  # R9 synthetic-only fixture

SPEC = importlib.util.spec_from_file_location("r10_verify_signed", SCRIPTS / "r10_verify_signed.py")
assert SPEC and SPEC.loader
r10 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r10)

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False


def signed_fixture():
    private = Ed25519PrivateKey.generate()
    der = private.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    key_id = "sha256:" + hashlib.sha256(der).hexdigest()
    issuer_id = "operator.local"
    p = fixture()
    at = "2026-10-21T23:00:00Z"
    message = "\n".join((r10.DOMAIN, issuer_id, key_id, at, p["payloadSha256"], "")).encode()
    sig = base64.b64encode(private.sign(message)).decode("ascii")
    signed = {
        "format": r10.SIGNED_FORMAT, "algorithm": "Ed25519",
        "issuerId": issuer_id, "keyId": key_id, "signedAt": at,
        "passport": p, "signature": sig,
    }
    store = {
        "format": r10.TRUST_FORMAT,
        "keys": [{
            "issuerId": issuer_id, "keyId": key_id,
            "publicKeySpkiBase64": base64.b64encode(der).decode("ascii"),
            "allowedScope": r10.SCOPE, "active": True,
        }]
    }
    return signed, store


@unittest.skipUnless(HAVE_CRYPTO, "Requires cryptography for Ed25519 verifier")
class TestR10PinnedSigner(unittest.TestCase):
    def test_valid_signature_is_pinned_but_still_zero_authority(self):
        signed, store = signed_fixture()
        result = r10.verify_signed_object(signed, store, True)
        self.assertTrue(result["signatureValid"])
        self.assertTrue(result["sourceReplayConsistent"])
        self.assertEqual(result["status"], "SIGNATURE_VALID_PINNED_NO_AUTHORITY")
        self.assertEqual(result["authority"], "NONE")
        self.assertFalse(result["actionAllowed"])
        self.assertEqual(result["permissions"], [])
        self.assertEqual(result["operatorReview"], "ACKNOWLEDGED_FOR_INSPECTION")
        self.assertTrue(r10.check_trust(store))

    def test_missing_pin_never_auto_trusts_signature(self):
        signed, store = signed_fixture()
        self.assertEqual(r10.verify_signed_object(signed)["status"], "UNPINNED_SIGNATURE")
        store["keys"] = []
        self.assertFalse(r10.verify_signed_object(signed, store)["signatureValid"])

    def test_signature_and_input_tampering_fail(self):
        signed, store = signed_fixture()
        for altered in (
            dict(signed, signedAt="2026-10-21T23:00:01Z"),
            dict(signed, issuerId="attacker"),
            dict(signed, signature=base64.b64encode(b"\x00" * 64).decode()),
            dict(signed, passport=dict(signed["passport"], payloadSha256="0" * 64)),
        ):
            self.assertFalse(r10.verify_signed_object(altered, store)["signatureValid"])

    def test_revoked_key_wrong_scope_and_injected_key_are_rejected(self):
        signed, store = signed_fixture()
        revoked = {"format": store["format"], "keys": [dict(store["keys"][0], active=False)]}
        self.assertFalse(r10.verify_signed_object(signed, revoked)["signatureValid"])
        wrong_scope = {"format": store["format"],
                       "keys": [dict(store["keys"][0], allowedScope="ADMIN")]}
        self.assertFalse(r10.check_trust(wrong_scope))
        injected = dict(signed, selfTrustedPublicKey="attacker-key")
        self.assertFalse(r10.verify_signed_object(injected, store)["signatureValid"])

    def test_malformed_and_oversized_fail(self):
        _, store = signed_fixture()
        self.assertFalse(r10.verify_signed_bytes(b"not json", store)["signatureValid"])
        self.assertFalse(r10.verify_signed_bytes(b"x" * (r10.MAX_BYTES + 1), store)["signatureValid"])


if __name__ == "__main__":
    unittest.main()
