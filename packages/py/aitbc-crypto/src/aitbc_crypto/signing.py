from __future__ import annotations

from typing import Any, Dict

import base64

from nacl.signing import SigningKey, VerifyKey

from .receipt import canonical_json


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _urlsafe_b64decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


class ReceiptSigner:
    def __init__(self, signing_key: bytes):
        self._key = SigningKey(signing_key)

    def sign(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = canonical_json(payload).encode("utf-8")
        signed = self._key.sign(message)
        return {
            "alg": "Ed25519",
            "key_id": _urlsafe_b64encode(self._key.verify_key.encode()),
            "sig": _urlsafe_b64encode(signed.signature),
        }


class ReceiptVerifier:
    def __init__(self, verify_key: bytes):
        self._key = VerifyKey(verify_key)

    def verify(self, payload: Dict[str, Any], signature: Dict[str, Any]) -> bool:
        if signature.get("alg") != "Ed25519":
            return False
        sig_field = signature.get("sig")
        if not isinstance(sig_field, str):
            return False
        message = canonical_json(payload).encode("utf-8")
        sig_bytes = _urlsafe_b64decode(sig_field)
        try:
            self._key.verify(message, sig_bytes)
            return True
        except Exception:
            return False
