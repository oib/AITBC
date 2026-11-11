from __future__ import annotations

import json
from typing import Any

from aitbc_sdk.receipts import SignatureValidation
from pydantic import BaseModel, Field, field_validator

# Bounds for admin-supplied inputs (#1746). These fields feed argon2
# (password), keccak hashing (message_base64), and unbounded sqlite writes
# (metadata/secret_key), so unbounded values are an allocation/DoS surface
# even behind require_admin_api_key + rate limiting.
_MAX_PASSWORD_LEN = 1024
_MAX_SECRET_KEY_B64_LEN = 256  # a 32-byte key is ~44 base64 chars
# ~64 KiB decoded — orders of magnitude beyond any real sign payload, while
# still rejecting multi-hundred-MB bodies before b64decode runs.
_MAX_MESSAGE_B64_LEN = 87_384
_MAX_METADATA_ITEMS = 64
_MAX_METADATA_BYTES = 8192
_MAX_DICT_ITEMS = 64
_MAX_DICT_BYTES = 16_384
_MAX_WALLET_ID_LEN = 256
_MAX_CHAIN_ID_LEN = 128
_MAX_ADDRESS_LEN = 128


def _check_bounded_dict(value: dict[str, Any], *, max_bytes: int) -> dict[str, Any]:
    """Reject dicts whose JSON serialization exceeds ``max_bytes``."""
    if len(json.dumps(value, default=str)) > max_bytes:
        raise ValueError("dict payload too large")
    return value


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
    chain_id: str = Field(max_length=_MAX_CHAIN_ID_LEN)
    wallet_id: str = Field(max_length=_MAX_WALLET_ID_LEN)
    password: str = Field(max_length=_MAX_PASSWORD_LEN)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=_MAX_METADATA_ITEMS)
    secret_key: str | None = Field(default=None, max_length=_MAX_SECRET_KEY_B64_LEN)

    @field_validator("metadata")
    @classmethod
    def _metadata_within_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _check_bounded_dict(value, max_bytes=_MAX_METADATA_BYTES)


class WalletCreateResponse(BaseModel):
    wallet: WalletDescriptor


class WalletUnlockRequest(BaseModel):
    password: str = Field(max_length=_MAX_PASSWORD_LEN)


class WalletUnlockResponse(BaseModel):
    wallet_id: str
    chain_id: str
    unlocked: bool


class WalletSignRequest(BaseModel):
    password: str = Field(max_length=_MAX_PASSWORD_LEN)
    message_base64: str = Field(max_length=_MAX_MESSAGE_B64_LEN)


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
    source_chain_id: str = Field(max_length=_MAX_CHAIN_ID_LEN)
    target_chain_id: str = Field(max_length=_MAX_CHAIN_ID_LEN)
    wallet_id: str = Field(max_length=_MAX_WALLET_ID_LEN)
    password: str = Field(max_length=_MAX_PASSWORD_LEN)
    new_password: str | None = Field(default=None, max_length=_MAX_PASSWORD_LEN)


class WalletMigrationResponse(BaseModel):
    success: bool
    source_wallet: WalletDescriptor
    target_wallet: WalletDescriptor
    migration_timestamp: str


class WalletTransactionRequest(BaseModel):
    """Request to send a transaction from a wallet"""

    password: str = Field(max_length=_MAX_PASSWORD_LEN)
    recipient: str = Field(max_length=_MAX_ADDRESS_LEN)
    amount: int
    fee: int = 36
    nonce: int | None = None
    chain_id: str | None = Field(default=None, max_length=_MAX_CHAIN_ID_LEN)
    payload: dict[str, Any] | None = Field(default=None, max_length=_MAX_DICT_ITEMS)

    @field_validator("payload")
    @classmethod
    def _payload_within_size(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value
        return _check_bounded_dict(value, max_bytes=_MAX_DICT_BYTES)


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
