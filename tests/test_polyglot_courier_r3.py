"""Synthetic, Python-produced R3 vector for the BrainC offline courier."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("cryptography")
from api.core.polyglot_courier import open_brainc_courier

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = (FIXTURES / "polyglot-r3-synthetic.json").read_text()
PUBLIC = (FIXTURES / "polyglot-r3-public.pem").read_bytes()
PASSWORD = "synthetic-test-phrase-not-secret"
WHEN = 1820000001


def read(raw=SAMPLE, *, trusted=PUBLIC, password=PASSWORD, now=WHEN):
    return open_brainc_courier(
        raw, trusted_signer_public_pem=trusted, passphrase=password, now=now
    )


def test_python_signed_vector_decrypts_to_unverified_context():
    context = read()
    assert context.capsule_id == "synthetic-fixture-r3"
    assert context.summary == "Fictional wrist gesture"
    assert context.entities == ("GenEWrist",)
    assert context.status == "unverified_external_context"


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(reader="pocketbrain"),
    lambda d: d.update(schema="phi.memory.polyglot.consumer.r2"),
    lambda d: d.update(expires_at=d["expires_at"] + 1),
    lambda d: d.update(issued_at=d["issued_at"] - 1),
    lambda d: d.update(ciphertext=d["ciphertext"][:-2] + "xx"),
    lambda d: d.update(salt="A"),
    lambda d: d.update(iv="A"),
    lambda d: d.update(signature="A"),
    lambda d: d.update(unknown="should fail"),
])
def test_tampering_or_bad_shapes_rejected(mutation):
    record = json.loads(SAMPLE)
    mutation(record)
    with pytest.raises(PermissionError):
        read(json.dumps(record))


def test_wrong_pin_cannot_verify_signed_content():
    with pytest.raises(PermissionError):
        read(trusted=b"-----BEGIN PUBLIC KEY-----\ninvalid\n-----END PUBLIC KEY-----\n")


def test_wrong_passphrase_does_not_reveal_memory():
    with pytest.raises(PermissionError) as exc:
        read(password="incorrect-synthetic-password")
    assert "Synthetic VR wrist-check" not in str(exc.value)


def test_expired_and_not_yet_valid():
    with pytest.raises(PermissionError):
        read(now=1820000120)
    with pytest.raises(PermissionError):
        read(now=1819999999)


def test_duplicate_json_key_rejected():
    with pytest.raises(PermissionError):
        read(SAMPLE.replace('"reader":', '"reader":"brainc","reader":', 1))


def test_nonstandard_constant_and_bad_utf8():
    with pytest.raises(PermissionError):
        read(SAMPLE.replace('"expires_at": 1820000120', '"expires_at": NaN'))
    with pytest.raises(PermissionError):
        read("x" * 32769)


def test_unverified_context_cannot_be_mutated():
    context = read()
    with pytest.raises(AttributeError):
        context.text = "new"


def test_public_vector_has_no_private_key_or_real_memory():
    assert "PRIVATE KEY" not in SAMPLE + PUBLIC.decode()
    assert "synthetic-fixture-r3" in read().capsule_id
