from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import httpx
import base64

from aitbc_crypto.signing import ReceiptVerifier


@dataclass
class SignatureValidation:
    key_id: str
    valid: bool
    algorithm: str = "Ed25519"


@dataclass
class ReceiptVerification:
    receipt: Dict[str, Any]
    miner_signature: SignatureValidation
    coordinator_attestations: List[SignatureValidation]

    @property
    def verified(self) -> bool:
        if not self.miner_signature.valid:
            return False
        return all(att.valid for att in self.coordinator_attestations)


class CoordinatorReceiptClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"X-Api-Key": self.api_key},
        )

    def fetch_latest(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._client() as client:
            resp = client.get(f"/v1/jobs/{job_id}/receipt")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    def fetch_history(self, job_id: str) -> List[Dict[str, Any]]:
        with self._client() as client:
            resp = client.get(f"/v1/jobs/{job_id}/receipts")
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data["items"]
            raise ValueError("unexpected receipt history response shape")


def _verify_signature(payload: Dict[str, Any], signature: Dict[str, Any]) -> SignatureValidation:
    key_id = signature.get("key_id", "")
    verifier = ReceiptVerifier(_decode_key(key_id))
    valid = verifier.verify(payload, signature)
    return SignatureValidation(key_id=key_id, valid=valid)


def verify_receipt(receipt: Dict[str, Any]) -> ReceiptVerification:
    payload = {k: v for k, v in receipt.items() if k not in {"signature", "attestations"}}
    miner_sig = receipt.get("signature") or {}
    miner_validation = _verify_signature(payload, miner_sig)

    attestations = receipt.get("attestations") or []
    att_validations = [
        _verify_signature(payload, att) for att in attestations if isinstance(att, dict)
    ]

    return ReceiptVerification(
        receipt=receipt,
        miner_signature=miner_validation,
        coordinator_attestations=att_validations,
    )


def verify_receipts(receipts: Iterable[Dict[str, Any]]) -> List[ReceiptVerification]:
    return [verify_receipt(receipt) for receipt in receipts]


def _decode_key(data: str) -> bytes:
    if not data:
        return b""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)
