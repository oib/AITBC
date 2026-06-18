"""
Multi-Chain AITBC Exchange API
Complete multi-chain trading with chain isolation
"""

import os
import sqlite3
from datetime import datetime

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AsyncAITBCHTTPClient
from aitbc.rate_limiting import RateLimitMiddleware

app = FastAPI(title="AITBC Multi-Chain Exchange", version="2.0.0")
app.add_middleware(RateLimitMiddleware, rate=100, per=60)
logger = get_logger(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "exchange_multichain.db")
SUPPORTED_CHAINS = {
    "ait-devnet": {
        "name": "AITBC Development Network",
        "status": "active",
        "blockchain_url": "http://localhost:8007",
        "token_symbol": "AITBC-DEV",
    },
    "ait-testnet": {"name": "AITBC Test Network", "status": "inactive", "blockchain_url": None, "token_symbol": "AITBC-TEST"},
}


class OrderRequest(BaseModel):
    order_type: str = Field(..., regex="^(BUY|SELL)$")
    amount: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    chain_id: str = Field(..., regex="^(ait-devnet|ait-testnet)$")
    user_address: str = Field(..., min_length=1)


class ChainOrderRequest(BaseModel):
    chain_id: str = Field(..., regex="^(ait-devnet|ait-testnet)$")
    order_type: str = Field(..., regex="^(BUY|SELL)$")


class MultiChainTradeRequest(BaseModel):
    buy_order_id: int | None = None
    sell_order_id: int | None = None
    amount: float = Field(..., gt=0)
    chain_id: str = Field(..., regex="^(ait-devnet|ait-testnet)$")


def get_db_connection():
    """Get database connection with proper configuration"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize database with multi-chain schema"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            CREATE TABLE IF NOT EXISTS chains (\n                chain_id TEXT PRIMARY KEY,\n                name TEXT NOT NULL,\n                status TEXT NOT NULL CHECK(status IN ('active', 'inactive', 'maintenance')),\n                blockchain_url TEXT,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                enabled BOOLEAN DEFAULT 1\n            )\n        "
        )
        cursor.execute(
            "\n            CREATE TABLE IF NOT EXISTS orders (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                order_type TEXT NOT NULL CHECK(order_type IN ('BUY', 'SELL')),\n                amount REAL NOT NULL,\n                price REAL NOT NULL,\n                total REAL NOT NULL,\n                filled REAL DEFAULT 0,\n                remaining REAL NOT NULL,\n                status TEXT DEFAULT 'open' CHECK(status IN ('open', 'filled', 'cancelled')),\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                user_address TEXT,\n                tx_hash TEXT,\n                chain_id TEXT NOT NULL DEFAULT 'ait-devnet',\n                blockchain_tx_hash TEXT,\n                chain_status TEXT DEFAULT 'pending' CHECK(chain_status IN ('pending', 'confirmed', 'failed'))\n            )\n        "
        )
        cursor.execute(
            "\n            CREATE TABLE IF NOT EXISTS trades (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                buy_order_id INTEGER,\n                sell_order_id INTEGER,\n                amount REAL NOT NULL,\n                price REAL NOT NULL,\n                total REAL NOT NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                chain_id TEXT NOT NULL DEFAULT 'ait-devnet',\n                blockchain_tx_hash TEXT,\n                chain_status TEXT DEFAULT 'pending' CHECK(chain_status IN ('pending', 'confirmed', 'failed'))\n            )\n        "
        )
        for chain_id, chain_info in SUPPORTED_CHAINS.items():
            cursor.execute(
                "\n                INSERT OR REPLACE INTO chains (chain_id, name, status, blockchain_url)\n                VALUES (?, ?, ?, ?)\n            ",
                (chain_id, chain_info["name"], chain_info["status"], chain_info["blockchain_url"]),
            )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_chain_id ON orders(chain_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_chain_id ON trades(chain_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_chain_status ON orders(chain_id, status)")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("Database initialization error: %s", e)
        return False


async def verify_chain_transaction(chain_id: str, tx_hash: str) -> bool:
    """Verify transaction on specific chain"""
    if chain_id not in SUPPORTED_CHAINS:
        return False
    chain_info = SUPPORTED_CHAINS[chain_id]
    if chain_info["status"] != "active" or not chain_info["blockchain_url"]:
        return False
    try:
        client = AsyncAITBCHTTPClient(base_url=chain_info["blockchain_url"], timeout=5)
        response = await client.async_get(f"/api/v1/transactions/{tx_hash}")
        return response is not None
    except NetworkError:
        return False


async def submit_chain_transaction(chain_id: str, order_data: dict) -> str | None:
    """Submit transaction to specific chain"""
    if chain_id not in SUPPORTED_CHAINS:
        return None
    chain_info = SUPPORTED_CHAINS[chain_id]
    if chain_info["status"] != "active" or not chain_info["blockchain_url"]:
        return None
    try:
        client = AsyncAITBCHTTPClient(base_url=chain_info["blockchain_url"], timeout=10)
        response = await client.async_post("/api/v1/transactions", json=order_data)
        if response:
            return response.get("tx_hash")
    except NetworkError as e:
        logger.error("Chain transaction error: %s", e)
    return None


@app.get("/health")
async def health_check():
    """Multi-chain health check"""
    chain_status = {}
    for chain_id, chain_info in SUPPORTED_CHAINS.items():
        chain_status[chain_id] = {
            "name": chain_info["name"],
            "status": chain_info["status"],
            "blockchain_url": chain_info["blockchain_url"],
            "connected": False,
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
        "service": "multi-chain-exchange",
        "version": "2.0.0",
        "supported_chains": list(SUPPORTED_CHAINS.keys()),
        "chain_status": chain_status,
        "multi_chain": True,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/v1/chains")
async def get_chains():
    """Get all supported chains with their status"""
    chains = []
    for chain_id, chain_info in SUPPORTED_CHAINS.items():
        chains.append(
            {
                "chain_id": chain_id,
                "name": chain_info["name"],
                "status": chain_info["status"],
                "blockchain_url": chain_info["blockchain_url"],
                "token_symbol": chain_info["token_symbol"],
            }
        )
    return {
        "chains": chains,
        "total_chains": len(chains),
        "active_chains": len([c for c in chains if c["status"] == "active"]),
    }


@app.post("/api/v1/orders")
async def create_order(order: OrderRequest, background_tasks: BackgroundTasks):
    """Create chain-specific order"""
    if order.chain_id not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail="Unsupported chain")
    chain_info = SUPPORTED_CHAINS[order.chain_id]
    if chain_info["status"] != "active":
        raise HTTPException(status_code=400, detail=f"Chain {order.chain_id} is not active")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            INSERT INTO orders (order_type, amount, price, total, remaining, user_address, chain_id)\n            VALUES (?, ?, ?, ?, ?, ?, ?)\n        ",
            (order.order_type, order.amount, order.price, order.total, order.amount, order.user_address, order.chain_id),
        )
        order_id = cursor.lastrowid
        background_tasks.add_task(submit_order_to_blockchain, order_id, order.chain_id)
        conn.commit()
        conn.close()
        return {
            "success": True,
            "order_id": order_id,
            "chain_id": order.chain_id,
            "status": "created",
            "message": f"Order created on {chain_info['name']}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Order creation failed: {str(e)}") from e


async def submit_order_to_blockchain(order_id: int, chain_id: str):
    """Submit order to blockchain in background"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        if order:
            order_data = {
                "type": "order",
                "order_type": order["order_type"],
                "amount": order["amount"],
                "price": order["price"],
                "user_address": order["user_address"],
            }
            tx_hash = await submit_chain_transaction(chain_id, order_data)
            if tx_hash:
                cursor.execute(
                    "\n                    UPDATE orders SET blockchain_tx_hash = ?, chain_status = 'pending'\n                    WHERE id = ?\n                ",
                    (tx_hash, order_id),
                )
                conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Background blockchain submission error: %s", e)


@app.get("/api/v1/orders/{chain_id}")
async def get_chain_orders(chain_id: str, status: str | None = None):
    """Get orders for specific chain"""
    if chain_id not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail="Unsupported chain")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = "SELECT * FROM orders WHERE chain_id = ?"
        params = [chain_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        orders = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {"chain_id": chain_id, "orders": orders, "total_orders": len(orders)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get orders: {str(e)}") from e


@app.get("/api/v1/orderbook/{chain_id}")
async def get_chain_orderbook(chain_id: str):
    """Get order book for specific chain"""
    if chain_id not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail="Unsupported chain")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            SELECT price, SUM(remaining) as volume, COUNT(*) as count\n            FROM orders \n            WHERE chain_id = ? AND order_type = 'BUY' AND status = 'open'\n            GROUP BY price\n            ORDER BY price DESC\n        ",
            (chain_id,),
        )
        buy_orders = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            "\n            SELECT price, SUM(remaining) as volume, COUNT(*) as count\n            FROM orders \n            WHERE chain_id = ? AND order_type = 'SELL' AND status = 'open'\n            GROUP BY price\n            ORDER BY price ASC\n        ",
            (chain_id,),
        )
        sell_orders = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {
            "chain_id": chain_id,
            "buy_orders": buy_orders,
            "sell_orders": sell_orders,
            "spread": sell_orders[0]["price"] - buy_orders[0]["price"] if buy_orders and sell_orders else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get orderbook: {str(e)}") from e


@app.get("/api/v1/trades/{chain_id}")
async def get_chain_trades(chain_id: str, limit: int = Query(default=50, le=100)):
    """Get trades for specific chain"""
    if chain_id not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail="Unsupported chain")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            SELECT t.*, o1.order_type as buy_order_type, o2.order_type as sell_order_type\n            FROM trades t\n            LEFT JOIN orders o1 ON t.buy_order_id = o1.id\n            LEFT JOIN orders o2 ON t.sell_order_id = o2.id\n            WHERE t.chain_id = ?\n            ORDER BY t.created_at DESC\n            LIMIT ?\n        ",
            (chain_id, limit),
        )
        trades = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {"chain_id": chain_id, "trades": trades, "total_trades": len(trades)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trades: {str(e)}") from e


@app.post("/api/v1/trades")
async def create_trade(trade: MultiChainTradeRequest, background_tasks: BackgroundTasks):
    """Create chain-specific trade"""
    if trade.chain_id not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail="Unsupported chain")
    chain_info = SUPPORTED_CHAINS[trade.chain_id]
    if chain_info["status"] != "active":
        raise HTTPException(status_code=400, detail="Chain is not active")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            INSERT INTO trades (buy_order_id, sell_order_id, amount, price, total, chain_id)\n            VALUES (?, ?, ?, ?, ?, ?)\n        ",
            (trade.buy_order_id, trade.sell_order_id, trade.amount, trade.price, trade.total, trade.chain_id),
        )
        trade_id = cursor.lastrowid
        background_tasks.add_task(submit_trade_to_blockchain, trade_id, trade.chain_id)
        conn.commit()
        conn.close()
        return {
            "success": True,
            "trade_id": trade_id,
            "chain_id": trade.chain_id,
            "status": "created",
            "message": f"Trade created on {chain_info['name']}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trade creation failed: {str(e)}") from e


async def submit_trade_to_blockchain(trade_id: int, chain_id: str):
    """Submit trade to blockchain in background"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
        trade = cursor.fetchone()
        if trade:
            trade_data = {
                "type": "trade",
                "buy_order_id": trade["buy_order_id"],
                "sell_order_id": trade["sell_order_id"],
                "amount": trade["amount"],
                "price": trade["price"],
            }
            tx_hash = await submit_chain_transaction(chain_id, trade_data)
            if tx_hash:
                cursor.execute(
                    "\n                    UPDATE trades SET blockchain_tx_hash = ?, chain_status = 'pending'\n                    WHERE id = ?\n                ",
                    (tx_hash, trade_id),
                )
                conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Background trade blockchain submission error: %s", e)


@app.get("/api/v1/stats/{chain_id}")
async def get_chain_stats(chain_id: str):
    """Get trading statistics for specific chain"""
    if chain_id not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail="Unsupported chain")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "\n            SELECT \n                COUNT(*) as total_orders,\n                SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_orders,\n                SUM(CASE WHEN status = 'filled' THEN 1 ELSE 0 END) as filled_orders,\n                SUM(amount) as total_volume\n            FROM orders WHERE chain_id = ?\n        ",
            (chain_id,),
        )
        order_stats = dict(cursor.fetchone())
        cursor.execute(
            "\n            SELECT \n                COUNT(*) as total_trades,\n                SUM(amount) as trade_volume,\n                AVG(price) as avg_price,\n                MAX(price) as highest_price,\n                MIN(price) as lowest_price\n            FROM trades WHERE chain_id = ?\n        ",
            (chain_id,),
        )
        trade_stats = dict(cursor.fetchone())
        conn.close()
        return {
            "chain_id": chain_id,
            "chain_name": SUPPORTED_CHAINS[chain_id]["name"],
            "orders": order_stats,
            "trades": trade_stats,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}") from e


if __name__ == "__main__":
    if init_database():
        logger.info("Multi-chain database initialized successfully")
    else:
        logger.error("Database initialization failed")
    uvicorn.run(app, host="0.0.0.0", port=8001)
