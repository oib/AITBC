"""Block routes — latest blocks, non-empty blocks, block by hash, block by address, block by height."""

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
    rpc_url_for,
    get_block,
    get_block_transactions_batch,
    get_latest_blocks_page,
    normalize_block,
    scoped_where,
)
from .common import like_pattern
from validation import (
    MAX_EMBEDDED_TXS_PER_BLOCK,
    check_height_cursor,
    check_page_offset,
    clamp_page_limit,
    validate_tx_hash,
)

logger = get_logger(__name__)

router = APIRouter()


@router.get("/api/blocks/latest")
async def api_latest_blocks(
    chain_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
    cursor: str | None = None,
) -> dict[str, Any]:
    """API endpoint for latest blocks. ``cursor`` takes a previous
    ``next_cursor`` for keyset pagination (#1717)."""
    limit = clamp_page_limit(limit)
    offset = check_page_offset(offset)
    check_height_cursor(cursor)
    blocks, next_cursor = await get_latest_blocks_page(limit, chain_id, offset, cursor)
    return {"blocks": blocks, "next_cursor": next_cursor}


@router.get("/api/blocks/non-empty")
async def api_non_empty_blocks(
    chain_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
    cursor: str | None = None,
) -> dict[str, Any]:
    """API endpoint for non-empty blocks (blocks with transactions).
    ``cursor`` takes a previous ``next_cursor`` for keyset pagination (#1717)."""
    limit = clamp_page_limit(limit)
    offset = check_page_offset(offset)
    cursor_height = check_height_cursor(cursor)
    try:
        cid = chain_id or default_chain_id()
        db_path = chain_db_path()

        if db_path is None:
            return {"blocks": [], "next_cursor": None}

        async with chain_db_connect(db_path) as conn:
            db_cursor = await conn.cursor()

            # Get current chain height — scoped: MAX(height) across a
            # multi-chain store would be another chain's tip (#1620).
            max_scope, max_scope_params = await chain_scope(conn, "block", cid)
            max_where, max_params = scoped_where("", max_scope, [], max_scope_params)
            max_clause = f"WHERE {max_where}" if max_where else ""
            await db_cursor.execute(f"SELECT MAX(height) FROM block {max_clause}", max_params)  # nosec B608 - WHERE fragments are internally generated clause strings; all values are bound parameters
            row = await db_cursor.fetchone()
            max_height = row[0] if row and row[0] is not None else 0

            # Find non-empty blocks by searching backwards from tip.
            # The join keys on (height, chain_id): block_height alone
            # collides across chains in a multi-chain store (#1620).
            b_scope, b_scope_params = await chain_scope(conn, "block", cid, alias="b")
            t_scope, t_scope_params = await chain_scope(conn, "transaction", cid, alias="t")
            join_scope = " AND b.chain_id = t.chain_id" if (b_scope and t_scope) else ""
            # The keyset cursor joins the same base fragment as the tip
            # bound so scope params keep their positions (#1717).
            base_where = "b.height <= ?"
            base_params: list[Any] = [max_height]
            if cursor_height is not None:
                base_where += " AND b.height < ?"
                base_params.append(cursor_height)
            where, params = scoped_where(base_where, b_scope, base_params, b_scope_params)
            where, params = scoped_where(where, t_scope, params, t_scope_params)
            await db_cursor.execute(
                f"""
                SELECT DISTINCT b.height, b.hash, b.proposer, b.timestamp, b.tx_count, b.state_root
                FROM block b
                INNER JOIN "transaction" t ON b.height = t.block_height{join_scope}
                WHERE {where}
                ORDER BY b.height DESC
                LIMIT ? OFFSET ?
            """,  # nosec B608 - WHERE fragments are internally generated clause strings; all values are bound parameters
                [*params, limit + 1, offset],
            )

            blocks = []
            rows = list(await db_cursor.fetchall())
            # One extra row proves a next page exists before next_cursor is
            # emitted — never point past the last returned row (#1717).
            next_cursor = str(rows[limit - 1][0]) if len(rows) > limit else None
            rows = rows[:limit]
            # EXPLORER-DEEP2-1 (#1745): one batched tx query for the whole
            # page instead of one query per block. Same per-block cap and
            # cap+1 truncation sentinel as before.
            tx_rows_by_height = await get_block_transactions_batch(conn, cid, [row[0] for row in rows])
            for row in rows:
                height, block_hash, proposer, timestamp, tx_count, state_root = row

                tx_rows = tx_rows_by_height.get(height, [])

                transactions = []
                truncated = len(tx_rows) > MAX_EMBEDDED_TXS_PER_BLOCK
                for tx_row in tx_rows[:MAX_EMBEDDED_TXS_PER_BLOCK]:
                    tx_hash, sender, recipient, payload, tx_type, status, created_at, value, fee, nonce = tx_row
                    transactions.append(
                        {
                            "tx_hash": tx_hash,
                            "sender": sender,
                            "recipient": recipient,
                            "payload": payload,
                            "amount": value,
                            "fee": fee,
                            "nonce": nonce,
                            "type": tx_type,
                            "status": status,
                            "created_at": created_at,
                        }
                    )

                blocks.append(
                    {
                        "height": height,
                        "hash": block_hash,
                        "proposer": proposer,
                        "timestamp": timestamp,
                        "txCount": tx_count,
                        "stateRoot": state_root,
                        "transactions": transactions,
                        "transactions_truncated": truncated,
                    }
                )

            return {"blocks": blocks, "next_cursor": next_cursor}
    except Exception:
        logger.exception("Error getting non-empty blocks")
        return {"blocks": [], "next_cursor": None}


@router.get("/api/blocks/by-hash/{hash}")
async def api_block_by_hash(hash: str, chain_id: str | None = None) -> dict[str, Any]:
    """API endpoint for block by hash"""
    if not validate_tx_hash(hash):
        raise HTTPException(status_code=400, detail="Invalid block hash")
    # Strip 0x prefix for comparison
    clean_hash = hash[2:] if hash.startswith("0x") else hash
    try:
        cid = chain_id or default_chain_id()
        # First try blockchain database for direct lookup
        db_path = chain_db_path()

        if db_path is not None:
            async with chain_db_connect(db_path) as conn:
                cursor = await conn.cursor()

                # Canonical block hashes are 0x-prefixed lowercase hex, so
                # exact-match candidates hit the hash index; the legacy
                # case-insensitive scan remains as fallback (PI-EX-001).
                # Both are chain-scoped — hash lookups must not cross chains
                # in a multi-chain store (#1620).
                scope_sql, scope_params = await chain_scope(conn, "block", cid)
                bare_hash = clean_hash.lower()
                where, params = scoped_where("hash IN (?, ?)", scope_sql, [f"0x{bare_hash}", bare_hash], scope_params)
                await cursor.execute(
                    f"""
                    SELECT height, hash, proposer, timestamp, tx_count, state_root
                    FROM block
                    WHERE {where}
                """,  # nosec B608 - WHERE fragments are internally generated clause strings; all values are bound parameters
                    params,
                )

                result = await cursor.fetchone()
                if result is None:
                    legacy_where, legacy_params = scoped_where(
                        "lower(replace(hash, '0x', '')) = ?", scope_sql, [bare_hash], scope_params
                    )
                    await cursor.execute(
                        f"""
                        SELECT height, hash, proposer, timestamp, tx_count, state_root
                        FROM block
                        WHERE {legacy_where}
                    """,  # nosec B608 - WHERE fragments are internally generated clause strings; all values are bound parameters
                        legacy_params,
                    )
                    result = await cursor.fetchone()

                if result:
                    height, block_hash, proposer, timestamp, tx_count, state_root = result

                    # Get transactions for this block — chain-scoped (#1620)
                    # via the shared batched fetch (#1745); the cap+1
                    # sentinel still detects truncation.
                    tx_rows = (await get_block_transactions_batch(conn, cid, [height])).get(height, [])

                    transactions = []
                    truncated = len(tx_rows) > MAX_EMBEDDED_TXS_PER_BLOCK
                    for tx_row in tx_rows[:MAX_EMBEDDED_TXS_PER_BLOCK]:
                        tx_hash, sender, recipient, payload, tx_type, status, created_at, value, fee, nonce = tx_row
                        transactions.append(
                            {
                                "tx_hash": tx_hash,
                                "sender": sender,
                                "recipient": recipient,
                                "payload": payload,
                                "amount": value,
                                "amount_ait": format_ait(value) if value else "0 AIT",
                                "fee": fee,
                                "fee_ait": format_ait(fee) if fee else "0 AIT",
                                "nonce": nonce,
                                "type": tx_type,
                                "status": status,
                                "created_at": created_at,
                            }
                        )

                    return {
                        "height": height,
                        "hash": block_hash,
                        "proposer": proposer,
                        "timestamp": timestamp,
                        "txCount": tx_count,
                        "stateRoot": state_root,
                        "transactions": transactions,
                        "transactions_truncated": truncated,
                    }

        # Fallback to RPC method
        rpc_url = rpc_url_for(cid)

        # Get current head to determine height range
        async with httpx.AsyncClient() as client:
            head_response = await client.get(f"{rpc_url}/rpc/head", params={"chain_id": cid})
            if head_response.status_code == 200:
                head = head_response.json()
                current_hash = head.get("hash", "")
                clean_current_hash = current_hash[2:] if current_hash.startswith("0x") else current_hash
                if clean_current_hash and clean_current_hash.lower() == clean_hash.lower():
                    return normalize_block(head)

                # Search through recent blocks using blocks-range
                current_height = head.get("height", 0)
                if current_height > 0:
                    start_height = max(1, current_height - 99)
                    range_response = await client.get(
                        f"{rpc_url}/rpc/blocks-range",
                        params={"start": start_height, "end": current_height, "include_tx": "false", "chain_id": cid},
                    )
                    if range_response.status_code == 200:
                        range_data = range_response.json()
                        blocks = range_data.get("blocks", [])
                        for block in blocks:
                            block_hash = block.get("hash", "")
                            clean_block_hash = block_hash[2:] if block_hash.startswith("0x") else block_hash
                            if clean_block_hash and clean_block_hash.lower() == clean_hash.lower():
                                return normalize_block(block)

        raise HTTPException(status_code=404, detail="Block not found")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting block by hash %s", hash)
        return {}


@router.get("/api/blocks/by-address/{address}")
async def api_blocks_by_address(
    address: str,
    chain_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Get all blocks that contain transactions referencing a given address"""
    limit = clamp_page_limit(limit)
    try:
        cid = chain_id or default_chain_id()
        db_path = chain_db_path()

        if db_path is None:
            return {"blocks": []}

        async with chain_db_connect(db_path) as conn:
            cursor = await conn.cursor()

            # Join keys on (height, chain_id) and both sides are scoped —
            # block_height/LIKE matches collide across chains (#1620).
            b_scope, b_scope_params = await chain_scope(conn, "block", cid, alias="b")
            t_scope, t_scope_params = await chain_scope(conn, "transaction", cid, alias="t")
            join_scope = " AND b.chain_id = t.chain_id" if (b_scope and t_scope) else ""
            search_term = like_pattern(address)
            where, params = scoped_where(
                "(t.sender LIKE ? ESCAPE '|' OR t.recipient LIKE ? ESCAPE '|' OR t.payload LIKE ? ESCAPE '|')",
                b_scope,
                [search_term, search_term, search_term],
                b_scope_params,
            )
            where, params = scoped_where(where, t_scope, params, t_scope_params)
            params = [*params, limit]
            await cursor.execute(
                f"""
                SELECT DISTINCT b.height, b.hash, b.proposer, b.timestamp, b.tx_count, b.state_root
                FROM block b
                JOIN "transaction" t ON b.height = t.block_height{join_scope}
                WHERE {where}
                ORDER BY b.height DESC
                LIMIT ?
            """,  # nosec B608 - WHERE fragments are internally generated clause strings; all values are bound parameters
                params,
            )

            blocks = []
            rows = await cursor.fetchall()
            for row in rows:
                height, block_hash, proposer, timestamp, tx_count, state_root = row
                blocks.append(
                    {
                        "height": height,
                        "hash": block_hash,
                        "proposer": proposer,
                        "timestamp": timestamp,
                        "txCount": tx_count,
                        "stateRoot": state_root,
                    }
                )

            return {"blocks": blocks}
    except Exception:
        logger.exception("Error getting blocks for address %s", address)
        return {"blocks": []}


@router.get("/api/blocks/{height}")
async def api_block(height: int, chain_id: str | None = None) -> dict[str, Any]:
    """API endpoint for block data"""
    block_data = await get_block(height, chain_id)
    if not block_data:
        raise HTTPException(status_code=404, detail="Block not found")

    # get_block already embeds the block's transaction list on the DB path;
    # only the RPC fallback lacks the key. Reuse the embedded list: the
    # second query this endpoint used to run was uncapped and overwrote
    # block_data["transactions"] — it would bypass any cap applied inside
    # get_block (EXPLORER-RESP-1 residual, #1516).
    block_data.setdefault("transactions", [])
    return block_data
