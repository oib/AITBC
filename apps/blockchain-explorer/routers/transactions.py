"""Transaction routes — transaction by hash, transaction search, transaction details."""

import json
from typing import Any

import aiosqlite
import httpx
from fastapi import APIRouter, HTTPException

from aitbc.aitbc_logging import get_logger
from aitbc.utils import format_ait

from chain_client import chain_db_path, default_chain_id, get_transaction, rpc_url_for
from .common import like_pattern
from validation import check_page_offset, clamp_page_limit, validate_tx_hash

logger = get_logger(__name__)

router = APIRouter()


@router.get("/api/transactions/by-hash/{hash}")
async def api_transaction_by_hash(hash: str, chain_id: str | None = None) -> dict[str, Any]:
    """API endpoint for transaction by hash"""
    if not validate_tx_hash(hash):
        raise HTTPException(status_code=400, detail="Invalid transaction hash")
    # Strip 0x prefix for comparison
    clean_hash = hash[2:] if hash.startswith("0x") else hash
    try:
        # First try blockchain database for direct lookup
        db_path = chain_db_path()

        if db_path is not None:
            async with aiosqlite.connect(str(db_path)) as conn:
                cursor = await conn.cursor()

                # Canonical storage is 0x-prefixed lowercase hex
                # (mempool.compute_tx_hash), so exact-match candidates hit the
                # tx_hash index. The legacy case-insensitive scan stays as a
                # fallback for any non-canonical row (PI-EX-001).
                bare_hash = clean_hash.lower()
                await cursor.execute(
                    """
                    SELECT tx_hash, sender, recipient, payload, block_height, created_at, type, status
                    FROM "transaction"
                    WHERE tx_hash IN (?, ?)
                """,
                    (f"0x{bare_hash}", bare_hash),
                )

                result = await cursor.fetchone()
                if result is None:
                    await cursor.execute(
                        """
                        SELECT tx_hash, sender, recipient, payload, block_height, created_at, type, status
                        FROM "transaction"
                        WHERE lower(replace(tx_hash, '0x', '')) = ?
                    """,
                        (bare_hash,),
                    )
                    result = await cursor.fetchone()

            if result:
                tx_hash, sender, recipient, payload, block_height, created_at, tx_type, status = result
                return {
                    "tx_hash": tx_hash,
                    "sender": sender,
                    "recipient": recipient,
                    "payload": payload,
                    "block_height": block_height,
                    "created_at": created_at,
                    "type": tx_type,
                    "status": status,
                }

        # Fallback to RPC method
        chain_id = chain_id or default_chain_id()
        rpc_url = rpc_url_for(chain_id)
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{rpc_url}/rpc/tx/{hash}", params={"chain_id": chain_id})
            if response.status_code == 200:
                return response.json()  # type: ignore[no-any-return]

        raise HTTPException(status_code=404, detail="Transaction not found")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting transaction by hash %s", hash)
        return {}


@router.get("/api/transactions/search")
async def api_search_transactions(
    address: str,
    chain_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Search transactions by address or node ID in blockchain database"""
    limit = clamp_page_limit(limit)
    offset = check_page_offset(offset)
    try:
        db_path = chain_db_path()

        if db_path is not None:
            async with aiosqlite.connect(str(db_path)) as conn:
                cursor = await conn.cursor()

                # Search for transactions where sender, recipient, or payload contains the address
                # Using LIKE for partial matching (payload contains node IDs like provider_node_id)
                search_term = like_pattern(address)
                await cursor.execute(
                    """
                    SELECT tx_hash, sender, recipient, payload, block_height, created_at, type, status
                    FROM "transaction"
                    WHERE sender LIKE ? ESCAPE '|'
                       OR recipient LIKE ? ESCAPE '|'
                       OR payload LIKE ? ESCAPE '|'
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """,
                    (search_term, search_term, search_term, limit, offset),
                )

                transactions = []
                rows = await cursor.fetchall()
                for row in rows:
                    tx_hash, sender, recipient, payload, block_height, created_at, tx_type, status = row
                    transactions.append(
                        {
                            "tx_hash": tx_hash,
                            "sender": sender,
                            "recipient": recipient,
                            "payload": payload,
                            "block_height": block_height,
                            "created_at": created_at,
                            "type": tx_type,
                            "status": status,
                        }
                    )

            return {"transactions": transactions}

        return {"transactions": []}
    except Exception:
        logger.exception("Error searching transactions for address %s", address)
        return {"transactions": []}


@router.get("/api/transactions/{tx_hash}")
async def api_transaction(tx_hash: str, chain_id: str | None = None) -> dict[str, Any]:
    """API endpoint for transaction data, normalized for frontend"""
    tx = await get_transaction(tx_hash, chain_id if chain_id else default_chain_id())
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    # Try to parse payload for additional fields
    payload_data = {}
    try:
        raw_payload = tx.get("payload", "{}")
        if isinstance(raw_payload, str) and raw_payload.strip():
            payload_data = json.loads(raw_payload)
        elif isinstance(raw_payload, dict):
            payload_data = raw_payload
    except Exception:
        pass
    value = tx.get("value") if tx.get("value") is not None else payload_data.get("amount", 0)
    fee = tx.get("fee") if tx.get("fee") is not None else payload_data.get("fee", 0)
    return {
        "hash": tx.get("tx_hash"),
        "tx_hash": tx.get("tx_hash"),
        "block_height": tx.get("block_height"),
        "from": tx.get("sender"),
        "sender": tx.get("sender"),
        "to": tx.get("recipient"),
        "recipient": tx.get("recipient"),
        "type": tx.get("type") or payload_data.get("type", "transfer"),
        "status": tx.get("status", "confirmed"),
        "value": value,
        "amount": value,
        "amount_ait": format_ait(value) if value else "0 AIT",
        "fee": fee,
        "fee_ait": format_ait(fee) if fee else "0 AIT",
        "nonce": tx.get("nonce", 0),
        "created_at": tx.get("created_at"),
        "timestamp": tx.get("created_at"),
        "payload": tx.get("payload"),
    }
