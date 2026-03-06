from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from aitbc_sdk import (
    CoordinatorReceiptClient,
    ReceiptVerification,
    SignatureValidation,
    verify_receipt,
    verify_receipts,
)


@dataclass
class ReceiptValidationResult:
    job_id: str
    receipt_id: str
    receipt: dict
    miner_signature: SignatureValidation
    coordinator_attestations: List[SignatureValidation]

    @property
    def miner_valid(self) -> bool:
        return self.miner_signature.valid

    @property
    def all_valid(self) -> bool:
        return self.miner_signature.valid and all(att.valid for att in self.coordinator_attestations)


class ReceiptVerifierService:
    """Wraps `aitbc_sdk` receipt verification for wallet daemon workflows."""

    def __init__(self, coordinator_url: str, api_key: str, timeout: float = 10.0) -> None:
        self.client = CoordinatorReceiptClient(coordinator_url, api_key, timeout=timeout)

    def verify_latest(self, job_id: str) -> Optional[ReceiptValidationResult]:
        receipt = self.client.fetch_latest(job_id)
        if receipt is None:
            return None
        verification = verify_receipt(receipt)
        return self._to_result(verification)

    def verify_history(self, job_id: str) -> List[ReceiptValidationResult]:
        receipts = self.client.fetch_history(job_id)
        verifications = verify_receipts(receipts)
        return [self._to_result(item) for item in verifications]

    @staticmethod
    def _to_result(verification: ReceiptVerification) -> ReceiptValidationResult:
        return ReceiptValidationResult(
            job_id=str(verification.receipt.get("job_id")),
            receipt_id=str(verification.receipt.get("receipt_id")),
            receipt=verification.receipt,
            miner_signature=verification.miner_signature,
            coordinator_attestations=list(verification.coordinator_attestations),
        )
