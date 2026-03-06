#!/usr/bin/env python3
"""
Cross-Chain Trading Extension for Multi-Chain Exchange
Adds cross-chain trading, bridging, and swap functionality
"""

import sqlite3
import json
import asyncio
import httpx
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
import uuid
import hashlib

# Import the base multi-chain exchange
from multichain_exchange_api import app, get_db_connection, SUPPORTED_CHAINS

# Cross-Chain Models
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

class CrossChainOrder(BaseModel):
    order_type: str = Field(..., regex="^(BUY|SELL)$")
    amount: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    chain_id: str = Field(..., regex="^(ait-devnet|ait-testnet)$")
    cross_chain: bool = Field(default=True)
    target_chain: Optional[str] = None
    user_address: str = Field(..., min_length=1)

# Cross-Chain Database Functions
def init_cross_chain_tables():
    """Initialize cross-chain trading tables"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
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
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_swaps_user ON cross_chain_swaps(user_address)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_swaps_status ON cross_chain_swaps(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_swaps_chains ON cross_chain_swaps(from_chain, to_chain)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bridge_status ON bridge_transactions(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bridge_chains ON bridge_transactions(source_chain, target_chain)')
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Cross-chain database initialization error: {e}")
        return False

# Cross-Chain Liquidity Management
def get_cross_chain_rate(from_chain: str, to_chain: str, from_token: str, to_token: str) -> Optional[float]:
    """Get cross-chain exchange rate"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if there's a liquidity pool for this pair
        cursor.execute('''
            SELECT reserve_a, reserve_b FROM cross_chain_pools 
            WHERE ((chain_a = ? AND chain_b = ? AND token_a = ? AND token_b = ?) OR
                   (chain_a = ? AND chain_b = ? AND token_a = ? AND token_b = ?))
        ''', (from_chain, to_chain, from_token, to_token, to_chain, from_chain, to_token, from_token))
        
        pool = cursor.fetchone()
        if pool:
            reserve_a, reserve_b = pool
            if from_chain == SUPPORTED_CHAINS[from_chain] and reserve_a > 0 and reserve_b > 0:
                return reserve_b / reserve_a
        
        # Fallback to 1:1 rate for same tokens
        if from_token == to_token:
            return 1.0
            
        # Get rates from individual chains
        rate_a = get_chain_token_price(from_chain, from_token)
        rate_b = get_chain_token_price(to_chain, to_token)
        
        if rate_a and rate_b:
            return rate_b / rate_a
            
        return None
    except Exception as e:
        print(f"Rate calculation error: {e}")
        return None

def get_chain_token_price(chain_id: str, token: str) -> Optional[float]:
    """Get token price on specific chain"""
    try:
        chain_info = SUPPORTED_CHAINS.get(chain_id)
        if not chain_info or chain_info["status"] != "active":
            return None
            
        # Mock price for now - in production, this would call the chain's price oracle
        if token == "AITBC":
            return 1.0
        elif token == "USDC":
            return 1.0
        else:
            return 0.5  # Default fallback
    except:
        return None

# Cross-Chain Swap Functions
async def execute_cross_chain_swap(swap_request: CrossChainSwapRequest) -> Dict[str, Any]:
    """Execute cross-chain swap"""
    try:
        # Validate chains
        if swap_request.from_chain == swap_request.to_chain:
            raise HTTPException(status_code=400, detail="Cannot swap within same chain")
        
        if swap_request.from_chain not in SUPPORTED_CHAINS or swap_request.to_chain not in SUPPORTED_CHAINS:
            raise HTTPException(status_code=400, detail="Unsupported chain")
        
        # Get exchange rate
        rate = get_cross_chain_rate(swap_request.from_chain, swap_request.to_chain, 
                                  swap_request.from_token, swap_request.to_token)
        if not rate:
            raise HTTPException(status_code=400, detail="No exchange rate available")
        
        # Calculate expected amount
        expected_amount = swap_request.amount * rate * (1 - 0.003)  # 0.3% fee
        
        # Check slippage
        if expected_amount < swap_request.min_amount:
            raise HTTPException(status_code=400, detail="Insufficient output due to slippage")
        
        # Create swap record
        swap_id = str(uuid.uuid4())
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO cross_chain_swaps 
            (swap_id, from_chain, to_chain, from_token, to_token, amount, min_amount, expected_amount, user_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (swap_id, swap_request.from_chain, swap_request.to_chain, swap_request.from_token, 
              swap_request.to_token, swap_request.amount, swap_request.min_amount, expected_amount, 
              swap_request.user_address))
        
        conn.commit()
        conn.close()
        
        # Execute swap in background
        asyncio.create_task(process_cross_chain_swap(swap_id))
        
        return {
            "success": True,
            "swap_id": swap_id,
            "from_chain": swap_request.from_chain,
            "to_chain": swap_request.to_chain,
            "amount": swap_request.amount,
            "expected_amount": expected_amount,
            "rate": rate,
            "status": "pending"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Swap execution failed: {str(e)}")

async def process_cross_chain_swap(swap_id: str):
    """Process cross-chain swap in background"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get swap details
        cursor.execute("SELECT * FROM cross_chain_swaps WHERE swap_id = ?", (swap_id,))
        swap = cursor.fetchone()
        
        if not swap:
            return
        
        # Update status to executing
        cursor.execute("UPDATE cross_chain_swaps SET status = 'executing' WHERE swap_id = ?", (swap_id,))
        conn.commit()
        
        # Step 1: Lock funds on source chain
        from_tx_hash = await lock_funds_on_chain(swap["from_chain"], swap["from_token"], 
                                                swap["amount"], swap["user_address"])
        
        if not from_tx_hash:
            cursor.execute('''
                UPDATE cross_chain_swaps SET status = 'failed', error_message = ? 
                WHERE swap_id = ?
            ''', ("Failed to lock source funds", swap_id))
            conn.commit()
            return
        
        # Step 2: Transfer to target chain
        to_tx_hash = await transfer_to_target_chain(swap["to_chain"], swap["to_token"], 
                                                  swap["expected_amount"], swap["user_address"])
        
        if not to_tx_hash:
            # Refund source chain
            await refund_source_chain(swap["from_chain"], from_tx_hash, swap["user_address"])
            cursor.execute('''
                UPDATE cross_chain_swaps SET status = 'refunded', error_message = ?, 
                from_tx_hash = ? WHERE swap_id = ?
            ''', ("Target transfer failed, refunded", from_tx_hash, swap_id))
            conn.commit()
            return
        
        # Step 3: Complete swap
        actual_amount = await verify_target_transfer(swap["to_chain"], to_tx_hash)
        
        cursor.execute('''
            UPDATE cross_chain_swaps SET status = 'completed', actual_amount = ?, 
            from_tx_hash = ?, to_tx_hash = ?, completed_at = CURRENT_TIMESTAMP 
            WHERE swap_id = ?
        ''', (actual_amount, from_tx_hash, to_tx_hash, swap_id))
        conn.commit()
        
        conn.close()
        
    except Exception as e:
        print(f"Cross-chain swap processing error: {e}")

async def lock_funds_on_chain(chain_id: str, token: str, amount: float, user_address: str) -> Optional[str]:
    """Lock funds on source chain"""
    try:
        chain_info = SUPPORTED_CHAINS[chain_id]
        if chain_info["status"] != "active":
            return None
        
        # Mock implementation - in production, this would call the chain's lock function
        lock_tx_hash = f"lock_{uuid.uuid4().hex[:8]}"
        
        # Simulate blockchain call
        await asyncio.sleep(1)
        
        return lock_tx_hash
    except:
        return None

async def transfer_to_target_chain(chain_id: str, token: str, amount: float, user_address: str) -> Optional[str]:
    """Transfer tokens to target chain"""
    try:
        chain_info = SUPPORTED_CHAINS[chain_id]
        if chain_info["status"] != "active":
            return None
        
        # Mock implementation - in production, this would call the chain's mint/transfer function
        transfer_tx_hash = f"transfer_{uuid.uuid4().hex[:8]}"
        
        # Simulate blockchain call
        await asyncio.sleep(2)
        
        return transfer_tx_hash
    except:
        return None

async def refund_source_chain(chain_id: str, lock_tx_hash: str, user_address: str) -> bool:
    """Refund locked funds on source chain"""
    try:
        chain_info = SUPPORTED_CHAINS[chain_id]
        if chain_info["status"] != "active":
            return False
        
        # Mock implementation - in production, this would call the chain's refund function
        await asyncio.sleep(1)
        
        return True
    except:
        return False

async def verify_target_transfer(chain_id: str, tx_hash: str) -> Optional[float]:
    """Verify transfer on target chain"""
    try:
        chain_info = SUPPORTED_CHAINS[chain_id]
        if chain_info["status"] != "active":
            return None
        
        # Mock implementation - in production, this would verify the actual transaction
        await asyncio.sleep(1)
        
        return 100.0  # Mock amount
    except:
        return None

# Cross-Chain API Endpoints
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
async def create_bridge_transaction(bridge_request: BridgeRequest, background_tasks: BackgroundTasks):
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
            "amount": bridge_request.amount,
            "bridge_fee": bridge_fee,
            "status": "pending"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bridge creation failed: {str(e)}")

async def process_bridge_transaction(bridge_id: str):
    """Process bridge transaction in background"""
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
        
        # Lock on source chain
        source_tx_hash = await lock_funds_on_chain(bridge["source_chain"], bridge["token"], 
                                                  bridge["amount"], bridge["recipient_address"])
        
        if source_tx_hash:
            # Transfer to target chain
            target_tx_hash = await transfer_to_target_chain(bridge["target_chain"], bridge["token"], 
                                                          bridge["amount"], bridge["recipient_address"])
            
            if target_tx_hash:
                cursor.execute('''
                    UPDATE bridge_transactions SET status = 'completed', 
                    source_tx_hash = ?, target_tx_hash = ?, completed_at = CURRENT_TIMESTAMP 
                    WHERE bridge_id = ?
                ''', (source_tx_hash, target_tx_hash, bridge_id))
            else:
                cursor.execute('''
                    UPDATE bridge_transactions SET status = 'failed', error_message = ? 
                    WHERE bridge_id = ?
                ''', ("Target transfer failed", bridge_id))
        else:
            cursor.execute('''
                UPDATE bridge_transactions SET status = 'failed', error_message = ? 
                WHERE bridge_id = ?
            ''', ("Source lock failed", bridge_id))
        
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

# Initialize cross-chain tables
if __name__ == "__main__":
    init_cross_chain_tables()
    print("✅ Cross-chain trading extensions initialized")
