"""Coin request execution endpoint.

Ported from the Hermes service in v0.5.9 §2. This is a hub-only endpoint
that executes an approved coin request by signing and submitting a
blockchain transaction from the genesis wallet.

Authority note (V23-62): the stored request is the authority for *what* gets paid.
The API key answers "may this caller ask the hub to execute something", which is a
much weaker question than "may this payment happen"; it is a shared secret held by
every island operator, so on its own it authorises an arbitrary treasury transfer.
The amount and destination therefore come from the row, never from the request body,
and a request that the hub has not itself recorded as approved is refused rather
than paid on the caller's word.
"""

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from aitbc.aitbc_logging import get_logger
from aitbc.crypto import TransactionService
from aitbc.db import get_db_session
from aitbc.models import CoinRequest, CoinRequestStatus

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/agent/coin-requests", tags=["coin-requests"])

# Canonical blockchain fee (matches RPC default, v0.5.8 fee fix)
TRANSACTION_FEE = 10

# Written to transaction_hash to claim a request before signing, so two concurrent
# calls cannot both pass the "not yet executed" check and pay twice. Recognisable on
# sight: if a crash strands a row mid-execution an operator can find it, reconcile
# against the chain and clear it by hand. It is deliberately not a valid hash, so
# nothing downstream can mistake it for a settled payment.
EXECUTION_CLAIM_PREFIX = "claiming:"


class RemoteExecuteRequest(BaseModel):
    """Request to execute an approved coin request forwarded from a follower node.

    Only ``request_id`` is used. The other fields are accepted for wire compatibility
    with deployed CLIs and logged when they disagree with the stored request, but they
    do not influence the payment — see the module docstring.
    """

    request_id: str
    sender: str | None = None
    amount: int | None = None
    wallet_address: str | None = None
    approved_by: str = "cli"


def _warn_on_mismatch(req: RemoteExecuteRequest, stored_amount: int, stored_address: str) -> None:
    """Log a body that disagrees with the stored request; it is ignored either way."""
    if req.amount is not None and req.amount != stored_amount:
        logger.warning(
            "Execute request %s asked for amount %s but the approved request is %s — using the approved amount",
            req.request_id,
            req.amount,
            stored_amount,
        )
    if req.wallet_address is not None and req.wallet_address != stored_address:
        logger.warning(
            "Execute request %s named destination %s but the approved request pays %s — using the approved destination",
            req.request_id,
            req.wallet_address,
            stored_address,
        )


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

    with get_db_session() as session:
        stored = session.query(CoinRequest).filter(CoinRequest.id == req.request_id).first()
        if stored is None:
            logger.warning("Execute refused: request %s is not known to this hub", req.request_id)
            raise HTTPException(status_code=404, detail=f"Coin request {req.request_id} not found")

        status = stored.status
        amount = int(stored.amount or 0)
        recipient = str(stored.wallet_address)
        existing_hash = stored.transaction_hash

    # A retry after a lost response must not pay again. Report the original outcome so
    # the caller can reconcile instead of being left unsure whether the first call landed.
    if existing_hash:
        if str(existing_hash).startswith(EXECUTION_CLAIM_PREFIX):
            raise HTTPException(
                status_code=409,
                detail=f"Coin request {req.request_id} is already being executed",
            )
        logger.info("Execute request %s replayed; returning the original transaction", req.request_id)
        return {
            "success": True,
            "already_executed": True,
            "request_id": req.request_id,
            "tx_hash": existing_hash,
            "amount": amount,
            "recipient": recipient,
        }

    if status != CoinRequestStatus.APPROVED:
        status_name = status.value if status is not None else "unknown"
        logger.warning("Execute refused: request %s has status %s", req.request_id, status_name)
        raise HTTPException(
            status_code=409,
            detail=f"Coin request {req.request_id} is not approved (status: {status_name})",
        )

    _warn_on_mismatch(req, amount, recipient)

    tx_service = TransactionService()
    if not tx_service.genesis_private_key:
        raise HTTPException(status_code=503, detail="GENESIS_PRIVATE_KEY not configured on this node")
    if not tx_service.genesis_address:
        raise HTTPException(status_code=503, detail="GENESIS_ADDRESS not configured on this node")

    balance = tx_service.get_balance(tx_service.genesis_address)
    total_required = amount + TRANSACTION_FEE
    if balance < total_required:
        raise HTTPException(status_code=400, detail=f"Insufficient genesis balance: {balance} < {total_required}")

    # Claim the request before signing anything. The WHERE clause is the guard: whichever
    # concurrent call updates a row wins, the other sees rowcount 0 and stops.
    claim = f"{EXECUTION_CLAIM_PREFIX}{datetime.now(UTC).isoformat()}"
    with get_db_session() as session:
        claimed = (
            session.query(CoinRequest)
            .filter(CoinRequest.id == req.request_id, CoinRequest.transaction_hash.is_(None))
            .update({"transaction_hash": claim}, synchronize_session=False)
        )
    if not claimed:
        logger.warning("Execute refused: request %s was claimed by a concurrent call", req.request_id)
        raise HTTPException(status_code=409, detail=f"Coin request {req.request_id} is already being executed")

    try:
        signed_tx = tx_service.generate_signed_transaction(to_address=recipient, amount=amount, fee=TRANSACTION_FEE)
        if not signed_tx:
            raise HTTPException(status_code=500, detail="Failed to generate signed transaction")

        from aitbc.network import AITBCHTTPClient

        http_client = AITBCHTTPClient(base_url=tx_service.rpc_url, timeout=30)
        result = http_client.post("/rpc/transaction", json=signed_tx)
        tx_hash = result.get("transaction_hash")
        if not tx_hash:
            raise HTTPException(status_code=502, detail="Blockchain did not return a transaction hash")
    except HTTPException:
        _release_claim(req.request_id, claim)
        raise
    except Exception as e:
        logger.exception("Unhandled exception")
        _release_claim(req.request_id, claim)

        raise HTTPException(status_code=502, detail="Internal server error") from e

    with get_db_session() as session:
        session.query(CoinRequest).filter(CoinRequest.id == req.request_id, CoinRequest.transaction_hash == claim).update(
            {"transaction_hash": tx_hash}, synchronize_session=False
        )
        settled = session.query(CoinRequest).filter(CoinRequest.id == req.request_id).first()
        if settled is not None:
            entry = f" | Executed by hub at {datetime.now(UTC).isoformat()} | Hash: {tx_hash}"
            settled.audit_log = (settled.audit_log or "") + entry

    logger.info(
        "Remote execution of %s: %s AIT to %s — tx %s",
        req.request_id,
        amount,
        recipient,
        tx_hash,
    )
    return {
        "success": True,
        "already_executed": False,
        "request_id": req.request_id,
        "tx_hash": tx_hash,
        "amount": amount,
        "recipient": recipient,
    }


def _release_claim(request_id: str, claim: str) -> None:
    """Undo a claim when the payment did not happen, so the request stays executable.

    Only ever clears the exact claim this call wrote, so a retry that has since taken
    the row is left alone. Best effort: if it fails the request is stranded rather than
    paid twice, which is the direction to fail in.
    """
    try:
        with get_db_session() as session:
            session.query(CoinRequest).filter(CoinRequest.id == request_id, CoinRequest.transaction_hash == claim).update(
                {"transaction_hash": None}, synchronize_session=False
            )
    except Exception:
        logger.exception("Could not release execution claim on %s; clear %s by hand to retry", request_id, claim)
