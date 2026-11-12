"""Transaction routes — transaction by hash, transaction search, transaction details."""

import json
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from aitbc.aitbc_logging import get_logger
from aitbc.utils import format_ait

from chain_client import (
    chain_db_connect,
    chain_db_path,
    chain_scope,
    default_chain_id,
    get_transaction,
    rpc_url_for,
    scoped_where,
)
from .common import like_pattern
from validation import check_page_offset, check_tx_keyset_cursor, clamp_page_limit, validate_tx_hash

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
        cid = chain_id or default_chain_id()
        # First try blockchain database for direct lookup
        db_path = chain_db_path()

        if db_path is not None:
            async with chain_db_connect(db_path) as conn:
                cursor = await conn.cursor()

                # Canonical storage is 0x-prefixed lowercase hex
                # (mempool.compute_tx_hash), so exact-match candidates hit the
                # tx_hash index. The legacy case-insensitive scan stays as a
                # fallback for any non-canonical row (PI-EX-001). Both reads
                # are chain-scoped: the fallback chain.db is multi-chain (#1620).
                scope_sql, scope_params = await chain_scope(conn, "transaction", cid)
                bare_hash = clean_hash.lower()
                where, params = scoped_where("tx_hash IN (?, ?)", scope_sql, [f"0x{bare_hash}", bare_hash], scope_params)
                await cursor.execute(
                    f"""
                    SELECT tx_hash, sender, recipient, payload, block_height, created_at, type, status
                    FROM "transaction"
                    WHERE {where}
                """,  # nosec B608 - WHERE fragments are internally generated clause strings; all values are bound parameters
                    params,
                )

                result = await cursor.fetchone()
                if result is None:
                    legacy_where, legacy_params = scoped_where(
                        "lower(replace(tx_hash, '0x', '')) = ?", scope_sql, [bare_hash], scope_params
                    )
                    await cursor.execute(
                        f"""
                        SELECT tx_hash, sender, recipient, payload, block_height, created_at, type, status
                        FROM "transaction"
                        WHERE {legacy_where}
                    """,  # nosec B608 - WHERE fragments are internally generated clause strings; all values are bound parameters
                        legacy_params,
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
        rpc_url = rpc_url_for(cid)
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{rpc_url}/rpc/tx/{hash}", params={"chain_id": cid})
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
    cursor: str | None = None,
) -> dict[str, Any]:
    """Search transactions by address or node ID in blockchain database.
    ``cursor`` takes a previous ``next_cursor`` for keyset pagination (#1717)."""
    limit = clamp_page_limit(limit)
    offset = check_page_offset(offset)
    keyset = check_tx_keyset_cursor(cursor)
    try:
        cid = chain_id or default_chain_id()
        db_path = chain_db_path()

        if db_path is not None:
            async with chain_db_connect(db_path) as conn:
                db_cursor = await conn.cursor()

                # Search for transactions where sender, recipient, or payload contains the address
                # Using LIKE for partial matching (payload contains node IDs like provider_node_id)
                scope_sql, scope_params = await chain_scope(conn, "transaction", cid)
                search_term = like_pattern(address)
                # The keyset predicate rides in the same base fragment so
                # scope params keep their positions; created_at is echoed
                # verbatim so the TEXT comparison matches ORDER BY (#1717).
                base_where = "(sender LIKE ? ESCAPE '|' OR recipient LIKE ? ESCAPE '|' OR payload LIKE ? ESCAPE '|')"
                base_params: list[Any] = [search_term, search_term, search_term]
                if keyset is not None:
                    base_where += " AND ((created_at < ?) OR (created_at = ? AND tx_hash < ?))"
                    base_params += [keyset[0], keyset[0], keyset[1]]
                where, params = scoped_where(base_where, scope_sql, base_params, scope_params)
                # scope params precede the LIMIT/OFFSET placeholders; one
                # extra row proves a next page exists before next_cursor.
                params = [*params, limit + 1, offset]
                await db_cursor.execute(
                    f"""
                    SELECT tx_hash, sender, recipient, payload, block_height, created_at, type, status
                    FROM "transaction"
                    WHERE {where}
                    ORDER BY created_at DESC, tx_hash DESC
                    LIMIT ? OFFSET ?
                """,  # nosec B608 - WHERE fragments are internally generated clause strings; all values are bound parameters
                    params,
                )

                transactions = []
                rows = list(await db_cursor.fetchall())
                next_cursor = f"{rows[limit - 1][5]}|{rows[limit - 1][0]}" if len(rows) > limit else None
                rows = rows[:limit]
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

            return {"transactions": transactions, "next_cursor": next_cursor}

        return {"transactions": [], "next_cursor": None}
    except Exception:
        logger.exception("Error searching transactions for address %s", address)
        return {"transactions": [], "next_cursor": None}


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
    except (ValueError, TypeError) as exc:
        logger.debug("unparseable tx payload for %s: %s", tx.get("tx_hash"), exc)
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
