from __future__ import annotations

from typing import Any

from aitbc_sdk.receipts import SignatureValidation  # type: ignore[import-not-found]
from pydantic import BaseModel


class SignatureValidationModel(BaseModel):
    key_id: str
    alg: str = "Ed25519"
    valid: bool


class ReceiptVerificationModel(BaseModel):
    job_id: str
    receipt_id: str
    miner_signature: SignatureValidationModel
    coordinator_attestations: list[SignatureValidationModel]
    all_valid: bool


class ReceiptVerifyResponse(BaseModel):
    result: ReceiptVerificationModel


def _signature_to_model(sig: SignatureValidation | SignatureValidationModel) -> SignatureValidationModel:
    if isinstance(sig, SignatureValidationModel):
        return sig
    return SignatureValidationModel(key_id=sig.key_id, alg=sig.algorithm, valid=sig.valid)


def from_validation_result(result: Any) -> ReceiptVerificationModel:
    return ReceiptVerificationModel(
        job_id=result.job_id,
        receipt_id=result.receipt_id,
        miner_signature=_signature_to_model(result.miner_signature),
        coordinator_attestations=[_signature_to_model(att) for att in result.coordinator_attestations],
        all_valid=result.all_valid,
    )


class ReceiptVerificationListResponse(BaseModel):
    items: list[ReceiptVerificationModel]


class WalletDescriptor(BaseModel):
    wallet_id: str
    chain_id: str
    public_key: str
    address: str | None
    metadata: dict[str, Any]


class WalletListResponse(BaseModel):
    items: list[WalletDescriptor]


class WalletCreateRequest(BaseModel):
    chain_id: str
    wallet_id: str
    password: str
    metadata: dict[str, Any] = {}
    secret_key: str | None = None


class WalletCreateResponse(BaseModel):
    wallet: WalletDescriptor


class WalletUnlockRequest(BaseModel):
    password: str


class WalletUnlockResponse(BaseModel):
    wallet_id: str
    chain_id: str
    unlocked: bool


class WalletSignRequest(BaseModel):
    password: str
    message_base64: str


class WalletSignResponse(BaseModel):
    wallet_id: str
    chain_id: str
    signature_base64: str


class ChainInfo(BaseModel):
    chain_id: str
    name: str
    status: str
    coordinator_url: str
    created_at: str
    updated_at: str
    wallet_count: int
    recent_activity: int


class ChainListResponse(BaseModel):
    chains: list[ChainInfo]
    total_chains: int
    active_chains: int


class ChainCreateRequest(BaseModel):
    chain_id: str
    name: str
    coordinator_url: str
    coordinator_api_key: str
    metadata: dict[str, Any] = {}


class ChainCreateResponse(BaseModel):
    chain: ChainInfo


class WalletMigrationRequest(BaseModel):
    source_chain_id: str
    target_chain_id: str
    wallet_id: str
    password: str
    new_password: str | None = None


class WalletMigrationResponse(BaseModel):
    success: bool
    source_wallet: WalletDescriptor
    target_wallet: WalletDescriptor
    migration_timestamp: str


class WalletTransactionRequest(BaseModel):
    """Request to send a transaction from a wallet"""

    password: str
    recipient: str
    amount: int
    fee: int = 1000
    nonce: int | None = None
    chain_id: str | None = None
    payload: dict[str, Any] | None = None


class WalletTransactionResponse(BaseModel):
    """Response after submitting a transaction"""

    success: bool
    tx_hash: str
    status: str
    sender: str
    recipient: str
    amount: int
    fee: int
    nonce: int
