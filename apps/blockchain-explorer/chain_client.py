"""Chain client — config constants, data layer, and shared DB/RPC helpers."""

import os
from typing import Any

import httpx

from aitbc.aitbc_logging import get_logger
from aitbc.utils import format_ait

from validation import validate_chain_id

logger = get_logger(__name__)

# Import data layer for toggle between mock and real data
try:
    from aitbc.data_layer import get_data_layer

    USE_DATA_LAYER = True
except ImportError:
    USE_DATA_LAYER = False

__all__ = [
    "BLOCKCHAIN_RPC_URLS",
    "DEFAULT_CHAIN",
    "EXTERNAL_RPC_URL",
    "USE_DATA_LAYER",
    "get_data_layer",
    "normalize_block",
    "get_chain_head",
    "get_transaction",
    "get_block",
    "get_latest_blocks",
]

# Configuration - Multi-chain support
chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")
BLOCKCHAIN_RPC_URLS = {
    chain_id: "http://localhost:8202",
    "ait-mainnet": "http://aitbc.keisanki.net:8082",
}
DEFAULT_CHAIN = chain_id
EXTERNAL_RPC_URL = "http://aitbc.keisanki.net:8082"  # External access


def normalize_block(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize block data from RPC to explorer format"""
    if not data:
        return {}
    # Map proposer -> validator for UI consistency
    if "proposer" in data and "validator" not in data:
        data["validator"] = data["proposer"]
    # Normalize snake_case -> camelCase for frontend consistency
    if "tx_count" in data and "txCount" not in data:
        data["txCount"] = data["tx_count"]
    if "state_root" in data and "stateRoot" not in data:
        data["stateRoot"] = data["state_root"]
    return data


async def get_chain_head(chain_id: str = DEFAULT_CHAIN) -> dict[str, Any]:
    """Get chain head from specified chain"""
    try:
        rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{rpc_url}/rpc/head", params={"chain_id": chain_id})
            if response.status_code == 200:
                return normalize_block(response.json())  # type: ignore[no-any-return]
    except Exception as e:
        print(f"Error getting chain head for {chain_id}: {e}")
    return {}


async def get_transaction(tx_hash: str, chain_id: str = DEFAULT_CHAIN) -> dict[str, Any]:
    """Get transaction by hash from specified chain using direct DB lookup"""
    if not validate_chain_id(chain_id):
        print("Invalid chain_id format")
        return {}
    try:
        import sqlite3
        from pathlib import Path

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if chain_db_path.exists():
            conn = sqlite3.connect(str(chain_db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT tx_hash, sender, recipient, payload, block_height, created_at, type, status, value, fee, nonce
                FROM "transaction"
                WHERE tx_hash = ?
            """,
                (tx_hash,),
            )

            result = cursor.fetchone()
            conn.close()

            if result:
                tx_hash_db, sender, recipient, payload, block_height, created_at, tx_type, status, value, fee, nonce = result
                return {
                    "hash": tx_hash_db,
                    "tx_hash": tx_hash_db,
                    "sender": sender,
                    "from": sender,
                    "recipient": recipient,
                    "to": recipient,
                    "payload": payload,
                    "block_height": block_height,
                    "created_at": created_at,
                    "type": tx_type,
                    "status": status,
                    "value": value,
                    "value_ait": format_ait(value) if value else "0 AIT",
                    "fee": fee,
                    "fee_ait": format_ait(fee) if fee else "0 AIT",
                    "nonce": nonce,
                }

        # Fallback to RPC if DB lookup fails
        rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{rpc_url}/rpc/tx/{tx_hash}", params={"chain_id": chain_id})
            if response.status_code == 200:
                return response.json()  # type: ignore[no-any-return]
    except Exception as e:
        print(f"Error getting transaction {tx_hash} for {chain_id}: {e}")
    return {}


async def get_block(height: int, chain_id: str = DEFAULT_CHAIN) -> dict[str, Any]:
    """Get a specific block by height from specified chain using real blockchain DB"""
    if not validate_chain_id(chain_id):
        print("Invalid chain_id format")
        return {}
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

            # Get block data
            cursor.execute(
                """
                SELECT height, hash, proposer, timestamp, tx_count, state_root
                FROM block
                WHERE height = ?
            """,
                (height,),
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
            else:
                conn.close()
                return {}
        else:
            # Fallback to RPC method
            rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{rpc_url}/rpc/blocks/{height}", params={"chain_id": chain_id, "include_tx": "false"}
                )
                if response.status_code == 200:
                    return normalize_block(response.json())  # type: ignore[no-any-return]
                elif response.status_code == 404:
                    # Block not found - return empty (will be handled by caller)
                    return {}
    except Exception as e:
        print(f"Error getting block {height} for {chain_id}: {e}")
    return {}


async def get_latest_blocks(limit: int = 10, chain_id: str = DEFAULT_CHAIN, offset: int = 0) -> list[dict[str, Any]]:
    """Get latest blocks from blockchain DB via RPC"""
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

            # Get latest blocks with offset
            cursor.execute(
                """
                SELECT height, hash, proposer, timestamp, tx_count, state_root
                FROM block
                ORDER BY height DESC
                LIMIT ? OFFSET ?
            """,
                (limit, offset),
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
                            "amount_ait": format_ait(value) if value else "0 AIT",
                            "fee": fee,
                            "fee_ait": format_ait(fee) if fee else "0 AIT",
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
            return blocks
        else:
            # Fallback to RPC method
            rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
            async with httpx.AsyncClient() as client:
                # Get current head to know the height
                head_response = await client.get(f"{rpc_url}/rpc/head", params={"chain_id": chain_id})
                if head_response.status_code == 200:
                    head = head_response.json()
                    current_height = head.get("height", 0)
                    if current_height == 0:
                        return []

                    # Fetch real blocks from blockchain DB via blocks-range
                    start_height = max(1, current_height - limit + 1)
                    range_response = await client.get(
                        f"{rpc_url}/rpc/blocks-range",
                        params={
                            "start": start_height,
                            "end": current_height,
                            "include_tx": "false",
                            "chain_id": chain_id,
                        },
                    )
                    if range_response.status_code == 200:
                        range_data = range_response.json()
                        blocks = range_data.get("blocks", [])
                        # Normalize and reverse to show newest first
                        blocks = [normalize_block(b) for b in blocks]
                        blocks.reverse()
                        return blocks
            return []
    except Exception as e:
        print(f"Error getting latest blocks: {e}")
        return []
