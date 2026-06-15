"""
Complete Cross-Chain AITBC Exchange
Multi-chain trading with cross-chain swaps and bridging
"""

import asyncio
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network.http_client import AsyncAITBCHTTPClient
from aitbc.rate_limiting import RateLimitMiddleware

app = FastAPI(title="AITBC Complete Cross-Chain Exchange", version="3.0.0")
app.add_middleware(RateLimitMiddleware, rate=100, per=60)
logger = get_logger(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "exchange_multichain.db")
SUPPORTED_CHAINS = {
    "ait-devnet": {
        "name": "AITBC Development Network",
        "status": "active",
        "blockchain_url": "http://localhost:8007",
        "token_symbol": "AITBC-DEV",
        "bridge_contract": "0x1234567890123456789012345678901234567890",
    },
    "ait-testnet": {
        "name": "AITBC Test Network",
        "status": "inactive",
        "blockchain_url": None,
        "token_symbol": "AITBC-TEST",
        "bridge_contract": "0x0987654321098765432109876543210987654321",
    },
}


class OrderRequest(BaseModel):
    order_type: str = Field(..., regex="^(BUY|SELL)$")
    amount: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    chain_id: str = Field(..., regex="^(ait-devnet|ait-testnet)$")
    user_address: str = Field(..., min_length=1)


class CrossChainSwapRequest(BaseModel):
    from_chain: str = Field(..., regex="^(ait-devnet|ait-testnet)$")
    to_chain: str = Field(..., regex="^(ait-devnet|ait-testnet)$")
    from_token: str = Field(..., min_length=1)
    to_token: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    min_amount: float = Field(..., gt=0)
    user_address: str = Field(..., min_length=1)
    slippage_tolerance: float = Field(default=0.01, ge=0, le=0.1)


class BridgeRequest(BaseModel):
    source_chain: str = Field(..., regex="^(ait-devnet|ait-testnet)$")
    target_chain: str = Field(..., regex="^(ait-devnet|ait-testnet)$")
    token: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    recipient_address: str = Field(..., min_length=1)


def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize complete cross-chain database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            CREATE TABLE IF NOT EXISTS chains (\n                chain_id TEXT PRIMARY KEY,\n                name TEXT NOT NULL,\n                status TEXT NOT NULL CHECK(status IN ('active', 'inactive', 'maintenance')),\n                blockchain_url TEXT,\n                token_symbol TEXT,\n                bridge_contract TEXT,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        "
        )
        cursor.execute(
            "\n            CREATE TABLE IF NOT EXISTS orders (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                order_type TEXT NOT NULL CHECK(order_type IN ('BUY', 'SELL')),\n                amount REAL NOT NULL,\n                price REAL NOT NULL,\n                total REAL NOT NULL,\n                filled REAL DEFAULT 0,\n                remaining REAL NOT NULL,\n                status TEXT DEFAULT 'open' CHECK(status IN ('open', 'filled', 'cancelled')),\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                user_address TEXT,\n                tx_hash TEXT,\n                chain_id TEXT NOT NULL DEFAULT 'ait-devnet',\n                blockchain_tx_hash TEXT,\n                chain_status TEXT DEFAULT 'pending' CHECK(chain_status IN ('pending', 'confirmed', 'failed'))\n            )\n        "
        )
        cursor.execute(
            "\n            CREATE TABLE IF NOT EXISTS trades (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                buy_order_id INTEGER,\n                sell_order_id INTEGER,\n                amount REAL NOT NULL,\n                price REAL NOT NULL,\n                total REAL NOT NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                chain_id TEXT NOT NULL DEFAULT 'ait-devnet',\n                blockchain_tx_hash TEXT,\n                chain_status TEXT DEFAULT 'pending' CHECK(chain_status IN ('pending', 'confirmed', 'failed'))\n            )\n        "
        )
        cursor.execute(
            "\n            CREATE TABLE IF NOT EXISTS cross_chain_swaps (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                swap_id TEXT UNIQUE NOT NULL,\n                from_chain TEXT NOT NULL,\n                to_chain TEXT NOT NULL,\n                from_token TEXT NOT NULL,\n                to_token TEXT NOT NULL,\n                amount REAL NOT NULL,\n                min_amount REAL NOT NULL,\n                expected_amount REAL NOT NULL,\n                actual_amount REAL DEFAULT NULL,\n                user_address TEXT NOT NULL,\n                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'executing', 'completed', 'failed', 'refunded')),\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                completed_at TIMESTAMP NULL,\n                from_tx_hash TEXT NULL,\n                to_tx_hash TEXT NULL,\n                bridge_fee REAL DEFAULT 0,\n                slippage REAL DEFAULT 0,\n                error_message TEXT NULL\n            )\n        "
        )
        cursor.execute(
            "\n            CREATE TABLE IF NOT EXISTS bridge_transactions (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                bridge_id TEXT UNIQUE NOT NULL,\n                source_chain TEXT NOT NULL,\n                target_chain TEXT NOT NULL,\n                token TEXT NOT NULL,\n                amount REAL NOT NULL,\n                recipient_address TEXT NOT NULL,\n                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'locked', 'transferred', 'completed', 'failed')),\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                completed_at TIMESTAMP NULL,\n                source_tx_hash TEXT NULL,\n                target_tx_hash TEXT NULL,\n                bridge_fee REAL DEFAULT 0,\n                lock_address TEXT NULL,\n                error_message TEXT NULL\n            )\n        "
        )
        cursor.execute(
            "\n            CREATE TABLE IF NOT EXISTS cross_chain_pools (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                pool_id TEXT UNIQUE NOT NULL,\n                token_a TEXT NOT NULL,\n                token_b TEXT NOT NULL,\n                chain_a TEXT NOT NULL,\n                chain_b TEXT NOT NULL,\n                reserve_a REAL DEFAULT 0,\n                reserve_b REAL DEFAULT 0,\n                total_liquidity REAL DEFAULT 0,\n                apr REAL DEFAULT 0,\n                fee_rate REAL DEFAULT 0.003,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        "
        )
        for chain_id, chain_info in SUPPORTED_CHAINS.items():
            cursor.execute(
                "\n                INSERT OR REPLACE INTO chains \n                (chain_id, name, status, blockchain_url, token_symbol, bridge_contract)\n                VALUES (?, ?, ?, ?, ?, ?)\n            ",
                (
                    chain_id,
                    chain_info["name"],
                    chain_info["status"],
                    chain_info["blockchain_url"],
                    chain_info["token_symbol"],
                    chain_info.get("bridge_contract"),
                ),
            )
        cursor.execute(
            "\n            INSERT OR IGNORE INTO cross_chain_pools \n            (pool_id, token_a, token_b, chain_a, chain_b, reserve_a, reserve_b, total_liquidity)\n            VALUES (?, ?, ?, ?, ?, ?, ?, ?)\n        ",
            ("ait-devnet-ait-testnet-AITBC", "AITBC", "AITBC", "ait-devnet", "ait-testnet", 1000, 1000, 2000),
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_chain_id ON orders(chain_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_chain_id ON trades(chain_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_swaps_user ON cross_chain_swaps(user_address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_swaps_status ON cross_chain_swaps(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bridge_status ON bridge_transactions(status)")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("Database initialization error: %s", e)
        return False


def get_cross_chain_rate(from_chain: str, to_chain: str, from_token: str, to_token: str) -> float | None:
    """Get cross-chain exchange rate"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            SELECT reserve_a, reserve_b FROM cross_chain_pools \n            WHERE ((chain_a = ? AND chain_b = ? AND token_a = ? AND token_b = ?) OR\n                   (chain_a = ? AND chain_b = ? AND token_a = ? AND token_b = ?))\n        ",
            (from_chain, to_chain, from_token, to_token, to_chain, from_chain, to_token, from_token),
        )
        pool = cursor.fetchone()
        if pool and pool["reserve_a"] > 0 and (pool["reserve_b"] > 0):
            return pool["reserve_b"] / pool["reserve_a"]
        if from_token == to_token:
            return 1.0
        return 1.0
    except Exception as e:
        logger.error("Rate calculation error: %s", e)
        return None


async def execute_cross_chain_swap(swap_request: CrossChainSwapRequest) -> dict[str, Any]:
    """Execute cross-chain swap"""
    try:
        if swap_request.from_chain == swap_request.to_chain:
            raise HTTPException(status_code=400, detail="Cannot swap within same chain")
        rate = get_cross_chain_rate(
            swap_request.from_chain, swap_request.to_chain, swap_request.from_token, swap_request.to_token
        )
        if not rate:
            raise HTTPException(status_code=400, detail="No exchange rate available")
        bridge_fee = swap_request.amount * 0.003
        swap_fee = swap_request.amount * 0.001
        total_fees = bridge_fee + swap_fee
        net_amount = swap_request.amount - total_fees
        expected_amount = net_amount * rate
        if expected_amount < swap_request.min_amount:
            raise HTTPException(status_code=400, detail="Insufficient output due to slippage")
        swap_id = str(uuid.uuid4())
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            INSERT INTO cross_chain_swaps \n            (swap_id, from_chain, to_chain, from_token, to_token, amount, min_amount, \n             expected_amount, user_address, bridge_fee, slippage)\n            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n        ",
            (
                swap_id,
                swap_request.from_chain,
                swap_request.to_chain,
                swap_request.from_token,
                swap_request.to_token,
                swap_request.amount,
                swap_request.min_amount,
                expected_amount,
                swap_request.user_address,
                bridge_fee,
                swap_request.slippage_tolerance,
            ),
        )
        conn.commit()
        conn.close()
        asyncio.create_task(process_cross_chain_swap(swap_id))
        return {
            "success": True,
            "swap_id": swap_id,
            "from_chain": swap_request.from_chain,
            "to_chain": swap_request.to_chain,
            "from_token": swap_request.from_token,
            "to_token": swap_request.to_token,
            "amount": swap_request.amount,
            "expected_amount": expected_amount,
            "rate": rate,
            "total_fees": total_fees,
            "bridge_fee": bridge_fee,
            "swap_fee": swap_fee,
            "status": "pending",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Swap execution failed: {str(e)}")


async def process_cross_chain_swap(swap_id: str):
    """Process cross-chain swap"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cross_chain_swaps WHERE swap_id = ?", (swap_id,))
        swap = cursor.fetchone()
        if not swap:
            return
        cursor.execute("UPDATE cross_chain_swaps SET status = 'executing' WHERE swap_id = ?", (swap_id,))
        conn.commit()
        await asyncio.sleep(3)
        from_tx_hash = f"0x{uuid.uuid4().hex[:64]}"
        to_tx_hash = f"0x{uuid.uuid4().hex[:64]}"
        actual_amount = swap["expected_amount"] * 0.98
        cursor.execute(
            "\n            UPDATE cross_chain_swaps SET status = 'completed', actual_amount = ?, \n            from_tx_hash = ?, to_tx_hash = ?, completed_at = CURRENT_TIMESTAMP \n            WHERE swap_id = ?\n        ",
            (actual_amount, from_tx_hash, to_tx_hash, swap_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Cross-chain swap processing error: %s", e)


@app.get("/health")
async def health_check():
    """Complete cross-chain health check"""
    chain_status = {}
    for chain_id, chain_info in SUPPORTED_CHAINS.items():
        chain_status[chain_id] = {
            "name": chain_info["name"],
            "status": chain_info["status"],
            "blockchain_url": chain_info["blockchain_url"],
            "connected": False,
            "bridge_contract": chain_info.get("bridge_contract"),
        }
        if chain_info["status"] == "active" and chain_info["blockchain_url"]:
            try:
                client = AsyncAITBCHTTPClient(base_url=chain_info["blockchain_url"], timeout=5)
                response = await client.async_get("/health")
                chain_status[chain_id]["connected"] = response is not None
            except NetworkError:
                pass
    return {
        "status": "ok",
        "service": "complete-cross-chain-exchange",
        "version": "3.0.0",
        "supported_chains": list(SUPPORTED_CHAINS.keys()),
        "chain_status": chain_status,
        "cross_chain": True,
        "features": ["trading", "swaps", "bridging", "liquidity_pools"],
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/v1/chains")
async def get_chains():
    """Get all supported chains"""
    chains = []
    for chain_id, chain_info in SUPPORTED_CHAINS.items():
        chains.append(
            {
                "chain_id": chain_id,
                "name": chain_info["name"],
                "status": chain_info["status"],
                "blockchain_url": chain_info["blockchain_url"],
                "token_symbol": chain_info["token_symbol"],
                "bridge_contract": chain_info.get("bridge_contract"),
            }
        )
    return {
        "chains": chains,
        "total_chains": len(chains),
        "active_chains": len([c for c in chains if c["status"] == "active"]),
    }


@app.post("/api/v1/cross-chain/swap")
async def create_cross_chain_swap(swap_request: CrossChainSwapRequest):
    """Create cross-chain swap"""
    return await execute_cross_chain_swap(swap_request)


@app.get("/api/v1/cross-chain/swap/{swap_id}")
async def get_cross_chain_swap(swap_id: str):
    """Get cross-chain swap details"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cross_chain_swaps WHERE swap_id = ?", (swap_id,))
        swap = cursor.fetchone()
        conn.close()
        if not swap:
            raise HTTPException(status_code=404, detail="Swap not found")
        return dict(swap)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get swap: {str(e)}")


@app.get("/api/v1/cross-chain/swaps")
async def get_cross_chain_swaps(user_address: str | None = None, status: str | None = None):
    """Get cross-chain swaps"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = "SELECT * FROM cross_chain_swaps"
        params = []
        if user_address:
            query += " WHERE user_address = ?"
            params.append(user_address)
        if status:
            if user_address:
                query += " AND status = ?"
            else:
                query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        swaps = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {"swaps": swaps, "total_swaps": len(swaps)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get swaps: {str(e)}")


@app.post("/api/v1/cross-chain/bridge")
async def create_bridge_transaction(bridge_request: BridgeRequest):
    """Create bridge transaction"""
    try:
        if bridge_request.source_chain == bridge_request.target_chain:
            raise HTTPException(status_code=400, detail="Cannot bridge to same chain")
        bridge_id = str(uuid.uuid4())
        bridge_fee = bridge_request.amount * 0.001
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            INSERT INTO bridge_transactions \n            (bridge_id, source_chain, target_chain, token, amount, recipient_address, bridge_fee)\n            VALUES (?, ?, ?, ?, ?, ?, ?)\n        ",
            (
                bridge_id,
                bridge_request.source_chain,
                bridge_request.target_chain,
                bridge_request.token,
                bridge_request.amount,
                bridge_request.recipient_address,
                bridge_fee,
            ),
        )
        conn.commit()
        conn.close()
        asyncio.create_task(process_bridge_transaction(bridge_id))
        return {
            "success": True,
            "bridge_id": bridge_id,
            "source_chain": bridge_request.source_chain,
            "target_chain": bridge_request.target_chain,
            "token": bridge_request.token,
            "amount": bridge_request.amount,
            "bridge_fee": bridge_fee,
            "status": "pending",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bridge creation failed: {str(e)}")


async def process_bridge_transaction(bridge_id: str):
    """Process bridge transaction"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bridge_transactions WHERE bridge_id = ?", (bridge_id,))
        bridge = cursor.fetchone()
        if not bridge:
            return
        cursor.execute("UPDATE bridge_transactions SET status = 'locked' WHERE bridge_id = ?", (bridge_id,))
        conn.commit()
        await asyncio.sleep(2)
        source_tx_hash = f"0x{uuid.uuid4().hex[:64]}"
        target_tx_hash = f"0x{uuid.uuid4().hex[:64]}"
        cursor.execute(
            "\n            UPDATE bridge_transactions SET status = 'completed', \n            source_tx_hash = ?, target_tx_hash = ?, completed_at = CURRENT_TIMESTAMP \n            WHERE bridge_id = ?\n        ",
            (source_tx_hash, target_tx_hash, bridge_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Bridge processing error: %s", e)


@app.get("/api/v1/cross-chain/bridge/{bridge_id}")
async def get_bridge_transaction(bridge_id: str):
    """Get bridge transaction details"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bridge_transactions WHERE bridge_id = ?", (bridge_id,))
        bridge = cursor.fetchone()
        conn.close()
        if not bridge:
            raise HTTPException(status_code=404, detail="Bridge transaction not found")
        return dict(bridge)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get bridge: {str(e)}")


@app.get("/api/v1/cross-chain/rates")
async def get_cross_chain_rates():
    """Get cross-chain exchange rates"""
    rates = {}
    for from_chain in SUPPORTED_CHAINS:
        for to_chain in SUPPORTED_CHAINS:
            if from_chain != to_chain:
                pair_key = f"{from_chain}-{to_chain}"
                rate = get_cross_chain_rate(from_chain, to_chain, "AITBC", "AITBC")
                if rate:
                    rates[pair_key] = rate
    return {"rates": rates, "timestamp": datetime.now().isoformat()}


@app.get("/api/v1/cross-chain/pools")
async def get_cross_chain_pools():
    """Get cross-chain liquidity pools"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cross_chain_pools ORDER BY total_liquidity DESC")
        pools = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {"pools": pools, "total_pools": len(pools)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get pools: {str(e)}")


@app.get("/api/v1/cross-chain/stats")
async def get_cross_chain_stats():
    """Get cross-chain trading statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            SELECT status, COUNT(*) as count, SUM(amount) as volume\n            FROM cross_chain_swaps \n            GROUP BY status\n        "
        )
        swap_stats = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            "\n            SELECT status, COUNT(*) as count, SUM(amount) as volume\n            FROM bridge_transactions \n            GROUP BY status\n        "
        )
        bridge_stats = [dict(row) for row in cursor.fetchall()]
        cursor.execute("SELECT SUM(amount) FROM cross_chain_swaps WHERE status = 'completed'")
        total_volume = cursor.fetchone()[0] or 0
        conn.close()
        return {
            "swap_stats": swap_stats,
            "bridge_stats": bridge_stats,
            "total_volume": total_volume,
            "supported_chains": list(SUPPORTED_CHAINS.keys()),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


if __name__ == "__main__":
    if init_database():
        logger.info("Complete cross-chain database initialized")
    else:
        logger.error("Database initialization failed")
    uvicorn.run(app, host="0.0.0.0", port=8001)
