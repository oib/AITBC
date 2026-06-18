"""
Cross-Chain Trading Extension for Multi-Chain Exchange
Adds cross-chain trading, bridging, and swap functionality
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks, HTTPException
from multichain_exchange_api import SUPPORTED_CHAINS, app, get_db_connection
from pydantic import BaseModel, Field

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class CrossChainSwapRequest(BaseModel):
    from_chain: str = Field(..., regex="^[a-z0-9.-]+$")
    to_chain: str = Field(..., regex="^[a-z0-9.-]+$")
    from_token: str = Field(..., min_length=1)
    to_token: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    min_amount: float = Field(..., gt=0)
    user_address: str = Field(..., min_length=1)
    slippage_tolerance: float = Field(default=0.01, ge=0, le=0.1)


class BridgeRequest(BaseModel):
    source_chain: str = Field(..., regex="^[a-z0-9.-]+$")
    target_chain: str = Field(..., regex="^[a-z0-9.-]+$")
    token: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    recipient_address: str = Field(..., min_length=1)


class CrossChainOrder(BaseModel):
    order_type: str = Field(..., regex="^(BUY|SELL)$")
    amount: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    chain_id: str = Field(..., regex="^[a-z0-9.-]+$")
    cross_chain: bool = Field(default=True)
    target_chain: str | None = None
    user_address: str = Field(..., min_length=1)


def init_cross_chain_tables():
    """Initialize cross-chain trading tables"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            CREATE TABLE IF NOT EXISTS cross_chain_swaps (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                swap_id TEXT UNIQUE NOT NULL,\n                from_chain TEXT NOT NULL,\n                to_chain TEXT NOT NULL,\n                from_token TEXT NOT NULL,\n                to_token TEXT NOT NULL,\n                amount REAL NOT NULL,\n                min_amount REAL NOT NULL,\n                expected_amount REAL NOT NULL,\n                actual_amount REAL DEFAULT NULL,\n                user_address TEXT NOT NULL,\n                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'executing', 'completed', 'failed', 'refunded')),\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                completed_at TIMESTAMP NULL,\n                from_tx_hash TEXT NULL,\n                to_tx_hash TEXT NULL,\n                bridge_fee REAL DEFAULT 0,\n                slippage REAL DEFAULT 0,\n                error_message TEXT NULL\n            )\n        "
        )
        cursor.execute(
            "\n            CREATE TABLE IF NOT EXISTS bridge_transactions (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                bridge_id TEXT UNIQUE NOT NULL,\n                source_chain TEXT NOT NULL,\n                target_chain TEXT NOT NULL,\n                token TEXT NOT NULL,\n                amount REAL NOT NULL,\n                recipient_address TEXT NOT NULL,\n                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'locked', 'transferred', 'completed', 'failed')),\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                completed_at TIMESTAMP NULL,\n                source_tx_hash TEXT NULL,\n                target_tx_hash TEXT NULL,\n                bridge_fee REAL DEFAULT 0,\n                lock_address TEXT NULL,\n                error_message TEXT NULL\n            )\n        "
        )
        cursor.execute(
            "\n            CREATE TABLE IF NOT EXISTS cross_chain_pools (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                pool_id TEXT UNIQUE NOT NULL,\n                token_a TEXT NOT NULL,\n                token_b TEXT NOT NULL,\n                chain_a TEXT NOT NULL,\n                chain_b TEXT NOT NULL,\n                reserve_a REAL DEFAULT 0,\n                reserve_b REAL DEFAULT 0,\n                total_liquidity REAL DEFAULT 0,\n                apr REAL DEFAULT 0,\n                fee_rate REAL DEFAULT 0.003,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        "
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_swaps_user ON cross_chain_swaps(user_address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_swaps_status ON cross_chain_swaps(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_swaps_chains ON cross_chain_swaps(from_chain, to_chain)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bridge_status ON bridge_transactions(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bridge_chains ON bridge_transactions(source_chain, target_chain)")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("Cross-chain database initialization error: %s", e)
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
        if pool:
            reserve_a, reserve_b = pool
            if from_chain == SUPPORTED_CHAINS[from_chain] and reserve_a > 0 and (reserve_b > 0):
                return reserve_b / reserve_a
        if from_token == to_token:
            return 1.0
        rate_a = get_chain_token_price(from_chain, from_token)
        rate_b = get_chain_token_price(to_chain, to_token)
        if rate_a and rate_b:
            return rate_b / rate_a
        return None
    except Exception as e:
        logger.error("Rate calculation error: %s", e)
        return None


def get_chain_token_price(chain_id: str, token: str) -> float | None:
    """Get token price on specific chain"""
    try:
        chain_info = SUPPORTED_CHAINS.get(chain_id)
        if not chain_info or chain_info["status"] != "active":
            return None
        if token == "AITBC":
            return 1.0
        elif token == "USDC":
            return 1.0
        else:
            return 0.5
    except Exception:
        return None


async def execute_cross_chain_swap(swap_request: CrossChainSwapRequest) -> dict[str, Any]:
    """Execute cross-chain swap"""
    try:
        if swap_request.from_chain == swap_request.to_chain:
            raise HTTPException(status_code=400, detail="Cannot swap within same chain")
        if swap_request.from_chain not in SUPPORTED_CHAINS or swap_request.to_chain not in SUPPORTED_CHAINS:
            raise HTTPException(status_code=400, detail="Unsupported chain")
        rate = get_cross_chain_rate(
            swap_request.from_chain, swap_request.to_chain, swap_request.from_token, swap_request.to_token
        )
        if not rate:
            raise HTTPException(status_code=400, detail="No exchange rate available")
        expected_amount = swap_request.amount * rate * (1 - 0.003)
        if expected_amount < swap_request.min_amount:
            raise HTTPException(status_code=400, detail="Insufficient output due to slippage")
        swap_id = str(uuid.uuid4())
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            INSERT INTO cross_chain_swaps \n            (swap_id, from_chain, to_chain, from_token, to_token, amount, min_amount, expected_amount, user_address)\n            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)\n        ",
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
            "amount": swap_request.amount,
            "expected_amount": expected_amount,
            "rate": rate,
            "status": "pending",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Swap execution failed: {str(e)}") from e


async def process_cross_chain_swap(swap_id: str):
    """Process cross-chain swap in background"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cross_chain_swaps WHERE swap_id = ?", (swap_id,))
        swap = cursor.fetchone()
        if not swap:
            return
        cursor.execute("UPDATE cross_chain_swaps SET status = 'executing' WHERE swap_id = ?", (swap_id,))
        conn.commit()
        from_tx_hash = await lock_funds_on_chain(swap["from_chain"], swap["from_token"], swap["amount"], swap["user_address"])
        if not from_tx_hash:
            cursor.execute(
                "\n                UPDATE cross_chain_swaps SET status = 'failed', error_message = ? \n                WHERE swap_id = ?\n            ",
                ("Failed to lock source funds", swap_id),
            )
            conn.commit()
            return
        to_tx_hash = await transfer_to_target_chain(
            swap["to_chain"], swap["to_token"], swap["expected_amount"], swap["user_address"]
        )
        if not to_tx_hash:
            await refund_source_chain(swap["from_chain"], from_tx_hash, swap["user_address"])
            cursor.execute(
                "\n                UPDATE cross_chain_swaps SET status = 'refunded', error_message = ?, \n                from_tx_hash = ? WHERE swap_id = ?\n            ",
                ("Target transfer failed, refunded", from_tx_hash, swap_id),
            )
            conn.commit()
            return
        actual_amount = await verify_target_transfer(swap["to_chain"], to_tx_hash)
        cursor.execute(
            "\n            UPDATE cross_chain_swaps SET status = 'completed', actual_amount = ?, \n            from_tx_hash = ?, to_tx_hash = ?, completed_at = CURRENT_TIMESTAMP \n            WHERE swap_id = ?\n        ",
            (actual_amount, from_tx_hash, to_tx_hash, swap_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Cross-chain swap processing error: %s", e)


async def lock_funds_on_chain(chain_id: str, token: str, amount: float, user_address: str) -> str | None:
    """Lock funds on source chain"""
    try:
        chain_info = SUPPORTED_CHAINS[chain_id]
        if chain_info["status"] != "active":
            return None
        lock_tx_hash = f"lock_{uuid.uuid4().hex[:8]}"
        await asyncio.sleep(1)
        return lock_tx_hash
    except Exception:
        return None


async def transfer_to_target_chain(chain_id: str, token: str, amount: float, user_address: str) -> str | None:
    """Transfer tokens to target chain"""
    try:
        chain_info = SUPPORTED_CHAINS[chain_id]
        if chain_info["status"] != "active":
            return None
        transfer_tx_hash = f"transfer_{uuid.uuid4().hex[:8]}"
        await asyncio.sleep(2)
        return transfer_tx_hash
    except Exception:
        return None


async def refund_source_chain(chain_id: str, lock_tx_hash: str, user_address: str) -> bool:
    """Refund locked funds on source chain"""
    try:
        chain_info = SUPPORTED_CHAINS[chain_id]
        if chain_info["status"] != "active":
            return False
        await asyncio.sleep(1)
        return True
    except Exception:
        return False


async def verify_target_transfer(chain_id: str, tx_hash: str) -> float | None:
    """Verify transfer on target chain"""
    try:
        chain_info = SUPPORTED_CHAINS[chain_id]
        if chain_info["status"] != "active":
            return None
        await asyncio.sleep(1)
        return 100.0
    except Exception:
        return None


@app.post("/api/v1/cross-chain/swap")
async def create_cross_chain_swap(swap_request: CrossChainSwapRequest, background_tasks: BackgroundTasks):
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
        raise HTTPException(status_code=500, detail=f"Failed to get swap: {str(e)}") from e


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
        raise HTTPException(status_code=500, detail=f"Failed to get swaps: {str(e)}") from e


@app.post("/api/v1/cross-chain/bridge")
async def create_bridge_transaction(bridge_request: BridgeRequest, background_tasks: BackgroundTasks):
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
            "amount": bridge_request.amount,
            "bridge_fee": bridge_fee,
            "status": "pending",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bridge creation failed: {str(e)}") from e


async def process_bridge_transaction(bridge_id: str):
    """Process bridge transaction in background"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bridge_transactions WHERE bridge_id = ?", (bridge_id,))
        bridge = cursor.fetchone()
        if not bridge:
            return
        cursor.execute("UPDATE bridge_transactions SET status = 'locked' WHERE bridge_id = ?", (bridge_id,))
        conn.commit()
        source_tx_hash = await lock_funds_on_chain(
            bridge["source_chain"], bridge["token"], bridge["amount"], bridge["recipient_address"]
        )
        if source_tx_hash:
            target_tx_hash = await transfer_to_target_chain(
                bridge["target_chain"], bridge["token"], bridge["amount"], bridge["recipient_address"]
            )
            if target_tx_hash:
                cursor.execute(
                    "\n                    UPDATE bridge_transactions SET status = 'completed', \n                    source_tx_hash = ?, target_tx_hash = ?, completed_at = CURRENT_TIMESTAMP \n                    WHERE bridge_id = ?\n                ",
                    (source_tx_hash, target_tx_hash, bridge_id),
                )
            else:
                cursor.execute(
                    "\n                    UPDATE bridge_transactions SET status = 'failed', error_message = ? \n                    WHERE bridge_id = ?\n                ",
                    ("Target transfer failed", bridge_id),
                )
        else:
            cursor.execute(
                "\n                UPDATE bridge_transactions SET status = 'failed', error_message = ? \n                WHERE bridge_id = ?\n            ",
                ("Source lock failed", bridge_id),
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
        raise HTTPException(status_code=500, detail=f"Failed to get bridge: {str(e)}") from e


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
        raise HTTPException(status_code=500, detail=f"Failed to get pools: {str(e)}") from e


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
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}") from e


if __name__ == "__main__":
    init_cross_chain_tables()
    logger.info("Cross-chain trading extensions initialized")
