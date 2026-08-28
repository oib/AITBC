"""
Transaction-related RPC endpoints.
"""

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlmodel import col, select
from sqlalchemy import literal_column

from aitbc.rate_limiting import rate_limit

from ..base_models import Bond, _to_ait_address
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


# Kept in step with migration b7f3c1a90d24, which builds ix_transaction_payload_job_id
# on exactly these expressions. If either side changes, the planner silently stops using
# the index -- verify with EXPLAIN QUERY PLAN, which should report SEARCH, not SCAN.
_JOB_ID_INDEX_EXPRESSIONS = {
    "sqlite": """json_extract(payload, '$."job_id"')""",
    "postgresql": """(payload ->> 'job_id')""",
}


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
        _logger.error("Failed to submit transaction: %s", e)
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
        _logger.exception("Failed to get mempool")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e


def _market_bond_min_amount() -> int:
    return int(os.getenv("MARKET_BOND_MIN_AMOUNT", "0"))


def _has_active_bond(session, chain_id: str, provider: str, min_amount: int) -> bool:
    if min_amount <= 0:
        return True
    now = datetime.now(UTC)
    bond = session.exec(
        select(Bond).where(
            Bond.chain_id == chain_id,
            Bond.provider == _to_ait_address(provider),
            Bond.status == "active",
            Bond.amount >= min_amount,
        )
    ).first()
    if not bond:
        return False
    if bond.locked_until:
        locked_until = bond.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        if now > locked_until:
            return False
    return True


@rate_limit(rate=50, per=60)
async def submit_marketplace_transaction(request: Request, tx_data: dict[str, Any]) -> dict[str, Any]:
    """Submit a marketplace transaction"""
    from ..mempool import get_mempool

    try:
        mempool = get_mempool()
        chain_id_arg = tx_data.get("chain_id") or ""
        chain_id = get_chain_id(chain_id_arg)

        # Verify transaction signature before normalization
        signature = tx_data.get("signature") or tx_data.get("sig")
        sender = tx_data.get("from")
        payload = tx_data.get("payload") or {}
        is_offer = tx_data.get("type") == "GPU_MARKETPLACE" and payload.get("action") in ("offer", "software_offer")
        is_hardware_offer = is_offer and payload.get("action") == "offer"
        if is_offer:
            # GPU/software offers are value-zero listings; they are still traceable to sender
            # by the public key / address, but requiring a secp256k1 signature here would break
            # the marketplace CLI which does not manage wallet private keys (V23-90).
            if not sender:
                raise HTTPException(status_code=400, detail="Sender required")
            # P2.5: software service offers (Whisper, FFmpeg, Ollama) do not require a prior
            # on-chain bond to list; hardware bundle offers still do if the bond minimum is set.
            if is_hardware_offer:
                min_bond = _market_bond_min_amount()
                if min_bond > 0:
                    with session_scope(chain_id) as session:
                        if not _has_active_bond(session, chain_id, sender, min_bond):
                            raise HTTPException(
                                status_code=403,
                                detail=f"Active bond of at least {min_bond} compute-seconds required to list",
                            )
            tx_for_verify = {k: v for k, v in tx_data.items() if k not in ("signature", "sig")}
        else:
            if not signature:
                raise HTTPException(status_code=403, detail="Signature required")
            if not sender:
                raise HTTPException(status_code=400, detail="Sender required")
            tx_for_verify = {k: v for k, v in tx_data.items() if k not in ("signature", "sig")}
            tx_for_verify["signature"] = signature
            if not verify_transaction_signature(tx_for_verify, signature, sender):
                raise HTTPException(status_code=403, detail="Invalid transaction signature")

        # Normalize transaction data
        tx_data_dict = normalize_transaction_data(tx_for_verify, chain_id)

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
        _logger.error("Failed to submit marketplace transaction: %s", e)
        raise HTTPException(status_code=400, detail=f"Failed to submit marketplace transaction: {str(e)}") from e


@rate_limit(rate=10, per=60)
async def match_marketplace(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Return active marketplace listings that could be matched against bids."""
    chain_id = get_chain_id(chain_id)
    with session_scope(chain_id) as session:
        offers = session.exec(
            select(Transaction)
            .where(Transaction.chain_id == chain_id)
            .where(Transaction.type == "GPU_MARKETPLACE")
            .where(Transaction.status == "confirmed")
        ).all()
        cancelled_ids: set[str] = set()
        for tx in offers:
            payload = tx.payload or {}
            action = payload.get("action", "")
            if action in ("cancel", "cancelled") or str(payload.get("status", "")).lower() == "cancelled":
                order_id = payload.get("order_id", "")
                if order_id:
                    cancelled_ids.add(str(order_id))
                order_ids = payload.get("order_ids") or []
                if not isinstance(order_ids, list):
                    order_ids = [order_ids]
                cancelled_ids.update(str(oid) for oid in order_ids)
                cancelled_ids.add(str(tx.tx_hash))
        matches = [
            {
                "offer_tx_hash": tx.tx_hash,
                "seller": tx.sender,
                "description": (tx.payload or {}).get("description", ""),
                "service_type": (tx.payload or {}).get("service_type", ""),
                "model": (tx.payload or {}).get("model", ""),
                "price": (tx.payload or {}).get("price", 0),
                "price_unit": (tx.payload or {}).get("price_unit", ""),
                "gpu_name": (tx.payload or {}).get("gpu_name", ""),
                "gpu_device": (tx.payload or {}).get("gpu_device", ""),
                "gpu_uuid": (tx.payload or {}).get("gpu_uuid", ""),
                "gpu_model": (tx.payload or {}).get("gpu_model") or (tx.payload or {}).get("gpu_name", ""),
                "memory_gb": (tx.payload or {}).get("memory_gb"),
                "compute_capability": (tx.payload or {}).get("compute_capability", ""),
            }
            for tx in offers
            if (tx.payload or {}).get("action") not in ("cancel", "cancelled")
            and str((tx.payload or {}).get("status", "")).lower() != "cancelled"
            and str(tx.tx_hash) not in cancelled_ids
        ]
        return {
            "chain_id": chain_id,
            "matches": matches,
            "total": len(matches),
        }


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
    address: str | None = None,
    job_id: str | None = None,
) -> list[dict[str, Any]]:
    """Query transactions with optional filters"""
    resolved_chain_id = get_chain_id(chain_id)

    _logger.info(f"Query transactions - resolved_chain_id: {resolved_chain_id}")

    with session_scope() as session:
        # Newest first. `limit` is applied after the payload filters below, so with the
        # natural (ascending id) order a bounded query returned the OLDEST rows and
        # silently omitted recent ones -- a caller asking for "the last 40 releases" got
        # the first 40 instead. Settlement depended on that answer to decide whether a job
        # had already been paid.
        query = (
            select(Transaction).where(Transaction.chain_id == resolved_chain_id).order_by(Transaction.id.desc())  # type: ignore[union-attr]
        )
        if address:
            from ..base_models import address_spellings

            spellings = address_spellings(address)
            query = query.where(col(Transaction.sender).in_(spellings) | col(Transaction.recipient).in_(spellings))

        if job_id is not None:
            # Filter in SQL, not in Python: the other payload filters below load every
            # transaction on the chain first. Settlement asks this question before paying
            # a provider, so it has to stay cheap.
            #
            # The JSON *path* is inlined rather than bound. SQLModel's
            # `payload["job_id"].as_string()` binds the path as a parameter, and neither
            # SQLite nor Postgres can match a parameterised path against an expression
            # index built on a literal one -- the plan degrades to a full scan. The
            # searched value stays bound; only the fixed path is inline.
            expression = _JOB_ID_INDEX_EXPRESSIONS.get(session.get_bind().dialect.name)
            if expression is not None:
                query = query.where(literal_column(expression) == job_id)
            else:
                query = query.where(Transaction.payload["job_id"].as_string() == job_id)

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

        # Apply limit (results are newest-first, so this keeps the most recent rows)
        if limit:
            results = results[:limit]

        _logger.info(f"Returning {len(results)} transactions after filtering")

        return results


@rate_limit(rate=200, per=60)
async def get_transaction(request: Request, tx_hash: str, chain_id: str | None = None) -> dict[str, Any]:
    """Look up one transaction by hash (V23-66).

    The chain could describe its transactions in bulk but could not answer "do you have
    this one", so nothing outside it could check a hash it had recorded. That matters for
    any record kept beside the chain rather than in it — the coin-request database stores
    a `transaction_hash` against every executed request, and a chain reset leaves those
    hashes pointing at transactions that no longer exist, with no way to find out.
    """
    # `get_chain_id` falls back to this node's own chain only for None — an empty string is
    # returned as-is, and `chain_id == ""` matches no transaction, so an omitted parameter
    # 404'd every hash on the chain until this said `or None`.
    resolved_chain_id = get_chain_id(chain_id or None)
    with session_scope() as session:
        tx = session.exec(
            select(Transaction).where(Transaction.chain_id == resolved_chain_id, Transaction.tx_hash == tx_hash)
        ).first()
        if tx is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Transaction {tx_hash} not found")
        return {
            "transaction_id": tx.id,
            "tx_hash": tx.tx_hash,
            "chain_id": tx.chain_id,
            "block_height": tx.block_height,
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
