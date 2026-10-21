"""R13: byte-for-byte Node -> Python signed governance fixture parity.

Node 22 emits a complete fixture using PUBLIC TEST-ONLY deterministic seed keys.
Python independently validates the same R6/R10/R12/R13 signatures and hashes.
Never use the deterministic private key seeds as real signing credentials.
"""
import base64
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import r10_verify_signed as r10
import r12_governance as r12
import r13_witness as r13
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

FIXTURE_SCRIPT=ROOT/'interop'/'r13-fixture.mjs'
def fixture():
    raw=subprocess.check_output(['node',str(FIXTURE_SCRIPT)],timeout=15)
    return json.loads(raw.decode('utf-8'))


class TestR13CrossRuntimeParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=fixture()

    def test_one_node_signed_fixture_replays_across_three_python_layers(self):
        f=self.fixture
        self.assertEqual(f["purpose"],"CROSS_RUNTIME_TEST_ONLY")
        self.assertEqual(f["fixtureVersion"],"philearn-r13-fixture-v1")
        self.assertTrue(r10.verify_signed_object(f["signed"],f["issuerTrust"])["signatureValid"])
        chain=r12.verify_ledger(f["ledger"],f["operatorTrust"])
        self.assertTrue(chain["chainValid"])
        self.assertEqual(chain["headHash"],f["checkpoint"]["headHash"])
        self.assertTrue(r12.checkpoint_matches(f["checkpoint"],chain))
        witnessed=r13.verify_witness(f["ledger"],f["operatorTrust"],
                                      f["witness"],f["witnessTrust"],f["minimumCount"])
        self.assertEqual(witnessed["status"],"WITNESSED_HISTORY_NO_AUTHORITY")
        self.assertTrue(witnessed["witnessValid"])
        self.assertTrue(witnessed["headAnchored"])
        self.assertEqual(witnessed["authority"],"NONE")
        self.assertEqual(witnessed["permissions"],[])
        self.assertFalse(witnessed["actionAllowed"])

    def test_exact_signed_message_bytes_and_hashes_match_node_crypto(self):
        f=self.fixture
        # The seeds are deliberately PUBLIC TEST material, never real secrets.
        issuer=Ed25519PrivateKey.from_private_bytes(bytes.fromhex("11"*32))
        operator=Ed25519PrivateKey.from_private_bytes(bytes.fromhex("22"*32))
        witness=Ed25519PrivateKey.from_private_bytes(bytes.fromhex("33"*32))
        signed=f["signed"]
        issuer_message="\n".join((
            r10.DOMAIN,signed["issuerId"],signed["keyId"],signed["signedAt"],
            signed["passport"]["payloadSha256"],""
        )).encode('utf-8')
        self.assertEqual(
            base64.b64encode(issuer.sign(issuer_message)).decode(),
            signed["signature"],
        )
        signed_entry=f["ledger"]["entries"][0]
        self.assertEqual(
            base64.b64encode(operator.sign(r12.message(signed_entry["event"]))).decode(),
            signed_entry["signature"],
        )
        witness_body={key:f["witness"][key] for key in (
            "format","witnessId","keyId","signedAt","scope","count","headHash"
        )}
        self.assertEqual(
            base64.b64encode(witness.sign(r13.message(witness_body))).decode(),
            f["witness"]["signature"],
        )
        self.assertEqual(r12.sha(signed_entry),f["checkpoint"]["headHash"])
        self.assertEqual(r12.envelope_hash(signed),signed_entry["event"]["envelopeSha256"])

    def test_python_produces_bit_identical_witness_receipt(self):
        f=self.fixture
        witness_key=Ed25519PrivateKey.from_private_bytes(bytes.fromhex("33"*32))
        again=r13.witness_checkpoint(f["ledger"],f["operatorTrust"],
                                     f["witnessTrust"],witness_key,"TEST.witness",
                                     f["witness"]["signedAt"])
        self.assertEqual(again,f["witness"])
        self.assertEqual(r13.compact(again),r13.compact(f["witness"]))

    def test_attacker_changes_are_rejected_and_rollback_floor_blocks_old_history(self):
        f=self.fixture
        self.assertEqual(r13.verify_witness(
            f["ledger"],f["operatorTrust"],f["witness"],f["witnessTrust"],2)["status"],
            "ROLLBACK_BELOW_FLOOR")
        altered=json.loads(json.dumps(f["ledger"]))
        altered["entries"][0]["event"]["model"]="attacker-model"
        self.assertFalse(r13.verify_witness(
            altered,f["operatorTrust"],f["witness"],f["witnessTrust"],1)["witnessValid"])
        changed=dict(f["witness"],count=2)
        self.assertFalse(r13.verify_witness(
            f["ledger"],f["operatorTrust"],changed,f["witnessTrust"],1)["witnessValid"])
        inactive=dict(f["witnessTrust"],witnesses=[
            dict(f["witnessTrust"]["witnesses"][0],active=False)
        ])
        self.assertFalse(r13.verify_witness(
            f["ledger"],f["operatorTrust"],f["witness"],inactive,1)["witnessValid"])
        same_operator=dict(f["witnessTrust"],witnesses=[
            dict(f["witnessTrust"]["witnesses"][0],
                 keyId=f["operatorTrust"]["operators"][0]["keyId"])
        ])
        self.assertFalse(r13.validate_witness_trust(same_operator,f["operatorTrust"]))


if __name__=="__main__":
    unittest.main()
