"""Block routes — latest blocks, non-empty blocks, block by hash, block by address, block by height."""

from typing import Any

import httpx
from fastapi import APIRouter

from aitbc.aitbc_logging import get_logger
from aitbc.utils import format_ait

from chain_client import (
    BLOCKCHAIN_RPC_URLS,
    DEFAULT_CHAIN,
    get_block,
    get_latest_blocks,
    normalize_block,
)
from validation import validate_tx_hash

logger = get_logger(__name__)

router = APIRouter()


@router.get("/api/blocks/latest")
async def api_latest_blocks(
    chain_id: str | None = DEFAULT_CHAIN,
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    """API endpoint for latest blocks"""
    blocks = await get_latest_blocks(limit, chain_id, offset)  # type: ignore[arg-type]
    return {"blocks": blocks}


@router.get("/api/blocks/non-empty")
async def api_non_empty_blocks(
    chain_id: str | None = DEFAULT_CHAIN,
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    """API endpoint for non-empty blocks (blocks with transactions)"""
    try:
        import sqlite3
        from pathlib import Path

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if not chain_db_path.exists():
            return {"blocks": []}

        conn = sqlite3.connect(str(chain_db_path))
        cursor = conn.cursor()

        # Get current chain height
        cursor.execute("SELECT MAX(height) FROM block")
        max_height = cursor.fetchone()[0] or 0

        # Find non-empty blocks by searching backwards from tip
        # Join with transaction table to find blocks that have transactions
        cursor.execute(
            """
            SELECT DISTINCT b.height, b.hash, b.proposer, b.timestamp, b.tx_count, b.state_root
            FROM block b
            INNER JOIN "transaction" t ON b.height = t.block_height
            WHERE b.height <= ?
            ORDER BY b.height DESC
            LIMIT ? OFFSET ?
        """,
            (max_height, limit, offset),
        )

        blocks = []
        for row in cursor.fetchall():
            height, block_hash, proposer, timestamp, tx_count, state_root = row

            # Get transactions for this block
            cursor.execute(
                """
                SELECT tx_hash, sender, recipient, payload, type, status, created_at, value, fee, nonce
                FROM "transaction"
                WHERE block_height = ?
                ORDER BY created_at
            """,
                (height,),
            )

            transactions = []
            for tx_row in cursor.fetchall():
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
                }
            )

        conn.close()
        return {"blocks": blocks}
    except Exception as e:
        print(f"Error getting non-empty blocks: {e}")
        return {"blocks": []}


@router.get("/api/blocks/by-hash/{hash}")
async def api_block_by_hash(hash: str, chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """API endpoint for block by hash"""
    if not validate_tx_hash(hash):
        return {}
    # Strip 0x prefix for comparison
    clean_hash = hash[2:] if hash.startswith("0x") else hash
    try:
        # First try blockchain database for direct lookup
        import sqlite3
        from pathlib import Path

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if chain_db_path.exists():
            conn = sqlite3.connect(str(chain_db_path))
            cursor = conn.cursor()

            # Search for block by hash (case-insensitive, with or without 0x prefix)
            cursor.execute(
                """
                SELECT height, hash, proposer, timestamp, tx_count, state_root
                FROM block
                WHERE lower(replace(hash, '0x', '')) = ?
            """,
                (clean_hash.lower(),),
            )

            result = cursor.fetchone()

            if result:
                height, block_hash, proposer, timestamp, tx_count, state_root = result

                # Get transactions for this block
                cursor.execute(
                    """
                    SELECT tx_hash, sender, recipient, payload, type, status, created_at, value, fee, nonce
                    FROM "transaction"
                    WHERE block_height = ?
                    ORDER BY created_at
                """,
                    (height,),
                )

                transactions = []
                for row in cursor.fetchall():
                    tx_hash, sender, recipient, payload, tx_type, status, created_at, value, fee, nonce = row
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

                conn.close()
                return {
                    "height": height,
                    "hash": block_hash,
                    "proposer": proposer,
                    "timestamp": timestamp,
                    "txCount": tx_count,
                    "stateRoot": state_root,
                    "transactions": transactions,
                }

            conn.close()

        # Fallback to RPC method
        rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])

        # Get current head to determine height range
        async with httpx.AsyncClient() as client:
            head_response = await client.get(f"{rpc_url}/rpc/head", params={"chain_id": chain_id})
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
                        params={"start": start_height, "end": current_height, "include_tx": "false", "chain_id": chain_id},
                    )
                    if range_response.status_code == 200:
                        range_data = range_response.json()
                        blocks = range_data.get("blocks", [])
                        for block in blocks:
                            block_hash = block.get("hash", "")
                            clean_block_hash = block_hash[2:] if block_hash.startswith("0x") else block_hash
                            if clean_block_hash and clean_block_hash.lower() == clean_hash.lower():
                                return normalize_block(block)

        return {}
    except Exception as e:
        print(f"Error getting block by hash {hash}: {e}")
        return {}


@router.get("/api/blocks/by-address/{address}")
async def api_blocks_by_address(
    address: str,
    chain_id: str | None = DEFAULT_CHAIN,
    limit: int = 50,
) -> dict[str, Any]:
    """Get all blocks that contain transactions referencing a given address"""
    try:
        import sqlite3
        from pathlib import Path

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if not chain_db_path.exists():
            return {"blocks": []}

        conn = sqlite3.connect(str(chain_db_path))
        cursor = conn.cursor()

        search_term = f"%{address}%"
        cursor.execute(
            """
            SELECT DISTINCT b.height, b.hash, b.proposer, b.timestamp, b.tx_count, b.state_root
            FROM block b
            JOIN "transaction" t ON b.height = t.block_height
            WHERE t.sender LIKE ? OR t.recipient LIKE ? OR t.payload LIKE ?
            ORDER BY b.height DESC
            LIMIT ?
        """,
            (search_term, search_term, search_term, limit),
        )

        blocks = []
        for row in cursor.fetchall():
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

        conn.close()
        return {"blocks": blocks}
    except Exception as e:
        print(f"Error getting blocks for address {address}: {e}")
        return {"blocks": []}


@router.get("/api/blocks/{height}")
async def api_block(height: int, chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """API endpoint for block data"""
    block_data = await get_block(height, chain_id)  # type: ignore[arg-type]

    # Add transactions for this block
    try:
        import sqlite3
        from pathlib import Path

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if chain_db_path.exists():
            conn = sqlite3.connect(str(chain_db_path))
            cursor = conn.cursor()

            # Get transactions for this block
            cursor.execute(
                """
                SELECT tx_hash, sender, recipient, payload, type, status, created_at, value, fee, nonce
                FROM "transaction"
                WHERE block_height = ?
                ORDER BY created_at
            """,
                (height,),
            )

            transactions = []
            for row in cursor.fetchall():
                tx_hash, sender, recipient, payload, tx_type, status, created_at, value, fee, nonce = row
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

            conn.close()
            block_data["transactions"] = transactions
        else:
            block_data["transactions"] = []
    except Exception as e:
        print(f"Error getting transactions for block {height}: {e}")
        block_data["transactions"] = []

    return block_data
