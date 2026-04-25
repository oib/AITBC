#!/usr/bin/env python3
"""
Complete Cross-Chain AITBC Exchange
Multi-chain trading with cross-chain swaps and bridging
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
import uuid
import hashlib

from aitbc.http_client import AsyncAITBCHTTPClient
from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError

app = FastAPI(title="AITBC Complete Cross-Chain Exchange", version="3.0.0")

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
        "token_symbol": "AITBC-DEV",
        "bridge_contract": "0x1234567890123456789012345678901234567890"
    },
    "ait-testnet": {
        "name": "AITBC Test Network", 
        "status": "inactive",
        "blockchain_url": None,
        "token_symbol": "AITBC-TEST",
        "bridge_contract": "0x0987654321098765432109876543210987654321"
    }
}

# Models
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

# Database functions
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
        
        # Chains table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chains (
                chain_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active', 'inactive', 'maintenance')),
                blockchain_url TEXT,
                token_symbol TEXT,
                bridge_contract TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Orders table with chain support
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
        
        # Trades table with chain support
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
        
        # Cross-chain swaps table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cross_chain_swaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                swap_id TEXT UNIQUE NOT NULL,
                from_chain TEXT NOT NULL,
                to_chain TEXT NOT NULL,
                from_token TEXT NOT NULL,
                to_token TEXT NOT NULL,
                amount REAL NOT NULL,
                min_amount REAL NOT NULL,
                expected_amount REAL NOT NULL,
                actual_amount REAL DEFAULT NULL,
                user_address TEXT NOT NULL,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'executing', 'completed', 'failed', 'refunded')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP NULL,
                from_tx_hash TEXT NULL,
                to_tx_hash TEXT NULL,
                bridge_fee REAL DEFAULT 0,
                slippage REAL DEFAULT 0,
                error_message TEXT NULL
            )
        ''')
        
        # Bridge transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bridge_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bridge_id TEXT UNIQUE NOT NULL,
                source_chain TEXT NOT NULL,
                target_chain TEXT NOT NULL,
                token TEXT NOT NULL,
                amount REAL NOT NULL,
                recipient_address TEXT NOT NULL,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'locked', 'transferred', 'completed', 'failed')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP NULL,
                source_tx_hash TEXT NULL,
                target_tx_hash TEXT NULL,
                bridge_fee REAL DEFAULT 0,
                lock_address TEXT NULL,
                error_message TEXT NULL
            )
        ''')
        
        # Cross-chain liquidity pools
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cross_chain_pools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pool_id TEXT UNIQUE NOT NULL,
                token_a TEXT NOT NULL,
                token_b TEXT NOT NULL,
                chain_a TEXT NOT NULL,
                chain_b TEXT NOT NULL,
                reserve_a REAL DEFAULT 0,
                reserve_b REAL DEFAULT 0,
                total_liquidity REAL DEFAULT 0,
                apr REAL DEFAULT 0,
                fee_rate REAL DEFAULT 0.003,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert default chains
        for chain_id, chain_info in SUPPORTED_CHAINS.items():
            cursor.execute('''
                INSERT OR REPLACE INTO chains 
                (chain_id, name, status, blockchain_url, token_symbol, bridge_contract)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (chain_id, chain_info["name"], chain_info["status"], 
                  chain_info["blockchain_url"], chain_info["token_symbol"], 
                  chain_info.get("bridge_contract")))
        
        # Create sample liquidity pool
        cursor.execute('''
            INSERT OR IGNORE INTO cross_chain_pools 
            (pool_id, token_a, token_b, chain_a, chain_b, reserve_a, reserve_b, total_liquidity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("ait-devnet-ait-testnet-AITBC", "AITBC", "AITBC", "ait-devnet", "ait-testnet", 1000, 1000, 2000))
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_chain_id ON orders(chain_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_chain_id ON trades(chain_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_swaps_user ON cross_chain_swaps(user_address)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_swaps_status ON cross_chain_swaps(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bridge_status ON bridge_transactions(status)')
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Database initialization error: {e}")
        return False

# Cross-chain rate calculation
def get_cross_chain_rate(from_chain: str, to_chain: str, from_token: str, to_token: str) -> Optional[float]:
    """Get cross-chain exchange rate"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check liquidity pool
        cursor.execute('''
            SELECT reserve_a, reserve_b FROM cross_chain_pools 
            WHERE ((chain_a = ? AND chain_b = ? AND token_a = ? AND token_b = ?) OR
                   (chain_a = ? AND chain_b = ? AND token_a = ? AND token_b = ?))
        ''', (from_chain, to_chain, from_token, to_token, to_chain, from_chain, to_token, from_token))
        
        pool = cursor.fetchone()
        if pool and pool["reserve_a"] > 0 and pool["reserve_b"] > 0:
            return pool["reserve_b"] / pool["reserve_a"]
        
        # Fallback to 1:1 for same tokens
        if from_token == to_token:
            return 1.0
            
        return 1.0  # Default fallback rate
    except Exception as e:
        print(f"Rate calculation error: {e}")
        return None

# Cross-chain swap execution
async def execute_cross_chain_swap(swap_request: CrossChainSwapRequest) -> Dict[str, Any]:
    """Execute cross-chain swap"""
    try:
        # Validate chains
        if swap_request.from_chain == swap_request.to_chain:
            raise HTTPException(status_code=400, detail="Cannot swap within same chain")
        
        # Get exchange rate
        rate = get_cross_chain_rate(swap_request.from_chain, swap_request.to_chain, 
                                  swap_request.from_token, swap_request.to_token)
        if not rate:
            raise HTTPException(status_code=400, detail="No exchange rate available")
        
        # Calculate expected amount (including fees)
        bridge_fee = swap_request.amount * 0.003  # 0.3% bridge fee
        swap_fee = swap_request.amount * 0.001    # 0.1% swap fee
        total_fees = bridge_fee + swap_fee
        net_amount = swap_request.amount - total_fees
        expected_amount = net_amount * rate
        
        # Check slippage
        if expected_amount < swap_request.min_amount:
            raise HTTPException(status_code=400, detail="Insufficient output due to slippage")
        
        # Create swap record
        swap_id = str(uuid.uuid4())
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO cross_chain_swaps 
            (swap_id, from_chain, to_chain, from_token, to_token, amount, min_amount, 
             expected_amount, user_address, bridge_fee, slippage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (swap_id, swap_request.from_chain, swap_request.to_chain, swap_request.from_token, 
              swap_request.to_token, swap_request.amount, swap_request.min_amount, expected_amount, 
              swap_request.user_address, bridge_fee, swap_request.slippage_tolerance))
        
        conn.commit()
        conn.close()
        
        # Process swap in background
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
            "status": "pending"
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
        
        # Update status
        cursor.execute("UPDATE cross_chain_swaps SET status = 'executing' WHERE swap_id = ?", (swap_id,))
        conn.commit()
        
        # Simulate cross-chain execution
        await asyncio.sleep(3)  # Simulate blockchain processing
        
        # Generate mock transaction hashes
        from_tx_hash = f"0x{uuid.uuid4().hex[:64]}"
        to_tx_hash = f"0x{uuid.uuid4().hex[:64]}"
        
        # Complete swap
        actual_amount = swap["expected_amount"] * 0.98  # Small slippage
        
        cursor.execute('''
            UPDATE cross_chain_swaps SET status = 'completed', actual_amount = ?, 
            from_tx_hash = ?, to_tx_hash = ?, completed_at = CURRENT_TIMESTAMP 
            WHERE swap_id = ?
        ''', (actual_amount, from_tx_hash, to_tx_hash, swap_id))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Cross-chain swap processing error: {e}")

# API Endpoints
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
            "bridge_contract": chain_info.get("bridge_contract")
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
        "service": "complete-cross-chain-exchange",
        "version": "3.0.0",
        "supported_chains": list(SUPPORTED_CHAINS.keys()),
        "chain_status": chain_status,
        "cross_chain": True,
        "features": ["trading", "swaps", "bridging", "liquidity_pools"],
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/v1/chains")
async def get_chains():
    """Get all supported chains"""
    chains = []
    for chain_id, chain_info in SUPPORTED_CHAINS.items():
        chains.append({
            "chain_id": chain_id,
            "name": chain_info["name"],
            "status": chain_info["status"],
            "blockchain_url": chain_info["blockchain_url"],
            "token_symbol": chain_info["token_symbol"],
            "bridge_contract": chain_info.get("bridge_contract")
        })
    
    return {
        "chains": chains,
        "total_chains": len(chains),
        "active_chains": len([c for c in chains if c["status"] == "active"])
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
async def get_cross_chain_swaps(user_address: Optional[str] = None, status: Optional[str] = None):
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
        
        return {
            "swaps": swaps,
            "total_swaps": len(swaps)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get swaps: {str(e)}")

@app.post("/api/v1/cross-chain/bridge")
async def create_bridge_transaction(bridge_request: BridgeRequest):
    """Create bridge transaction"""
    try:
        if bridge_request.source_chain == bridge_request.target_chain:
            raise HTTPException(status_code=400, detail="Cannot bridge to same chain")
        
        bridge_id = str(uuid.uuid4())
        bridge_fee = bridge_request.amount * 0.001  # 0.1% bridge fee
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO bridge_transactions 
            (bridge_id, source_chain, target_chain, token, amount, recipient_address, bridge_fee)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (bridge_id, bridge_request.source_chain, bridge_request.target_chain, 
              bridge_request.token, bridge_request.amount, bridge_request.recipient_address, bridge_fee))
        
        conn.commit()
        conn.close()
        
        # Process bridge in background
        asyncio.create_task(process_bridge_transaction(bridge_id))
        
        return {
            "success": True,
            "bridge_id": bridge_id,
            "source_chain": bridge_request.source_chain,
            "target_chain": bridge_request.target_chain,
            "token": bridge_request.token,
            "amount": bridge_request.amount,
            "bridge_fee": bridge_fee,
            "status": "pending"
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
        
        # Update status
        cursor.execute("UPDATE bridge_transactions SET status = 'locked' WHERE bridge_id = ?", (bridge_id,))
        conn.commit()
        
        # Simulate bridge processing
        await asyncio.sleep(2)
        
        # Generate mock transaction hashes
        source_tx_hash = f"0x{uuid.uuid4().hex[:64]}"
        target_tx_hash = f"0x{uuid.uuid4().hex[:64]}"
        
        # Complete bridge
        cursor.execute('''
            UPDATE bridge_transactions SET status = 'completed', 
            source_tx_hash = ?, target_tx_hash = ?, completed_at = CURRENT_TIMESTAMP 
            WHERE bridge_id = ?
        ''', (source_tx_hash, target_tx_hash, bridge_id))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Bridge processing error: {e}")

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
    
    return {
        "rates": rates,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/v1/cross-chain/pools")
async def get_cross_chain_pools():
    """Get cross-chain liquidity pools"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM cross_chain_pools ORDER BY total_liquidity DESC")
        pools = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "pools": pools,
            "total_pools": len(pools)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get pools: {str(e)}")

@app.get("/api/v1/cross-chain/stats")
async def get_cross_chain_stats():
    """Get cross-chain trading statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Swap stats
        cursor.execute('''
            SELECT status, COUNT(*) as count, SUM(amount) as volume
            FROM cross_chain_swaps 
            GROUP BY status
        ''')
        swap_stats = [dict(row) for row in cursor.fetchall()]
        
        # Bridge stats
        cursor.execute('''
            SELECT status, COUNT(*) as count, SUM(amount) as volume
            FROM bridge_transactions 
            GROUP BY status
        ''')
        bridge_stats = [dict(row) for row in cursor.fetchall()]
        
        # Total volume
        cursor.execute("SELECT SUM(amount) FROM cross_chain_swaps WHERE status = 'completed'")
        total_volume = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            "swap_stats": swap_stats,
            "bridge_stats": bridge_stats,
            "total_volume": total_volume,
            "supported_chains": list(SUPPORTED_CHAINS.keys()),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

if __name__ == "__main__":
    # Initialize database
    if init_database():
        print("✅ Complete cross-chain database initialized")
    else:
        print("❌ Database initialization failed")
    
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=8001)
