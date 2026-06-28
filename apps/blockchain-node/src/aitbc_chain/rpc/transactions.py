"""
Transaction-related RPC endpoints.
"""

from typing import Any

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlmodel import select

from aitbc.rate_limiting import rate_limit

from ..database import session_scope
from ..logger import get_logger
from ..models import Account, Transaction
from .utils import get_chain_id, normalize_transaction_data, verify_transaction_signature

_logger = get_logger(__name__)


class TransactionRequest(BaseModel):
    """Transaction request model"""

    chain_id: str | None = None
    sender: str = Field(..., alias="from")
    recipient: str = Field(..., alias="to")
    amount: int
    fee: int = 36
    nonce: int = 0
    type: str = "TRANSFER"
    payload: dict[str, Any] = Field(default_factory=dict)
    sig: str = Field(..., alias="signature")

    @model_validator(mode="before")
    @classmethod
    def validate_payload(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Ensure payload contains recipient and amount"""
        payload = values.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        # Set recipient/to in payload if not present
        if "to" not in payload and "recipient" in values:
            payload["to"] = values["recipient"]
        if "amount" not in payload and "amount" in values:
            payload["amount"] = values["amount"]

        values["payload"] = payload
        return values


def _validate_transaction_admission(tx_data: dict[str, Any], mempool: Any) -> None:
    """Validate transaction can be admitted to mempool"""
    from ..mempool import compute_tx_hash

    chain_id = tx_data["chain_id"]
    from .utils import get_supported_chains

    supported_chains = get_supported_chains()
    if not chain_id:
        raise ValueError("transaction.chain_id is required")
    if supported_chains and chain_id not in supported_chains:
        raise ValueError(f"unsupported chain_id '{chain_id}'. Supported chains: {supported_chains}")

    compute_tx_hash(tx_data)

    with session_scope() as session:
        sender_account = session.get(Account, (chain_id, tx_data["from"]))
        if sender_account is None:
            raise ValueError(f"sender account not found on chain '{chain_id}'")

        total_cost = tx_data["amount"] + tx_data["fee"]
        if sender_account.balance < total_cost:
            raise ValueError(
                f"insufficient balance for sender '{tx_data['from']}' on chain '{chain_id}': has {sender_account.balance}, needs {total_cost}"
            )

        if tx_data["nonce"] != sender_account.nonce:
            raise ValueError(
                f"invalid nonce for sender '{tx_data['from']}' on chain '{chain_id}': expected {sender_account.nonce}, got {tx_data['nonce']}"
            )


@rate_limit(rate=50, per=60)
async def submit_transaction(request: Request, tx_data: TransactionRequest) -> dict[str, Any]:
    """Submit a new transaction to the mempool"""
    from ..mempool import get_mempool

    try:
        mempool = get_mempool()
        chain_id = get_chain_id(tx_data.chain_id)

        # Convert TransactionRequest to dict for normalization
        # Use validated top-level fields instead of reading from payload
        # chain_id is included so the signature verifier covers it (v0.5.17 B4:
        # prevents cross-chain replay — a tx signed for chain A cannot be
        # replayed on chain B because the signed message differs).
        tx_data_dict = {
            "from": tx_data.sender,
            "to": tx_data.recipient,
            "amount": tx_data.amount,
            "fee": tx_data.fee,
            "nonce": tx_data.nonce,
            "payload": tx_data.payload,
            "type": tx_data.type,
            "chain_id": chain_id,
            "signature": tx_data.sig,
        }

        # Verify transaction signature (Bug 4: signature was never verified)
        if not verify_transaction_signature(tx_data_dict, tx_data.sig, tx_data.sender):
            raise HTTPException(status_code=403, detail="Invalid transaction signature")

        tx_data_dict = normalize_transaction_data(tx_data_dict, chain_id)
        _validate_transaction_admission(tx_data_dict, mempool)

        tx_hash = mempool.add(tx_data_dict, chain_id=chain_id)

        return {"success": True, "transaction_hash": tx_hash, "message": "Transaction submitted to mempool"}
    except Exception as e:
        _logger.error("Failed to submit transaction", extra={"error": str(e)})
        raise HTTPException(status_code=400, detail=f"Failed to submit transaction: {str(e)}") from e


@rate_limit(rate=200, per=60)
async def get_mempool(request: Request, chain_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Get pending transactions from mempool"""
    from ..mempool import get_mempool

    try:
        mempool = get_mempool()
        chain_id_arg = chain_id if chain_id else ""
        pending_txs = mempool.get_pending_transactions(chain_id=chain_id_arg, limit=limit)

        return {"success": True, "transactions": pending_txs, "count": len(pending_txs)}
    except Exception as e:
        _logger.error("Failed to get mempool", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get mempool: {str(e)}"
        ) from e


@rate_limit(rate=50, per=60)
async def submit_marketplace_transaction(request: Request, tx_data: dict[str, Any]) -> dict[str, Any]:
    """Submit a marketplace transaction"""
    from ..mempool import get_mempool

    try:
        mempool = get_mempool()
        chain_id_arg = tx_data.get("chain_id") or ""
        chain_id = get_chain_id(chain_id_arg)

        # Normalize transaction data
        tx_data_dict = normalize_transaction_data(tx_data, chain_id)

        # For GPU registration, use GPU_REGISTER transaction type
        if tx_data_dict.get("type") == "GPU_REGISTER":
            tx_data_dict["type"] = "GPU_REGISTER"
            # GPU registration doesn't require amount transfer, only fee
            tx_data_dict["amount"] = 0
        else:
            _validate_transaction_admission(tx_data_dict, mempool)

        tx_hash = mempool.add(tx_data_dict, chain_id=chain_id)

        return {"success": True, "transaction_hash": tx_hash, "message": "Marketplace transaction submitted to mempool"}
    except Exception as e:
        _logger.error("Failed to submit marketplace transaction", extra={"error": str(e)})
        raise HTTPException(status_code=400, detail=f"Failed to submit marketplace transaction: {str(e)}") from e


@rate_limit(rate=200, per=60)
async def query_transactions(
    request: Request,
    transaction_type: str | None = None,
    island_id: str | None = None,
    pair: str | None = None,
    status: str | None = None,
    order_id: str | None = None,
    limit: int | None = 100,
    chain_id: str | None = None,
) -> list[dict[str, Any]]:
    """Query transactions with optional filters"""
    chain_id_arg = chain_id if chain_id else ""
    resolved_chain_id = get_chain_id(chain_id_arg)

    _logger.info(f"Query transactions - chain_id_arg: {chain_id_arg}, resolved_chain_id: {resolved_chain_id}")

    with session_scope() as session:
        query = select(Transaction).where(Transaction.chain_id == resolved_chain_id)

        _logger.info(f"Query: {query}")

        # Apply filters based on payload fields
        transactions = session.exec(query).all()

        _logger.info(f"Found {len(transactions)} transactions for chain {resolved_chain_id}")

        results = []
        for tx in transactions:
            # Filter by transaction type in transaction type field (not payload)
            if transaction_type and tx.type != transaction_type:
                continue

            # Filter by island_id in payload
            if island_id and tx.payload.get("island_id") != island_id:
                continue

            # Filter by pair in payload
            if pair and tx.payload.get("pair") != pair:
                continue

            # Filter by status in payload
            if status and tx.payload.get("status") != status:
                continue

            # Filter by order_id in payload
            if (
                order_id
                and tx.payload.get("order_id") != order_id
                and tx.payload.get("offer_id") != order_id
                and tx.payload.get("bid_id") != order_id
            ):
                continue

            results.append(
                {
                    "transaction_id": tx.id,
                    "tx_hash": tx.tx_hash,
                    "sender": tx.sender,
                    "recipient": tx.recipient,
                    "payload": tx.payload,
                    "type": tx.type,
                    "status": tx.status,
                    "created_at": tx.created_at.isoformat(),
                    "timestamp": tx.timestamp,
                    "nonce": tx.nonce,
                    "value": tx.value,
                    "fee": tx.fee,
                }
            )

        # Apply limit
        if limit:
            results = results[:limit]

        _logger.info(f"Returning {len(results)} transactions after filtering")

        return results
