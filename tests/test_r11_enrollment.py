"""R11: temporary signed fixture, receiver-local inspection-only approvals."""
import sys
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'scripts'))
sys.path.insert(0,str(HERE))
from test_r10_verify_signed import signed_fixture, HAVE_CRYPTO
import r11_enrollment as r11

T0="2026-10-21T21:00:00Z"
T1="2026-10-21T22:00:00Z"


@unittest.skipUnless(HAVE_CRYPTO,"cryptography is required for R10/R11 test fixtures")
class TestR11Enrollment(unittest.TestCase):
    def test_default_denial_and_explicit_approval_are_separate(self):
        signed,trust=signed_fixture()
        self.assertEqual(r11.evaluate(signed,trust,None,T1)["status"],"REGISTRY_REJECTED")
        self.assertEqual(r11.evaluate(signed,trust,r11.empty_registry(),T1)["status"],"NOT_ENROLLED")
        with self.assertRaises(ValueError):
            r11.approve_for_inspection(signed,trust,r11.empty_registry(),
                                       "operator",T0,24,False)
        registry=r11.approve_for_inspection(signed,trust,r11.empty_registry(),
                                            "operator",T0,24,True)
        self.assertTrue(r11.validate_registry(registry))
        result=r11.evaluate(signed,trust,registry,T1)
        self.assertEqual(result["status"],"APPROVED_FOR_INSPECTION_ONLY")
        self.assertTrue(result["reviewApproved"])
        self.assertTrue(result["inspectionOnly"])
        self.assertEqual(result["authority"],"NONE")
        self.assertFalse(result["actionAllowed"])
        self.assertEqual(result["permissions"],[])

    def test_expiry_future_gate_and_revocation(self):
        signed,trust=signed_fixture()
        reg=r11.approve_for_inspection(signed,trust,r11.empty_registry(),
                                       "operator",T0,24,True)
        self.assertEqual(r11.evaluate(signed,trust,reg,"2026-10-21T20:59:59Z")["status"],"NOT_YET_VALID")
        self.assertEqual(r11.evaluate(signed,trust,reg,"2026-10-22T21:00:00Z")["status"],"EXPIRED")
        id_=reg["entries"][0]["enrollmentId"]
        revoked=r11.revoke(reg,id_,"operator",True)
        self.assertEqual(r11.evaluate(signed,trust,revoked,T1)["status"],"REVOKED")
        with self.assertRaises(ValueError):
            r11.revoke(revoked,id_,"operator",True)
        with self.assertRaises(ValueError):
            r11.approve_for_inspection(signed,trust,revoked,"operator",T0,1,True)
        with self.assertRaises(ValueError):
            r11.revoke(reg,id_,"operator",False)

    def test_invalid_keys_and_scope_cannot_be_promoted(self):
        signed,trust=signed_fixture()
        changed=dict(signed,signedAt="2026-10-21T23:00:01Z")
        self.assertEqual(r11.evaluate(changed,trust,r11.empty_registry(),T1)["status"],
                         "SIGNATURE_REJECTED")
        revoked_keys={"format":trust["format"],
                      "keys":[dict(trust["keys"][0],active=False)]}
        with self.assertRaises(ValueError):
            r11.approve_for_inspection(signed,revoked_keys,r11.empty_registry(),
                                       "operator",T0,24,True)
        for hours in (0,169,-2,2.5):
            with self.assertRaises(ValueError):
                r11.approve_for_inspection(signed,trust,r11.empty_registry(),
                                           "operator",T0,hours,True)

    def test_registry_invariants_and_binding(self):
        signed,trust=signed_fixture()
        reg=r11.approve_for_inspection(signed,trust,r11.empty_registry(),
                                       "operator",T0,24,True)
        first=reg["entries"][0]
        self.assertEqual(len(r11.envelope_hash(signed)),64)
        for changed in (
            dict(first,scope="FULL_PRODUCTION_ACCESS"),
            dict(first,state="APPROVED_TOOL_EXECUTION"),
            dict(first,expiresAt="2026-11-21T21:00:00Z"),
        ):
            self.assertFalse(r11.validate_registry({"format":r11.FORMAT,"entries":[changed]}))
        dupe={"format":r11.FORMAT,"entries":[first,first]}
        self.assertFalse(r11.validate_registry(dupe))
        swapped={"format":r11.FORMAT,"entries":[dict(first,model="different-model")]}
        self.assertEqual(r11.evaluate(signed,trust,swapped,T1)["status"],"REGISTRY_REJECTED")


if __name__=="__main__":
    unittest.main()
