import base64

from nacl.signing import SigningKey

from aitbc_crypto.receipt import canonical_json, receipt_hash
from aitbc_crypto.signing import ReceiptSigner, ReceiptVerifier


def test_canonical_json_orders_keys():
    payload = {
        "b": 2,
        "a": 1,
        "nested": {
            "y": None,
            "x": 5,
        },
    }
    json_str = canonical_json(payload)
    assert json_str == '{"a":1,"b":2,"nested":{"x":5}}'


def test_receipt_sign_and_verify():
    payload = {
        "version": "1.0",
        "receipt_id": "rcpt-1",
        "job_id": "job-1",
        "provider": "miner-1",
        "client": "client-1",
        "units": 1.0,
        "unit_type": "gpu_seconds",
        "started_at": 1695720000,
        "completed_at": 1695720005,
    }

    signing_key = SigningKey.generate()
    signer = ReceiptSigner(signing_key.encode())
    signature = signer.sign(payload)

    verifier = ReceiptVerifier(signing_key.verify_key.encode())
    assert verifier.verify(payload, signature)

    # tamper payload
    tampered = payload.copy()
    tampered["units"] = 2.0
    assert verifier.verify(tampered, signature) is False
