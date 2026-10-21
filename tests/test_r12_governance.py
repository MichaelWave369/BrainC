"""R12 cross-runtime governance tests. Ephemeral synthetic-only fixtures and keys."""
import json
import sys
from pathlib import Path
import unittest

TESTS=Path(__file__).resolve().parent
sys.path.insert(0,str(TESTS))
sys.path.insert(0,str(TESTS.parent/'scripts'))
from test_r10_verify_signed import signed_fixture, HAVE_CRYPTO
import r12_governance as r12

if HAVE_CRYPTO:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

AT="2026-10-21T23:00:00.000Z"
LATER="2026-10-21T23:10:00.000Z"


def setup():
    signed,issuer_trust=signed_fixture()
    op=Ed25519PrivateKey.generate()
    pem=op.private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()).decode("utf-8")
    operator_trust={"format":r12.TRUST_FORMAT,
                    "operators":[r12.create_operator_record("operator.alpha",op.public_key())]}
    return signed,issuer_trust,operator_trust,pem


def approved():
    signed,issuer_trust,trust,pem=setup()
    ledger=r12.append_approval(signed,issuer_trust,trust,r12.empty_ledger(),pem,
                                "operator.alpha",AT,24,True,r12.empty_checkpoint())
    head=r12.create_checkpoint(ledger,trust)
    return signed,issuer_trust,trust,pem,ledger,head


@unittest.skipUnless(HAVE_CRYPTO,"Ed25519 cryptography needed")
class TestR12SignedGovernance(unittest.TestCase):
    def test_explicit_signed_inspection_approval_requires_separate_anchor(self):
        signed,issuer_trust,trust,pem,ledger,head=approved()
        self.assertTrue(r12.verify_ledger(ledger,trust)["chainValid"])
        self.assertTrue(r12.checkpoint_matches(head,r12.verify_ledger(ledger,trust)))
        result=r12.evaluate(signed,issuer_trust,trust,ledger,head,LATER)
        self.assertEqual(result["status"],"INSPECTION_APPROVED_WITH_SIGNED_HISTORY")
        self.assertTrue(result["reviewApproved"])
        self.assertFalse(result["actionAllowed"])
        self.assertEqual(result["authority"],"NONE")
        self.assertEqual(result["permissions"],[])
        self.assertEqual(r12.evaluate(signed,issuer_trust,trust,ledger,None,LATER)["status"],
                         "UNANCHORED_OR_CHANGED")

    def test_edit_delete_reorder_and_stale_checkpoint_refuse(self):
        signed,issuer_trust,trust,pem,ledger,head=approved()
        edited=json.loads(json.dumps(ledger))
        edited["entries"][0]["event"]["model"]="tampered"
        self.assertFalse(r12.verify_ledger(edited,trust)["chainValid"])
        self.assertTrue(r12.verify_ledger(r12.empty_ledger(),trust)["chainValid"])
        self.assertFalse(r12.evaluate(signed,issuer_trust,trust,r12.empty_ledger(),
                                      head,LATER)["reviewApproved"])
        enrolled=ledger["entries"][0]["event"]["enrollmentId"]
        revoked=r12.append_closure("REVOKE_INSPECTION",enrolled,trust,ledger,pem,
                                   "operator.alpha",LATER,True,head)
        swapped=dict(revoked,entries=list(reversed(revoked["entries"])))
        self.assertFalse(r12.verify_ledger(swapped,trust)["chainValid"])
        self.assertEqual(r12.evaluate(signed,issuer_trust,trust,revoked,head,LATER)["status"],
                         "UNANCHORED_OR_CHANGED")

    def test_revocation_is_signed_and_terminal(self):
        signed,issuer_trust,trust,pem,ledger,head=approved()
        id_=ledger["entries"][0]["event"]["enrollmentId"]
        revoked=r12.append_closure("REVOKE_INSPECTION",id_,trust,ledger,pem,
                                   "operator.alpha",LATER,True,head)
        new_head=r12.create_checkpoint(revoked,trust)
        self.assertEqual(r12.evaluate(signed,issuer_trust,trust,revoked,new_head,LATER)["status"],
                         "REVOKED")
        with self.assertRaises(ValueError):
            r12.append_closure("REVOKE_INSPECTION",id_,trust,revoked,pem,
                               "operator.alpha","2026-10-21T22:00:00Z",True,new_head)
        with self.assertRaises(ValueError):
            r12.append_approval(signed,issuer_trust,trust,revoked,pem,
                                "operator.alpha","2026-10-21T22:00:00Z",24,True,new_head)
        with self.assertRaises(ValueError):
            r12.append_closure("EXPIRE_INSPECTION",id_,trust,ledger,pem,
                               "operator.alpha",LATER,True,head)

    def test_separate_signer_keys_and_operator_confirmation(self):
        signed,issuer_trust,trust,pem=setup()
        with self.assertRaises(ValueError):
            r12.append_approval(signed,issuer_trust,trust,r12.empty_ledger(),pem,
                                "operator.alpha",AT,24,False,r12.empty_checkpoint())
        with self.assertRaises(ValueError):
            r12.append_approval(signed,issuer_trust,trust,r12.empty_ledger(),pem,
                                "operator.alpha",AT,169,True,r12.empty_checkpoint())
        other=Ed25519PrivateKey.generate().private_bytes(
            Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()).decode()
        with self.assertRaises(ValueError):
            r12.append_approval(signed,issuer_trust,trust,r12.empty_ledger(),other,
                                "operator.alpha",AT,24,True,r12.empty_checkpoint())
        active=r12.append_approval(signed,issuer_trust,trust,r12.empty_ledger(),pem,
                                   "operator.alpha",AT,24,True,r12.empty_checkpoint())
        revoked_keys={"format":trust["format"],
                      "operators":[dict(trust["operators"][0],active=False)]}
        self.assertFalse(r12.verify_ledger(active,revoked_keys)["chainValid"])

    def test_bad_event_signatures_duplicates_and_registry_conformance(self):
        _,_,trust,_,ledger,_=approved()
        modified=json.loads(json.dumps(ledger))
        import base64
        modified["entries"][0]["signature"]=base64.b64encode(b"\0"*64).decode()
        self.assertFalse(r12.verify_ledger(modified,trust)["chainValid"])
        duplicate={"format":trust["format"],"operators":trust["operators"]*2}
        self.assertFalse(r12.validate_operator_trust(duplicate))
        self.assertFalse(r12.verify_ledger(dict(ledger,adminOverride=True),trust)["chainValid"])
        self.assertEqual(r12.empty_checkpoint()["headHash"],r12.GENESIS)


if __name__=="__main__":
    unittest.main()
