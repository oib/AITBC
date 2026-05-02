from __future__ import annotations

from aitbc import get_logger

logger = get_logger(__name__)
from datetime import datetime, timezone
from secrets import token_hex
from typing import Any

from aitbc_crypto.signing import ReceiptSigner
from sqlmodel import Session

from ..config import settings
from ..domain import Job, JobReceipt
from .zk_proofs import zk_proof_service


class ReceiptService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._signer: ReceiptSigner | None = None
        self._attestation_signer: ReceiptSigner | None = None
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
        job_result: dict[str, Any] | None,
        result_metrics: dict[str, Any] | None,
        privacy_level: str | None = None,
    ) -> dict[str, Any] | None:
        if self._signer is None:
            return None
        metrics = result_metrics or {}
        result_payload = job_result or {}
        unit_type = _first_present(
            [
                metrics.get("unit_type"),
                result_payload.get("unit_type"),
            ],
            default="gpu_seconds",
        )

        units = _coerce_float(
            _first_present(
                [
                    metrics.get("units"),
                    result_payload.get("units"),
                ]
            )
        )
        if units is None:
            duration_ms = _coerce_float(metrics.get("duration_ms"))
            if duration_ms is not None:
                units = duration_ms / 1000.0
            else:
                duration_seconds = _coerce_float(
                    _first_present(
                        [
                            metrics.get("duration_seconds"),
                            metrics.get("compute_time"),
                            result_payload.get("execution_time"),
                            result_payload.get("duration"),
                        ]
                    )
                )
                units = duration_seconds
        if units is None:
            units = 0.0

        unit_price = _coerce_float(
            _first_present(
                [
                    metrics.get("unit_price"),
                    result_payload.get("unit_price"),
                ]
            )
        )
        if unit_price is None:
            unit_price = 0.02

        price = _coerce_float(
            _first_present(
                [
                    metrics.get("price"),
                    result_payload.get("price"),
                    metrics.get("aitbc_earned"),
                    result_payload.get("aitbc_earned"),
                    metrics.get("cost"),
                    result_payload.get("cost"),
                ]
            )
        )
        if price is None:
            price = round(units * unit_price, 6)
        status_value = job.state.value if hasattr(job.state, "value") else job.state
        payload = {
            "version": "1.0",
            "receipt_id": token_hex(16),
            "job_id": job.id,
            "provider": miner_id,
            "client": job.client_id,
            "status": status_value,
            "units": units,
            "unit_type": unit_type,
            "unit_price": unit_price,
            "price": price,
            "started_at": int(job.requested_at.timestamp()) if job.requested_at else int(datetime.now(timezone.utc).timestamp()),
            "completed_at": int(datetime.now(timezone.utc).timestamp()),
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

        # Skip async ZK proof generation in synchronous context; log intent
        if privacy_level and zk_proof_service.is_enabled():
            logger.warning("ZK proof generation skipped in synchronous receipt creation")

        receipt_row = JobReceipt(job_id=job.id, receipt_id=payload["receipt_id"], payload=payload)
        self.session.add(receipt_row)
        return payload


def _first_present(values: list[Any | None], default: Any | None = None) -> Any | None:
    for value in values:
        if value is not None:
            return value
    return default


def _coerce_float(value: Any) -> float | None:
    """Coerce a value to float, returning None if not possible"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
