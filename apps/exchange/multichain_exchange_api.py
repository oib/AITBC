#!/usr/bin/env python3
"""
Multi-Chain AITBC Exchange API
Complete multi-chain trading with chain isolation
"""

import sqlite3
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
import uvicorn
import os

from aitbc.http_client import AsyncAITBCHTTPClient
from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError

app = FastAPI(title="AITBC Multi-Chain Exchange", version="2.0.0")

# Initialize logger
logger = get_logger(__name__)

# Database configuration
DB_PATH = os.path.join(os.path.dirname(__file__), "exchange_multichain.db")

# Supported chains
SUPPORTED_CHAINS = {
    "ait-devnet": {
        "name": "AITBC Development Network",
        "status": "active",
        "blockchain_url": "http://localhost:8007",
        "token_symbol": "AITBC-DEV"
    },
    "ait-testnet": {
        "name": "AITBC Test Network", 
        "status": "inactive",
        "blockchain_url": None,
        "token_symbol": "AITBC-TEST"
    }
}

# Models
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
    buy_order_id: Optional[int] = None
    sell_order_id: Optional[int] = None
    amount: float = Field(..., gt=0)
    chain_id: str = Field(..., regex="^(ait-devnet|ait-testnet)$")

# Database functions
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
        
        # Create chains table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chains (
                chain_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active', 'inactive', 'maintenance')),
                blockchain_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                enabled BOOLEAN DEFAULT 1
            )
        ''')
        
        # Create orders table with chain support
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_type TEXT NOT NULL CHECK(order_type IN ('BUY', 'SELL')),
                amount REAL NOT NULL,
                price REAL NOT NULL,
                total REAL NOT NULL,
                filled REAL DEFAULT 0,
                remaining REAL NOT NULL,
                status TEXT DEFAULT 'open' CHECK(status IN ('open', 'filled', 'cancelled')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_address TEXT,
                tx_hash TEXT,
                chain_id TEXT NOT NULL DEFAULT 'ait-devnet',
                blockchain_tx_hash TEXT,
                chain_status TEXT DEFAULT 'pending' CHECK(chain_status IN ('pending', 'confirmed', 'failed'))
            )
        ''')
        
        # Create trades table with chain support
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                buy_order_id INTEGER,
                sell_order_id INTEGER,
                amount REAL NOT NULL,
                price REAL NOT NULL,
                total REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                chain_id TEXT NOT NULL DEFAULT 'ait-devnet',
                blockchain_tx_hash TEXT,
                chain_status TEXT DEFAULT 'pending' CHECK(chain_status IN ('pending', 'confirmed', 'failed'))
            )
        ''')
        
        # Insert default chains
        for chain_id, chain_info in SUPPORTED_CHAINS.items():
            cursor.execute('''
                INSERT OR REPLACE INTO chains (chain_id, name, status, blockchain_url)
                VALUES (?, ?, ?, ?)
            ''', (chain_id, chain_info["name"], chain_info["status"], chain_info["blockchain_url"]))
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_chain_id ON orders(chain_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_chain_id ON trades(chain_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_chain_status ON orders(chain_id, status)')
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Database initialization error: {e}")
        return False

# Chain-specific functions
async def verify_chain_transaction(chain_id: str, tx_hash: str) -> bool:
    """Verify transaction on specific chain"""
    if chain_id not in SUPPORTED_CHAINS:
        return False
    
    chain_info = SUPPORTED_CHAINS[chain_id]
    if chain_info["status"] != "active" or not chain_info["blockchain_url"]:
        return False
    
    try:
        client = AsyncAITBCHTTPClient(base_url=chain_info['blockchain_url'], timeout=5)
        response = await client.async_get(f"/api/v1/transactions/{tx_hash}")
        return response is not None
    except NetworkError:
        return False

async def submit_chain_transaction(chain_id: str, order_data: Dict) -> Optional[str]:
    """Submit transaction to specific chain"""
    if chain_id not in SUPPORTED_CHAINS:
        return None
    
    chain_info = SUPPORTED_CHAINS[chain_id]
    if chain_info["status"] != "active" or not chain_info["blockchain_url"]:
        return None
    
    try:
        client = AsyncAITBCHTTPClient(base_url=chain_info['blockchain_url'], timeout=10)
        response = await client.async_post("/api/v1/transactions", json=order_data)
        if response:
            return response.get("tx_hash")
    except NetworkError as e:
        logger.error(f"Chain transaction error: {e}")

    return None

# API Endpoints
@app.get("/health")
async def health_check():
    """Multi-chain health check"""
    chain_status = {}
    for chain_id, chain_info in SUPPORTED_CHAINS.items():
        chain_status[chain_id] = {
            "name": chain_info["name"],
            "status": chain_info["status"],
            "blockchain_url": chain_info["blockchain_url"],
            "connected": False
        }
        
        if chain_info["status"] == "active" and chain_info["blockchain_url"]:
            try:
                client = AsyncAITBCHTTPClient(base_url=chain_info['blockchain_url'], timeout=5)
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
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/v1/chains")
async def get_chains():
    """Get all supported chains with their status"""
    chains = []
    for chain_id, chain_info in SUPPORTED_CHAINS.items():
        chains.append({
            "chain_id": chain_id,
            "name": chain_info["name"],
            "status": chain_info["status"],
            "blockchain_url": chain_info["blockchain_url"],
            "token_symbol": chain_info["token_symbol"]
        })
    
    return {
        "chains": chains,
        "total_chains": len(chains),
        "active_chains": len([c for c in chains if c["status"] == "active"])
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
        
        # Create order with chain isolation
        cursor.execute('''
            INSERT INTO orders (order_type, amount, price, total, remaining, user_address, chain_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (order.order_type, order.amount, order.price, order.total, order.amount, order.user_address, order.chain_id))
        
        order_id = cursor.lastrowid
        
        # Submit to blockchain in background
        background_tasks.add_task(submit_order_to_blockchain, order_id, order.chain_id)
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "order_id": order_id,
            "chain_id": order.chain_id,
            "status": "created",
            "message": f"Order created on {chain_info['name']}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Order creation failed: {str(e)}")

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
                "user_address": order["user_address"]
            }
            
            tx_hash = await submit_chain_transaction(chain_id, order_data)
            if tx_hash:
                cursor.execute('''
                    UPDATE orders SET blockchain_tx_hash = ?, chain_status = 'pending'
                    WHERE id = ?
                ''', (tx_hash, order_id))
                conn.commit()
        
        conn.close()
    except Exception as e:
        print(f"Background blockchain submission error: {e}")

@app.get("/api/v1/orders/{chain_id}")
async def get_chain_orders(chain_id: str, status: Optional[str] = None):
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
        
        return {
            "chain_id": chain_id,
            "orders": orders,
            "total_orders": len(orders)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get orders: {str(e)}")

@app.get("/api/v1/orderbook/{chain_id}")
async def get_chain_orderbook(chain_id: str):
    """Get order book for specific chain"""
    if chain_id not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail="Unsupported chain")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get buy orders (sorted by price descending)
        cursor.execute('''
            SELECT price, SUM(remaining) as volume, COUNT(*) as count
            FROM orders 
            WHERE chain_id = ? AND order_type = 'BUY' AND status = 'open'
            GROUP BY price
            ORDER BY price DESC
        ''', (chain_id,))
        buy_orders = [dict(row) for row in cursor.fetchall()]
        
        # Get sell orders (sorted by price ascending)
        cursor.execute('''
            SELECT price, SUM(remaining) as volume, COUNT(*) as count
            FROM orders 
            WHERE chain_id = ? AND order_type = 'SELL' AND status = 'open'
            GROUP BY price
            ORDER BY price ASC
        ''', (chain_id,))
        sell_orders = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "chain_id": chain_id,
            "buy_orders": buy_orders,
            "sell_orders": sell_orders,
            "spread": sell_orders[0]["price"] - buy_orders[0]["price"] if buy_orders and sell_orders else None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get orderbook: {str(e)}")

@app.get("/api/v1/trades/{chain_id}")
async def get_chain_trades(chain_id: str, limit: int = Query(default=50, le=100)):
    """Get trades for specific chain"""
    if chain_id not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail="Unsupported chain")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT t.*, o1.order_type as buy_order_type, o2.order_type as sell_order_type
            FROM trades t
            LEFT JOIN orders o1 ON t.buy_order_id = o1.id
            LEFT JOIN orders o2 ON t.sell_order_id = o2.id
            WHERE t.chain_id = ?
            ORDER BY t.created_at DESC
            LIMIT ?
        ''', (chain_id, limit))
        
        trades = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "chain_id": chain_id,
            "trades": trades,
            "total_trades": len(trades)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trades: {str(e)}")

@app.post("/api/v1/trades")
async def create_trade(trade: MultiChainTradeRequest, background_tasks: BackgroundTasks):
    """Create chain-specific trade"""
    if trade.chain_id not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail="Unsupported chain")
    
    chain_info = SUPPORTED_CHAINS[trade.chain_id]
    if chain_info["status"] != "active":
        raise HTTPException(status_code=400, detail=f"Chain is not active")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create trade with chain isolation
        cursor.execute('''
            INSERT INTO trades (buy_order_id, sell_order_id, amount, price, total, chain_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (trade.buy_order_id, trade.sell_order_id, trade.amount, trade.price, trade.total, trade.chain_id))
        
        trade_id = cursor.lastrowid
        
        # Submit to blockchain in background
        background_tasks.add_task(submit_trade_to_blockchain, trade_id, trade.chain_id)
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "trade_id": trade_id,
            "chain_id": trade.chain_id,
            "status": "created",
            "message": f"Trade created on {chain_info['name']}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trade creation failed: {str(e)}")

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
                "price": trade["price"]
            }
            
            tx_hash = await submit_chain_transaction(chain_id, trade_data)
            if tx_hash:
                cursor.execute('''
                    UPDATE trades SET blockchain_tx_hash = ?, chain_status = 'pending'
                    WHERE id = ?
                ''', (tx_hash, trade_id))
                conn.commit()
        
        conn.close()
    except Exception as e:
        print(f"Background trade blockchain submission error: {e}")

@app.get("/api/v1/stats/{chain_id}")
async def get_chain_stats(chain_id: str):
    """Get trading statistics for specific chain"""
    if chain_id not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail="Unsupported chain")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get order stats
        cursor.execute('''
            SELECT 
                COUNT(*) as total_orders,
                SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_orders,
                SUM(CASE WHEN status = 'filled' THEN 1 ELSE 0 END) as filled_orders,
                SUM(amount) as total_volume
            FROM orders WHERE chain_id = ?
        ''', (chain_id,))
        order_stats = dict(cursor.fetchone())
        
        # Get trade stats
        cursor.execute('''
            SELECT 
                COUNT(*) as total_trades,
                SUM(amount) as trade_volume,
                AVG(price) as avg_price,
                MAX(price) as highest_price,
                MIN(price) as lowest_price
            FROM trades WHERE chain_id = ?
        ''', (chain_id,))
        trade_stats = dict(cursor.fetchone())
        
        conn.close()
        
        return {
            "chain_id": chain_id,
            "chain_name": SUPPORTED_CHAINS[chain_id]["name"],
            "orders": order_stats,
            "trades": trade_stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

if __name__ == "__main__":
    # Initialize database
    if init_database():
        print("✅ Multi-chain database initialized successfully")
    else:
        print("❌ Database initialization failed")
    
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=8001)
