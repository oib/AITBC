"""
Bridge router.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from aitbc.rate_limiting import rate_limit

from ...logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/bridge", tags=["bridge"])


# ---------------------------------------------------------------------------
# Pydantic request models — validate input at the API boundary before
# passing to the bridge service layer (which still uses dict.get()).
# ---------------------------------------------------------------------------


class BridgeLockRequest(BaseModel):
    """Request body for POST /bridge/lock."""

    target_chain: str = Field(..., min_length=1, description="Target chain ID")
    sender: str = Field(..., min_length=1, description="Sender address")
    recipient: str = Field(..., min_length=1, description="Recipient address")
    amount: int = Field(..., gt=0, description="Amount to bridge (positive integer)")
    asset: str = Field(default="native", description="Asset identifier")
    source_chain: str | None = Field(default=None, description="Source chain ID (defaults to this chain)")
    signature: str = Field(..., min_length=1, description="Sender signature authorizing the lock")


class BridgeConfirmRequest(BaseModel):
    """Request body for POST /bridge/confirm."""

    transfer_id: str = Field(..., min_length=1, description="Transfer ID to confirm")
    proof: str | dict[str, Any] = Field(..., description="Merkle proof of the lock (string or dict)")
    confirmer: str | None = Field(default=None, description="Confirmer address (defaults to recipient)")
    signature: str = Field(..., min_length=1, description="Confirmer signature")


class BridgeUnlockRequest(BaseModel):
    """Request body for POST /bridge/unlock."""

    transfer_id: str = Field(..., min_length=1, description="Transfer ID to refund")
    sender: str = Field(..., min_length=1, description="Original sender address")
    signature: str = Field(..., min_length=1, description="Sender signature authorizing the refund")


class BridgeBatchRequest(BaseModel):
    """Request body for batch lock/confirm endpoints."""

    transfers: list[dict[str, Any]] = Field(..., min_length=1, description="List of transfer dicts")


class ValidatorRegisterRequest(BaseModel):
    """Request body for POST /bridge/validators/register."""

    chain_id: str = Field(..., min_length=1, description="Chain ID to register on")
    address: str = Field(..., min_length=1, description="Validator address")
    public_key: str = Field(..., min_length=1, description="Validator public key")
    signature: str = Field(..., min_length=1, description="Validator signature proving ownership")
    epoch: int = Field(default=0, ge=0, description="Epoch number (defaults to 0)")


class BlockHeaderRequest(BaseModel):
    """Request body for POST /bridge/block-headers."""

    chain_id: str = Field(..., min_length=1, description="Chain ID")
    height: int = Field(..., ge=0, description="Block height")
    hash: str = Field(..., min_length=1, description="Block hash")
    proposer: str = Field(..., min_length=1, description="Block proposer address")
    state_root: str = Field(..., min_length=1, description="State root hash")
    parent_hash: str | None = Field(default=None, description="Parent block hash")
    signature: str | None = Field(default=None, description="Block proposer signature")
    confirmation_count: int = Field(default=0, ge=0, description="Number of confirmations")
    finality_confirmed: bool = Field(default=False, description="Whether finality is confirmed")


# Optional imports - will be None if module not available
bridge_batch_confirm = None
bridge_batch_lock = None
bridge_confirm = None
bridge_health = None
bridge_lock = None
bridge_oracle_status = None
bridge_security_status = None
bridge_unlock = None
get_block_header = None
get_bridge_balance = None
get_bridge_transfer = None
get_validator_set = None
list_pending_transfers = None
register_validator = None
store_block_header = None

try:
    from ..bridge import (
        bridge_batch_confirm,
        bridge_batch_lock,
        bridge_confirm,
        bridge_health,
        bridge_lock,
        bridge_oracle_status,
        bridge_security_status,
        bridge_unlock,
        get_block_header,
        get_bridge_balance,
        get_bridge_transfer,
        get_validator_set,
        list_pending_transfers,
        register_validator,
        store_block_header,
    )
except ImportError as e:
    _logger.error("Bridge module not available: %s — affected endpoints will return 503", e)


@router.post("/lock", summary="Lock funds for cross-chain transfer")
@rate_limit(rate=20, per=60)
async def bridge_lock_route(request: Request, lock_data: BridgeLockRequest) -> dict[str, Any]:
    """Initiate a cross-chain bridge transfer by locking funds"""
    if bridge_lock is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await bridge_lock(request, lock_data.model_dump(exclude_none=True))


@router.post("/confirm", summary="Confirm and release cross-chain transfer")
@rate_limit(rate=20, per=60)
async def bridge_confirm_route(request: Request, confirm_data: BridgeConfirmRequest) -> dict[str, Any]:
    """Confirm a cross-chain bridge transfer and release funds"""
    if bridge_confirm is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await bridge_confirm(request, confirm_data.model_dump(exclude_none=True))


@router.get("/transfer/{transfer_id}", summary="Get transfer status")
@rate_limit(rate=100, per=60)
async def get_bridge_transfer_route(request: Request, transfer_id: str) -> dict[str, Any]:
    """Get the status of a cross-chain transfer"""
    if get_bridge_transfer is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await get_bridge_transfer(request, transfer_id)


@router.get("/pending", summary="List pending bridge transfers")
@rate_limit(rate=50, per=60)
async def list_pending_transfers_route(request: Request, chain_id: str | None = None) -> list[dict[str, Any]]:
    """List all pending cross-chain transfers"""
    if list_pending_transfers is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await list_pending_transfers(request, chain_id)


@router.post("/unlock", summary="Refund a pending bridge transfer")
@rate_limit(rate=20, per=60)
async def bridge_unlock_route(request: Request, unlock_data: BridgeUnlockRequest) -> dict[str, Any]:
    """Refund/cancel a pending bridge transfer — return locked funds to sender"""
    if bridge_unlock is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await bridge_unlock(request, unlock_data.model_dump(exclude_none=True))


@router.get("/balance/{chain_id}", summary="Get bridge balance for a chain")
@rate_limit(rate=100, per=60)
async def get_bridge_balance_route(request: Request, chain_id: str) -> dict[str, Any]:
    """Get total locked amount for a chain (sum of pending/locked transfers)"""
    if get_bridge_balance is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await get_bridge_balance(request, chain_id)


@router.get("/health", summary="Bridge health check")
@rate_limit(rate=100, per=60)
async def bridge_health_route(request: Request) -> dict[str, Any]:
    """Get bridge health status — active transfers, pending count, configuration"""
    if bridge_health is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await bridge_health(request)


@router.get("/status/{transfer_id}", summary="Get transfer status (alias)")
@rate_limit(rate=100, per=60)
async def get_bridge_status_route(request: Request, transfer_id: str) -> dict[str, Any]:
    """Alias for GET /bridge/transfer/{transfer_id}"""
    if get_bridge_transfer is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await get_bridge_transfer(request, transfer_id)


@router.post("/batch/lock", summary="Batch lock multiple transfers")
@rate_limit(rate=20, per=60)
async def bridge_batch_lock_route(request: Request, batch_data: BridgeBatchRequest) -> list[dict[str, Any]]:
    """Batch lock multiple cross-chain transfers"""
    if bridge_batch_lock is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await bridge_batch_lock(request, batch_data.model_dump(exclude_none=True))


@router.post("/batch/confirm", summary="Batch confirm multiple transfers")
@rate_limit(rate=20, per=60)
async def bridge_batch_confirm_route(request: Request, batch_data: BridgeBatchRequest) -> list[dict[str, Any]]:
    """Batch confirm multiple cross-chain transfers (gated by BRIDGE_RELEASE_ENABLED)"""
    if bridge_batch_confirm is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await bridge_batch_confirm(request, batch_data.model_dump(exclude_none=True))


@router.post("/validators/register", summary="Register a bridge validator")
@rate_limit(rate=20, per=60)
async def register_validator_route(request: Request, reg_data: ValidatorRegisterRequest) -> dict[str, Any]:
    """Register a validator for bridge multi-sig operations (v0.7.1)"""
    if register_validator is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await register_validator(request, reg_data.model_dump(exclude_none=True))


@router.get("/validators/{chain_id}", summary="Get validator set for a chain")
@rate_limit(rate=100, per=60)
async def get_validator_set_route(request: Request, chain_id: str) -> dict[str, Any]:
    """Get the validator set for a chain (v0.7.1). Optional ?epoch= query param."""
    if get_validator_set is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await get_validator_set(request, chain_id)


@router.get("/security/status", summary="Bridge security status")
@rate_limit(rate=100, per=60)
async def bridge_security_status_route(request: Request) -> dict[str, Any]:
    """Get bridge security status — multi-sig config, validator count, etc. (v0.7.1)"""
    if bridge_security_status is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await bridge_security_status(request)


@router.post("/block-headers", summary="Store a remote chain block header")
@rate_limit(rate=20, per=60)
async def store_block_header_route(request: Request, header_data: BlockHeaderRequest) -> dict[str, Any]:
    """Store a remote chain block header for bridge proof verification (v0.7.2)"""
    if store_block_header is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await store_block_header(request, header_data.model_dump(exclude_none=True))


@router.get("/block-headers/{chain_id}/{height}", summary="Get a block header with finality status")
@rate_limit(rate=100, per=60)
async def get_block_header_route(request: Request, chain_id: str, height: int) -> dict[str, Any]:
    """Get a stored block header with finality status (v0.7.2)"""
    if get_block_header is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await get_block_header(request, chain_id, height)


@router.get("/oracle/status", summary="Bridge oracle/verification status")
@rate_limit(rate=100, per=60)
async def bridge_oracle_status_route(request: Request) -> dict[str, Any]:
    """Get bridge oracle/verification status (v0.7.2)"""
    if bridge_oracle_status is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return await bridge_oracle_status(request)
