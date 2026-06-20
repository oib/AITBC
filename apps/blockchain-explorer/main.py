#!/usr/bin/env python3
"""
AITBC Blockchain Explorer API
Agent-first API for blockchain data access
"""

import csv
import io
import json
import os
import re
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Import data layer for toggle between mock and real data
try:
    from aitbc.data_layer import get_data_layer

    USE_DATA_LAYER = True
except ImportError:
    USE_DATA_LAYER = False

app = FastAPI(title="AITBC Blockchain Explorer API", version="2.0.0")

# Validation patterns for user inputs to prevent SSRF
TX_HASH_PATTERN = re.compile(r"^(0x)?[a-fA-F0-9]{64}$")  # 64-character hex string, optional 0x prefix
CHAIN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,100}$")  # Chain ID pattern (allows dots)


def validate_tx_hash(tx_hash: str) -> bool:
    """Validate transaction hash to prevent SSRF"""
    if not tx_hash:
        return False
    # Check for path traversal or URL manipulation
    if any(char in tx_hash for char in ["/", "\\", "..", "\n", "\r", "\t", "?", "&"]):
        return False
    # Validate against hash pattern (allows optional 0x prefix)
    return bool(TX_HASH_PATTERN.match(tx_hash))


def validate_chain_id(chain_id: str) -> bool:
    """Validate chain ID to prevent SSRF"""
    if not chain_id:
        return False
    # Check for path traversal or URL manipulation
    if any(char in chain_id for char in ["/", "\\", "..", "\n", "\r", "\t", "?", "&"]):
        return False
    # Validate against chain ID pattern
    return bool(CHAIN_ID_PATTERN.match(chain_id))


@app.get("/api/chains")
def list_chains() -> dict[str, Any]:
    """List all supported chains"""
    chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")
    return {
        "chains": [
            {"id": chain_id, "name": "AIT Hub Network", "status": "active"},
            {"id": "ait-mainnet", "name": "AIT Main Network", "status": "coming_soon"},
        ]
    }


# Configuration - Multi-chain support
chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")
BLOCKCHAIN_RPC_URLS = {
    chain_id: "http://localhost:8202",
    "ait-mainnet": "http://aitbc.keisanki.net:8082",
}
DEFAULT_CHAIN = chain_id
EXTERNAL_RPC_URL = "http://aitbc.keisanki.net:8082"  # External access


# Pydantic models for API
class TransactionSearch(BaseModel):
    address: str | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    tx_type: str | None = None
    since: str | None = None
    until: str | None = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class BlockSearch(BaseModel):
    validator: str | None = None
    since: str | None = None
    until: str | None = None
    min_tx: int | None = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AnalyticsRequest(BaseModel):
    period: str = Field(default="24h", pattern="^(1h|24h|7d|30d)$")
    granularity: str | None = None
    metrics: list[str] = Field(default_factory=list)


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
    """Get transaction by hash from specified chain"""
    if not validate_tx_hash(tx_hash) or not validate_chain_id(chain_id):
        print("Invalid tx_hash or chain_id format")
        return {}
    try:
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
            cursor.execute("""
                SELECT height, hash, proposer, timestamp, tx_count, state_root
                FROM block 
                WHERE height = ?
            """, (height,))
            
            result = cursor.fetchone()
            
            if result:
                height, block_hash, proposer, timestamp, tx_count, state_root = result
                
                # Get transactions for this block
                cursor.execute("""
                    SELECT tx_hash, sender, recipient, payload, type, status, created_at
                    FROM "transaction" 
                    WHERE block_height = ?
                    ORDER BY created_at
                """, (height,))
                
                transactions = []
                for row in cursor.fetchall():
                    tx_hash, sender, recipient, payload, tx_type, status, created_at = row
                    transactions.append({
                        "tx_hash": tx_hash,
                        "sender": sender,
                        "recipient": recipient,
                        "payload": payload,
                        "type": tx_type,
                        "status": status,
                        "created_at": created_at,
                    })
                
                conn.close()
                
                return {
                    "height": height,
                    "hash": block_hash,
                    "proposer": proposer,
                    "timestamp": timestamp,
                    "txCount": tx_count,
                    "stateRoot": state_root,
                    "transactions": transactions
                }
            else:
                conn.close()
                return {}
        else:
            # Fallback to RPC method
            rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{rpc_url}/rpc/blocks/{height}", params={"chain_id": chain_id, "include_tx": "false"})
                if response.status_code == 200:
                    return normalize_block(response.json())  # type: ignore[no-any-return]
                elif response.status_code == 404:
                    # Block not found - return empty (will be handled by caller)
                    return {}
    except Exception as e:
        print(f"Error getting block {height} for {chain_id}: {e}")
    return {}


@app.get("/api/chain/head")
async def api_chain_head(chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """API endpoint for chain head"""
    return await get_chain_head(chain_id)  # type: ignore[arg-type]


@app.get("/api/analytics/activity")
async def api_activity_timeline(
    chain_id: str | None = DEFAULT_CHAIN,
    days: int = 30,
) -> dict[str, Any]:
    """Get daily transaction counts for activity timeline chart"""
    try:
        import sqlite3
        from pathlib import Path
        from datetime import datetime, timedelta

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if not chain_db_path.exists():
            return {"labels": [], "datasets": []}

        conn = sqlite3.connect(str(chain_db_path))
        cursor = conn.cursor()

        # Get daily transaction counts for the last N days
        cursor.execute("""
            SELECT DATE(created_at) as day, type, COUNT(*) as count
            FROM "transaction"
            WHERE created_at >= datetime('now', '-{} days')
            GROUP BY DATE(created_at), type
            ORDER BY day
        """.format(days))

        # Organize by day and type
        data: dict[str, dict[str, int]] = {}
        tx_types: set[str] = set()
        for row in cursor.fetchall():
            day, tx_type, count = row
            if day not in data:
                data[day] = {}
            data[day][tx_type] = count
            tx_types.add(tx_type)

        conn.close()

        labels = sorted(data.keys())
        type_colors = {
            "TRANSFER": "#10b981",
            "GPU_MARKETPLACE": "#3b82f6",
            "ESCROW_RELEASE": "#8b5cf6",
            "FAUCET": "#f59e0b",
            "GPU_REGISTER": "#ef4444",
        }

        datasets = []
        for tx_type in sorted(tx_types):
            datasets.append({
                "label": tx_type,
                "data": [data.get(day, {}).get(tx_type, 0) for day in labels],
                "backgroundColor": type_colors.get(tx_type, "#6b7280"),
            })

        return {"labels": labels, "datasets": datasets}
    except Exception as e:
        print(f"Error getting activity timeline: {e}")
        return {"labels": [], "datasets": []}


@app.get("/api/analytics/network-stats")
async def api_network_stats(chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """Get aggregate network stats: total AIT, active offers, unique nodes/providers"""
    try:
        import sqlite3
        from pathlib import Path

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if not chain_db_path.exists():
            return {"total_ait": 0, "active_offers": 0, "unique_nodes": 0, "unique_providers": 0, "total_transactions": 0}

        conn = sqlite3.connect(str(chain_db_path))
        cursor = conn.cursor()

        # Total AIT from TRANSFER + GPU_MARKETPLACE transactions (sum of values)
        cursor.execute("""
            SELECT COALESCE(SUM(CAST(value AS REAL)), 0)
            FROM "transaction"
            WHERE type IN ('TRANSFER', 'GPU_MARKETPLACE')
        """)
        total_ait = cursor.fetchone()[0] or 0

        # Active offers (GPU_MARKETPLACE transactions)
        cursor.execute("""
            SELECT COUNT(DISTINCT tx_hash) FROM "transaction" WHERE type = 'GPU_MARKETPLACE'
        """)
        active_offers = cursor.fetchone()[0] or 0

        # Unique nodes (distinct senders)
        cursor.execute("""
            SELECT COUNT(DISTINCT sender) FROM "transaction"
        """)
        unique_nodes = cursor.fetchone()[0] or 0

        # Unique providers from GPU_MARKETPLACE payload
        cursor.execute("""
            SELECT payload FROM "transaction" WHERE type = 'GPU_MARKETPLACE'
        """)
        providers = set()
        for row in cursor.fetchall():
            try:
                payload = json.loads(row[0]) if row[0] else {}
                pid = payload.get("provider_node_id") or payload.get("node_id")
                if pid:
                    providers.add(pid)
            except Exception:
                pass
        unique_providers = len(providers)

        # Total transactions
        cursor.execute("SELECT COUNT(*) FROM \"transaction\"")
        total_transactions = cursor.fetchone()[0] or 0

        conn.close()
        return {
            "total_ait": round(total_ait, 2),
            "active_offers": active_offers,
            "unique_nodes": unique_nodes,
            "unique_providers": unique_providers,
            "total_transactions": total_transactions,
        }
    except Exception as e:
        print(f"Error getting network stats: {e}")
        return {"total_ait": 0, "active_offers": 0, "unique_nodes": 0, "unique_providers": 0, "total_transactions": 0}


@app.get("/api/analytics/top-addresses")
async def api_top_addresses(
    chain_id: str | None = DEFAULT_CHAIN,
    limit: int = 20,
) -> dict[str, Any]:
    """Get top addresses by transaction count and AIT volume"""
    try:
        import sqlite3
        from pathlib import Path

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if not chain_db_path.exists():
            return {"addresses": []}

        conn = sqlite3.connect(str(chain_db_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                CASE WHEN sender = 'faucet' OR sender = '0x0000000000000000000000000000000000000000' THEN recipient ELSE sender END as addr,
                COUNT(*) as tx_count,
                COALESCE(SUM(CAST(value AS REAL)), 0) as volume
            FROM "transaction"
            WHERE sender != 'faucet' AND sender != '0x0000000000000000000000000000000000000000'
            GROUP BY addr
            ORDER BY tx_count DESC
            LIMIT ?
        """, (limit,))

        addresses = []
        for row in cursor.fetchall():
            addr, tx_count, volume = row
            addresses.append({
                "address": addr,
                "transaction_count": tx_count,
                "volume": round(volume, 2),
            })

        conn.close()
        return {"addresses": addresses}
    except Exception as e:
        print(f"Error getting top addresses: {e}")
        return {"addresses": []}


@app.get("/api/analytics/provider-reputation/{provider_id}")
async def api_provider_reputation(provider_id: str, chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """Compute provider reputation score from blockchain history"""
    try:
        import sqlite3
        from pathlib import Path
        from datetime import datetime

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        if not chain_db_path.exists():
            return {"provider_id": provider_id, "score": 0, "level": "New", "transactions": 0, "days_active": 0}

        conn = sqlite3.connect(str(chain_db_path))
        cursor = conn.cursor()

        # Find all transactions related to this provider
        cursor.execute("""
            SELECT type, value, created_at, payload
            FROM "transaction"
            WHERE sender = ? OR recipient = ?
            ORDER BY created_at ASC
        """, (provider_id, provider_id))

        txs = cursor.fetchall()
        conn.close()

        gpu_offers = 0
        total_volume = 0.0
        first_tx_date = None
        confirmed_count = 0

        for tx in txs:
            tx_type, tx_value, created_at, payload = tx
            if first_tx_date is None:
                first_tx_date = created_at
            if tx_type == "GPU_MARKETPLACE":
                gpu_offers += 1
            try:
                total_volume += float(tx_value or 0)
            except Exception:
                pass
            confirmed_count += 1

        days_active = 0
        if first_tx_date:
            try:
                first_dt = datetime.strptime(first_tx_date, "%Y-%m-%d %H:%M:%S")
                days_active = (datetime.utcnow() - first_dt).days
            except Exception:
                pass

        # Simple reputation formula
        score = min(100, 10 + (gpu_offers * 15) + (days_active * 2) + (confirmed_count * 5))
        level = "New"
        if score >= 80:
            level = "Elite"
        elif score >= 60:
            level = "Trusted"
        elif score >= 40:
            level = "Established"
        elif score >= 20:
            level = "Growing"

        return {
            "provider_id": provider_id,
            "score": score,
            "level": level,
            "transactions": confirmed_count,
            "gpu_offers": gpu_offers,
            "days_active": days_active,
            "total_volume": round(total_volume, 2),
        }
    except Exception as e:
        print(f"Error getting provider reputation: {e}")
        return {"provider_id": provider_id, "score": 0, "level": "New", "transactions": 0, "days_active": 0}


@app.get("/api/blocks/latest")
async def api_latest_blocks(
    chain_id: str | None = DEFAULT_CHAIN,
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    """API endpoint for latest blocks"""
    blocks = await get_latest_blocks(limit, chain_id, offset)  # type: ignore[arg-type]
    return {"blocks": blocks}


@app.get("/api/blocks/non-empty")
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
        cursor.execute("""
            SELECT DISTINCT b.height, b.hash, b.proposer, b.timestamp, b.tx_count, b.state_root
            FROM block b
            INNER JOIN "transaction" t ON b.height = t.block_height
            WHERE b.height <= ?
            ORDER BY b.height DESC
            LIMIT ? OFFSET ?
        """, (max_height, limit, offset))

        blocks = []
        for row in cursor.fetchall():
            height, block_hash, proposer, timestamp, tx_count, state_root = row

            # Get transactions for this block
            cursor.execute("""
                SELECT tx_hash, sender, recipient, payload, type, status, created_at
                FROM "transaction"
                WHERE block_height = ?
                ORDER BY created_at
            """, (height,))

            transactions = []
            for tx_row in cursor.fetchall():
                tx_hash, sender, recipient, payload, tx_type, status, created_at = tx_row
                transactions.append({
                    "tx_hash": tx_hash,
                    "sender": sender,
                    "recipient": recipient,
                    "payload": payload,
                    "type": tx_type,
                    "status": status,
                    "created_at": created_at,
                })

            blocks.append({
                "height": height,
                "hash": block_hash,
                "proposer": proposer,
                "timestamp": timestamp,
                "txCount": tx_count,
                "stateRoot": state_root,
                "transactions": transactions,
            })

        conn.close()
        return {"blocks": blocks}
    except Exception as e:
        print(f"Error getting non-empty blocks: {e}")
        return {"blocks": []}


@app.get("/api/blocks/by-hash/{hash}")
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
            cursor.execute("""
                SELECT height, hash, proposer, timestamp, tx_count, state_root
                FROM block 
                WHERE lower(replace(hash, '0x', '')) = ?
            """, (clean_hash.lower(),))
            
            result = cursor.fetchone()
            
            if result:
                height, block_hash, proposer, timestamp, tx_count, state_root = result
                
                # Get transactions for this block
                cursor.execute("""
                    SELECT tx_hash, sender, recipient, payload, type, status, created_at
                    FROM "transaction" 
                    WHERE block_height = ?
                    ORDER BY created_at
                """, (height,))
                
                transactions = []
                for row in cursor.fetchall():
                    tx_hash, sender, recipient, payload, tx_type, status, created_at = row
                    transactions.append({
                        "tx_hash": tx_hash,
                        "sender": sender,
                        "recipient": recipient,
                        "payload": payload,
                        "type": tx_type,
                        "status": status,
                        "created_at": created_at,
                    })
                
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


@app.get("/api/transactions/by-hash/{hash}")
async def api_transaction_by_hash(hash: str, chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """API endpoint for transaction by hash"""
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
            
            # Search for transaction by hash (case-insensitive, with or without 0x prefix)
            cursor.execute("""
                SELECT tx_hash, sender, recipient, payload, block_height, created_at, type, status
                FROM "transaction" 
                WHERE lower(replace(tx_hash, '0x', '')) = ?
            """, (clean_hash.lower(),))
            
            result = cursor.fetchone()
            conn.close()
            
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
        rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{rpc_url}/rpc/tx/{hash}", params={"chain_id": chain_id})
            if response.status_code == 200:
                return response.json()
        
        return {}
    except Exception as e:
        print(f"Error getting transaction by hash {hash}: {e}")
        return {}


@app.get("/api/transactions/search")
async def api_search_transactions(
    address: str,
    chain_id: str | None = DEFAULT_CHAIN,
    limit: int = 100,
) -> dict[str, Any]:
    """Search transactions by address or node ID in blockchain database"""
    try:
        import sqlite3
        from pathlib import Path
        
        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")
        
        if chain_db_path.exists():
            conn = sqlite3.connect(str(chain_db_path))
            cursor = conn.cursor()
            
            # Search for transactions where sender, recipient, or payload contains the address
            # Using LIKE for partial matching (payload contains node IDs like provider_node_id)
            search_term = f"%{address}%"
            cursor.execute("""
                SELECT tx_hash, sender, recipient, payload, block_height, created_at, type, status
                FROM "transaction" 
                WHERE sender LIKE ? 
                   OR recipient LIKE ? 
                   OR payload LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (search_term, search_term, search_term, limit))
            
            transactions = []
            for row in cursor.fetchall():
                tx_hash, sender, recipient, payload, block_height, created_at, tx_type, status = row
                transactions.append({
                    "tx_hash": tx_hash,
                    "sender": sender,
                    "recipient": recipient,
                    "payload": payload,
                    "block_height": block_height,
                    "created_at": created_at,
                    "type": tx_type,
                    "status": status,
                })
            
            conn.close()
            return {"transactions": transactions}
        
        return {"transactions": []}
    except Exception as e:
        print(f"Error searching transactions for address {address}: {e}")
        return {"transactions": []}


@app.get("/api/blocks/{height}")
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
            cursor.execute("""
                SELECT tx_hash, sender, recipient, payload, type, status, created_at
                FROM "transaction" 
                WHERE block_height = ?
                ORDER BY created_at
            """, (height,))
            
            transactions = []
            for row in cursor.fetchall():
                tx_hash, sender, recipient, payload, tx_type, status, created_at = row
                transactions.append({
                    "tx_hash": tx_hash,
                    "sender": sender,
                    "recipient": recipient,
                    "payload": payload,
                    "type": tx_type,
                    "status": status,
                    "created_at": created_at,
                })
            
            conn.close()
            block_data["transactions"] = transactions
        else:
            block_data["transactions"] = []
    except Exception as e:
        print(f"Error getting transactions for block {height}: {e}")
        block_data["transactions"] = []
    
    return block_data


@app.get("/api/transactions/{tx_hash}")
async def api_transaction(tx_hash: str, chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    """API endpoint for transaction data, normalized for frontend"""
    tx = await get_transaction(tx_hash, chain_id if chain_id else DEFAULT_CHAIN)
    payload = tx.get("payload", {})
    return {
        "hash": tx.get("tx_hash"),
        "block_height": tx.get("block_height"),
        "from": tx.get("sender"),
        "to": tx.get("recipient"),
        "type": payload.get("type", "transfer"),
        "amount": payload.get("amount", 0),
        "fee": payload.get("fee", 0),
        "timestamp": tx.get("created_at"),
    }


# Enhanced API endpoints
@app.get("/api/search/transactions")
async def search_transactions(
    address: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    tx_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 50,
    offset: int = 0,
    chain_id: str | None = DEFAULT_CHAIN,
) -> dict[str, Any]:
    """Advanced transaction search"""
    try:
        if USE_DATA_LAYER:
            # Use data layer with toggle support
            data_layer = get_data_layer()
            rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id if chain_id else DEFAULT_CHAIN, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
            result = await data_layer.get_transactions(
                address, amount_min, amount_max, tx_type, since, until, limit, offset, chain_id, rpc_url
            )
            return result if isinstance(result, dict) else {"transactions": result}
        else:
            # Original implementation without data layer
            # Build query parameters
            params: dict[str, str | int | float] = {}
            if address:
                params["address"] = address
            if amount_min:
                params["amount_min"] = amount_min
            if amount_max:
                params["amount_max"] = amount_max
            if tx_type:
                params["type"] = tx_type
            if since:
                params["since"] = since
            if until:
                params["until"] = until
            params["limit"] = limit
            params["offset"] = offset
            params["chain_id"] = chain_id if chain_id else DEFAULT_CHAIN

            rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id if chain_id else DEFAULT_CHAIN, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{rpc_url}/rpc/search/transactions", params=params)
                if response.status_code == 200:
                    result = response.json()
                    return result if isinstance(result, dict) else {"transactions": result}
                elif response.status_code == 404:
                    return {"transactions": []}
                else:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch transactions from blockchain RPC: {response.text}",
                    )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Blockchain RPC unavailable: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}") from e


@app.get("/api/search/blocks")
async def search_blocks(
    validator: str | None = None,
    since: str | None = None,
    until: str | None = None,
    min_tx: int | None = None,
    limit: int = 50,
    offset: int = 0,
    chain_id: str | None = DEFAULT_CHAIN,
) -> dict[str, Any]:
    """Advanced block search"""
    try:
        if USE_DATA_LAYER:
            # Use data layer with toggle support
            data_layer = get_data_layer()
            rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id if chain_id else DEFAULT_CHAIN, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
            result = await data_layer.get_blocks(validator, since, until, min_tx, limit, offset, chain_id, rpc_url)
            return result if isinstance(result, dict) else {"blocks": result}
        else:
            # Original implementation without data layer
            params: dict[str, str | int] = {}
            if validator:
                params["validator"] = validator
            if since:
                params["since"] = since
            if until:
                params["until"] = until
            if min_tx:
                params["min_tx"] = min_tx
            params["limit"] = limit
            params["offset"] = offset
            params["chain_id"] = chain_id if chain_id else DEFAULT_CHAIN

            rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id if chain_id else DEFAULT_CHAIN, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{rpc_url}/rpc/search/blocks", params=params)
                if response.status_code == 200:
                    result = response.json()
                    return result if isinstance(result, dict) else {"blocks": result}
                elif response.status_code == 404:
                    return {"blocks": []}
                else:
                    raise HTTPException(
                        status_code=response.status_code, detail=f"Failed to fetch blocks from blockchain RPC: {response.text}"
                    )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Blockchain RPC unavailable: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}") from e


@app.get("/api/analytics/overview")
async def analytics_overview(period: str = "24h") -> dict[str, Any]:
    """Get analytics overview from blockchain RPC"""
    try:
        if USE_DATA_LAYER:
            # Use data layer with toggle support
            data_layer = get_data_layer()
            rpc_url = BLOCKCHAIN_RPC_URLS.get(DEFAULT_CHAIN)
            return await data_layer.get_analytics_overview(period, rpc_url)  # type: ignore[no-any-return]
        else:
            # Original implementation without data layer
            rpc_url = BLOCKCHAIN_RPC_URLS.get(DEFAULT_CHAIN)
            params = {"period": period}

            async with httpx.AsyncClient() as client:
                response = await client.get(f"{rpc_url}/rpc/analytics/overview", params=params)
                if response.status_code == 200:
                    return response.json()  # type: ignore[no-any-return]
                elif response.status_code == 404:
                    raise HTTPException(status_code=501, detail="Analytics endpoint not available on blockchain RPC")
                else:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch analytics from blockchain RPC: {response.text}",
                    )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Blockchain RPC unavailable: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics failed: {str(e)}") from e


@app.get("/api/export/search")
async def export_search(format: str = "csv", type: str = "transactions", data: str = "") -> StreamingResponse:
    """Export search results"""
    try:
        if not data:
            raise HTTPException(status_code=400, detail="No data to export")

        results = json.loads(data)

        if format == "csv":
            output = io.StringIO()
            if type == "transactions":
                writer = csv.writer(output)
                writer.writerow(["Hash", "Type", "From", "To", "Amount", "Fee", "Timestamp"])
                for tx in results:
                    writer.writerow(
                        [
                            tx.get("hash", ""),
                            tx.get("type", ""),
                            tx.get("from", ""),
                            tx.get("to", ""),
                            tx.get("amount", ""),
                            tx.get("fee", ""),
                            tx.get("timestamp", ""),
                        ]
                    )
            else:  # blocks
                writer = csv.writer(output)
                writer.writerow(["Height", "Hash", "Validator", "Transactions", "Timestamp"])
                for block in results:
                    writer.writerow(
                        [
                            block.get("height", ""),
                            block.get("hash", ""),
                            block.get("validator", ""),
                            block.get("tx_count", ""),
                            block.get("timestamp", ""),
                        ]
                    )

            output.seek(0)
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=search_results.{format}"},
            )

        elif format == "json":
            return StreamingResponse(
                io.BytesIO(json.dumps(results, indent=2).encode()),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename=search_results.{format}"},
            )

        else:
            raise HTTPException(status_code=400, detail="Unsupported format")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}") from e


@app.get("/api/export/blocks")
async def export_blocks(format: str = "csv") -> StreamingResponse:
    """Export latest blocks"""
    try:
        # Get latest blocks
        blocks = await get_latest_blocks(50)

        if format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Height", "Hash", "Validator", "Transactions", "Timestamp"])
            for block in blocks:
                writer.writerow(
                    [
                        block.get("height", ""),
                        block.get("hash", ""),
                        block.get("validator", ""),
                        block.get("tx_count", ""),
                        block.get("timestamp", ""),
                    ]
                )

            output.seek(0)
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=latest_blocks.{format}"},
            )

        elif format == "json":
            return StreamingResponse(
                io.BytesIO(json.dumps(blocks, indent=2).encode()),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename=latest_blocks.{format}"},
            )

        else:
            raise HTTPException(status_code=400, detail="Unsupported format")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}") from e


# Helper functions
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
            cursor.execute("""
                SELECT height, hash, proposer, timestamp, tx_count, state_root
                FROM block 
                ORDER BY height DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            blocks = []
            for row in cursor.fetchall():
                height, block_hash, proposer, timestamp, tx_count, state_root = row
                
                # Get transactions for this block
                cursor.execute("""
                    SELECT tx_hash, sender, recipient, payload, type, status, created_at
                    FROM "transaction" 
                    WHERE block_height = ?
                    ORDER BY created_at
                """, (height,))
                
                transactions = []
                for tx_row in cursor.fetchall():
                    tx_hash, sender, recipient, payload, tx_type, status, created_at = tx_row
                    transactions.append({
                        "tx_hash": tx_hash,
                        "sender": sender,
                        "recipient": recipient,
                        "payload": payload,
                        "type": tx_type,
                        "status": status,
                        "created_at": created_at,
                    })
                
                blocks.append({
                    "height": height,
                    "hash": block_hash,
                    "proposer": proposer,
                    "timestamp": timestamp,
                    "txCount": tx_count,
                    "stateRoot": state_root,
                    "transactions": transactions
                })
            
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


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint"""
    try:
        # Test blockchain node connectivity
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN]}/rpc/head", timeout=5.0)
            node_status = "ok" if response.status_code == 200 else "error"
    except Exception:
        node_status = "error"

    return {
        "status": "ok" if node_status == "ok" else "degraded",
        "node_status": node_status,
        "version": "2.0.0",
        "features": "advanced_search,analytics,export,real_time",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8100)
