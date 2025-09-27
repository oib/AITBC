from __future__ import annotations

from typing import List

from aitbc_sdk import SignatureValidation

from pydantic import BaseModel


class SignatureValidationModel(BaseModel):
    key_id: str
    alg: str = "Ed25519"
    valid: bool


class ReceiptVerificationModel(BaseModel):
    job_id: str
    receipt_id: str
    miner_signature: SignatureValidationModel
    coordinator_attestations: List[SignatureValidationModel]
    all_valid: bool


class ReceiptVerifyResponse(BaseModel):
    result: ReceiptVerificationModel


def _signature_to_model(sig: SignatureValidation | SignatureValidationModel) -> SignatureValidationModel:
    if isinstance(sig, SignatureValidationModel):
        return sig
    return SignatureValidationModel(key_id=sig.key_id, alg=sig.algorithm, valid=sig.valid)


def from_validation_result(result) -> ReceiptVerificationModel:
    return ReceiptVerificationModel(
        job_id=result.job_id,
        receipt_id=result.receipt_id,
        miner_signature=_signature_to_model(result.miner_signature),
        coordinator_attestations=[_signature_to_model(att) for att in result.coordinator_attestations],
        all_valid=result.all_valid,
    )


class ReceiptVerificationListResponse(BaseModel):
    items: List[ReceiptVerificationModel]
