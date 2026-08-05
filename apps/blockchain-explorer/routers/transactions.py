"""Transaction routes — transaction by hash, transaction search, transaction details."""

import json
from pathlib import Path
from typing import Any

import aiosqlite
import httpx
from fastapi import APIRouter

from aitbc.aitbc_logging import get_logger
from aitbc.utils import format_ait

from chain_client import BLOCKCHAIN_RPC_URLS, DEFAULT_CHAIN, get_transaction
from .common import like_pattern
from validation import validate_tx_hash

logger = get_logger(__name__)

router = APIRouter()


@router.get("/api/transactions/by-hash/{hash}")
async def api_transaction_by_hash(hash: str, chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """API endpoint for transaction by hash"""
    if not validate_tx_hash(hash):
        return {}
    # Strip 0x prefix for comparison
    clean_hash = hash[2:] if hash.startswith("0x") else hash
    try:
        # First try blockchain database for direct lookup
        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if chain_db_path.exists():
            async with aiosqlite.connect(str(chain_db_path)) as conn:
                cursor = await conn.cursor()

                # Search for transaction by hash (case-insensitive, with or without 0x prefix)
                await cursor.execute(
                    """
                    SELECT tx_hash, sender, recipient, payload, block_height, created_at, type, status
                    FROM "transaction"
                    WHERE lower(replace(tx_hash, '0x', '')) = ?
                """,
                    (clean_hash.lower(),),
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
        rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id or DEFAULT_CHAIN, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{rpc_url}/rpc/tx/{hash}", params={"chain_id": chain_id or DEFAULT_CHAIN})
            if response.status_code == 200:
                return response.json()  # type: ignore[no-any-return]

        return {}
    except Exception:
        logger.exception("Error getting transaction by hash %s", hash)
        return {}


@router.get("/api/transactions/search")
async def api_search_transactions(
    address: str,
    chain_id: str | None = DEFAULT_CHAIN,
    limit: int = 100,
) -> dict[str, Any]:
    """Search transactions by address or node ID in blockchain database"""
    try:
        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if chain_db_path.exists():
            async with aiosqlite.connect(str(chain_db_path)) as conn:
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
                    LIMIT ?
                """,
                    (search_term, search_term, search_term, limit),
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
async def api_transaction(tx_hash: str, chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """API endpoint for transaction data, normalized for frontend"""
    tx = await get_transaction(tx_hash, chain_id if chain_id else DEFAULT_CHAIN)
    if not tx:
        return {}
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
