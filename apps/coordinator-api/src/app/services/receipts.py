from __future__ import annotations

from typing import Any, Dict, Optional
from secrets import token_hex
from datetime import datetime

from aitbc_crypto.signing import ReceiptSigner

from sqlmodel import Session

from ..config import settings
from ..domain import Job, JobReceipt


class ReceiptService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._signer: Optional[ReceiptSigner] = None
        self._attestation_signer: Optional[ReceiptSigner] = None
        if settings.receipt_signing_key_hex:
            key_bytes = bytes.fromhex(settings.receipt_signing_key_hex)
            self._signer = ReceiptSigner(key_bytes)
        if settings.receipt_attestation_key_hex:
            attest_bytes = bytes.fromhex(settings.receipt_attestation_key_hex)
            self._attestation_signer = ReceiptSigner(attest_bytes)

    def create_receipt(
        self,
        job: Job,
        miner_id: str,
        job_result: Dict[str, Any] | None,
        result_metrics: Dict[str, Any] | None,
    ) -> Dict[str, Any] | None:
        if self._signer is None:
            return None
        payload = {
            "version": "1.0",
            "receipt_id": token_hex(16),
            "job_id": job.id,
            "provider": miner_id,
            "client": job.client_id,
            "units": _first_present([
                (result_metrics or {}).get("units"),
                (job_result or {}).get("units"),
            ], default=0.0),
            "unit_type": _first_present([
                (result_metrics or {}).get("unit_type"),
                (job_result or {}).get("unit_type"),
            ], default="gpu_seconds"),
            "price": _first_present([
                (result_metrics or {}).get("price"),
                (job_result or {}).get("price"),
            ]),
            "started_at": int(job.requested_at.timestamp()) if job.requested_at else int(datetime.utcnow().timestamp()),
            "completed_at": int(datetime.utcnow().timestamp()),
            "metadata": {
                "job_payload": job.payload,
                "job_constraints": job.constraints,
                "result": job_result,
                "metrics": result_metrics,
            },
        }
        payload["signature"] = self._signer.sign(payload)
        if self._attestation_signer:
            payload.setdefault("attestations", [])
            attestation_payload = dict(payload)
            attestation_payload.pop("attestations", None)
            attestation_payload.pop("signature", None)
            payload["attestations"].append(self._attestation_signer.sign(attestation_payload))
        receipt_row = JobReceipt(job_id=job.id, receipt_id=payload["receipt_id"], payload=payload)
        self.session.add(receipt_row)
        return payload


def _first_present(values: list[Optional[Any]], default: Optional[Any] = None) -> Optional[Any]:
    for value in values:
        if value is not None:
            return value
    return default
