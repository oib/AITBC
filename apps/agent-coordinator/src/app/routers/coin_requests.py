"""Coin request execution endpoint.

Ported from the Hermes service in v0.5.9 §2. This is a hub-only endpoint
that executes an approved coin request by signing and submitting a
blockchain transaction from the genesis wallet.
"""

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from aitbc.aitbc_logging import get_logger
from aitbc.crypto import TransactionService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/agent/coin-requests", tags=["coin-requests"])

# Canonical blockchain fee (matches RPC default, v0.5.8 fee fix)
TRANSACTION_FEE = 10


class RemoteExecuteRequest(BaseModel):
    """Request to execute an approved coin request forwarded from a follower node."""

    request_id: str
    sender: str
    amount: int
    wallet_address: str
    approved_by: str = "cli"


@router.post("/execute")
async def remote_execute_coin_request(
    req: RemoteExecuteRequest, x_api_key: str | None = Header(default=None)
) -> dict[str, Any]:
    """
    Execute an approved coin request forwarded from a follower node.
    Hub-only endpoint — requires COORDINATOR_API_KEY authentication.
    Signs and submits the transaction using the genesis wallet.
    """
    expected_key = os.getenv("COORDINATOR_API_KEY") or os.getenv("SECRET_KEY")
    if not expected_key or x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    tx_service = TransactionService()
    if not tx_service.genesis_private_key:
        raise HTTPException(status_code=503, detail="GENESIS_PRIVATE_KEY not configured on this node")

    balance = tx_service.get_balance(tx_service.genesis_address)
    total_required = req.amount + TRANSACTION_FEE
    if balance < total_required:
        raise HTTPException(status_code=400, detail=f"Insufficient genesis balance: {balance} < {total_required}")

    signed_tx = tx_service.generate_signed_transaction(to_address=req.wallet_address, amount=req.amount, fee=TRANSACTION_FEE)
    if not signed_tx:
        raise HTTPException(status_code=500, detail="Failed to generate signed transaction")

    try:
        from aitbc.network import AITBCHTTPClient

        http_client = AITBCHTTPClient(base_url=tx_service.rpc_url, timeout=30)
        result = http_client.post("/rpc/transaction", json=signed_tx)
        tx_hash = result.get("transaction_hash")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Blockchain RPC error: {e}") from e

    logger.info(
        "Remote execution of %s: %s AIT to %s — tx %s",
        req.request_id,
        req.amount,
        req.wallet_address,
        tx_hash,
    )
    return {
        "success": True,
        "request_id": req.request_id,
        "tx_hash": tx_hash,
        "amount": req.amount,
        "recipient": req.wallet_address,
    }
