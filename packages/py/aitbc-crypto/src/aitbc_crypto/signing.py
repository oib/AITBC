from __future__ import annotations

import base64
import logging
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from .receipt import canonical_json

logger = logging.getLogger(__name__)


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
        message = canonical_json(payload).encode("utf-8")
        try:
            sig_bytes = base64.urlsafe_b64decode(signature["sig"] + "==")
        except (KeyError, ValueError, TypeError) as exc:
            # Malformed input, not a failed signature check. Both used to return a bare
            # False, so a caller could not tell "this receipt was tampered with" from
            # "we were handed the wrong dict shape".
            logger.warning("Signature payload is malformed: %s", exc)
            return False

        try:
            self._key.verify(message, sig_bytes)
            return True
        except BadSignatureError:
            # The expected negative result: a genuine mismatch. Not logged as a warning --
            # verifying untrusted receipts is the normal path.
            return False
        except Exception:
            # Anything else is a programming or environment error; losing it silently is
            # how a broken verifier looks exactly like a batch of invalid receipts.
            logger.exception("Unexpected error during signature verification")
            return False
