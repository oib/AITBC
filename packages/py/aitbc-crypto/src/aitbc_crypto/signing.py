from __future__ import annotations

import base64
from typing import Any

from nacl.signing import SigningKey, VerifyKey

from .receipt import canonical_json


class ReceiptSigner:
    def __init__(self, signing_key: bytes):
        self._key = SigningKey(signing_key)

    def sign(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = canonical_json(payload).encode("utf-8")
        signature = self._key.sign(message)
        return {
            "alg": "Ed25519",
            "key_id": base64.urlsafe_b64encode(self._key.verify_key.encode()).decode("utf-8").rstrip("="),
            "sig": base64.urlsafe_b64encode(signature.signature).decode("utf-8").rstrip("="),
        }


class ReceiptVerifier:
    def __init__(self, verify_key: bytes):
        self._key = VerifyKey(verify_key)

    def verify(self, payload: dict[str, Any], signature: dict[str, Any]) -> bool:
        if signature.get("alg") != "Ed25519":
            return False
        sig_bytes = base64.urlsafe_b64decode(signature["sig"] + "==")
        message = canonical_json(payload).encode("utf-8")
        try:
            self._key.verify(message, sig_bytes)
            return True
        except Exception:
            return False
