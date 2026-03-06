#!/usr/bin/env python3
"""
Simple Multi-Chain Wallet Daemon

Minimal implementation to test CLI integration without Pydantic issues.
"""

import json
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from typing import Dict, Any, List
from datetime import datetime

# Create FastAPI app
app = FastAPI(title="AITBC Wallet Daemon - Simple", debug=False)

# Mock data
chains_data = {
    "chains": [
        {
            "chain_id": "ait-devnet",
            "name": "AITBC Development Network",
            "status": "active",
            "coordinator_url": "http://localhost:8001",
            "blockchain_url": "http://localhost:8007",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "wallet_count": 0,
            "recent_activity": 0
        },
        {
            "chain_id": "ait-testnet",
            "name": "AITBC Test Network",
            "status": "inactive",
            "coordinator_url": "http://localhost:8001",
            "blockchain_url": None,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "wallet_count": 0,
            "recent_activity": 0
        }
    ],
    "total_chains": 2,
    "active_chains": 1
}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse({
        "status": "ok",
        "env": "dev",
        "python_version": "3.13.5",
        "multi_chain": True
    })

@app.get("/v1/chains")
async def list_chains():
    """List all blockchain chains"""
    return JSONResponse(chains_data)

@app.post("/v1/chains")
async def create_chain():
    """Create a new blockchain chain"""
    # For now, just return the current chains
    return JSONResponse(chains_data)

@app.get("/v1/chains/{chain_id}/wallets")
async def list_chain_wallets(chain_id: str):
    """List wallets in a specific chain"""
    return JSONResponse({
        "chain_id": chain_id,
        "wallets": [],
        "count": 0,
        "mode": "daemon"
    })

@app.post("/v1/chains/{chain_id}/wallets")
async def create_chain_wallet(chain_id: str):
    """Create a wallet in a specific chain"""
    # Chain-specific wallet addresses - different chains have different addresses
    chain_addresses = {
        "ait-devnet": "ait-devnet-1a2b3c4d5e6f7890abcdef1234567890abcdef12",
        "ait-testnet": "ait-testnet-9f8e7d6c5b4a3210fedcba9876543210fedcba98",
        "mainnet": "ait-mainnet-0123456789abcdef0123456789abcdef01234567"
    }
    
    wallet_data = {
        "mode": "daemon",
        "chain_id": chain_id,
        "wallet_name": "test-wallet",
        "public_key": f"test-public-key-{chain_id}",
        "address": chain_addresses.get(chain_id, f"unknown-address-{chain_id}"),
        "created_at": datetime.now().isoformat(),
        "metadata": {
            "chain_specific": True,
            "token_symbol": f"AITBC-{chain_id.upper()}"
        }
    }
    return JSONResponse(wallet_data)

@app.get("/v1/chains/{chain_id}/wallets/{wallet_id}")
async def get_chain_wallet_info(chain_id: str, wallet_id: str):
    """Get wallet information from a specific chain"""
    # Chain-specific wallet addresses
    chain_addresses = {
        "ait-devnet": "ait-devnet-1a2b3c4d5e6f7890abcdef1234567890abcdef12",
        "ait-testnet": "ait-testnet-9f8e7d6c5b4a3210fedcba9876543210fedcba98",
        "mainnet": "ait-mainnet-0123456789abcdef0123456789abcdef01234567"
    }
    
    wallet_data = {
        "mode": "daemon",
        "chain_id": chain_id,
        "wallet_name": wallet_id,
        "public_key": f"test-public-key-{chain_id}",
        "address": chain_addresses.get(chain_id, f"unknown-address-{chain_id}"),
        "created_at": datetime.now().isoformat(),
        "metadata": {
            "chain_specific": True,
            "token_symbol": f"AITBC-{chain_id.upper()}"
        }
    }
    return JSONResponse(wallet_data)

@app.post("/v1/chains/{chain_id}/wallets/{wallet_id}/unlock")
async def unlock_chain_wallet(chain_id: str, wallet_id: str):
    """Unlock a wallet in a specific chain"""
    return JSONResponse({
        "wallet_id": wallet_id,
        "chain_id": chain_id,
        "unlocked": True
    })

@app.post("/v1/chains/{chain_id}/wallets/{wallet_id}/sign")
async def sign_chain_message(chain_id: str, wallet_id: str):
    """Sign a message with a wallet in a specific chain"""
    return JSONResponse({
        "wallet_id": wallet_id,
        "chain_id": chain_id,
        "signature_base64": "dGVzdC1zaWduYXR1cmU="
    })

@app.get("/v1/chains/{chain_id}/wallets/{wallet_id}/balance")
async def get_chain_wallet_balance(chain_id: str, wallet_id: str):
    """Get wallet balance in a specific chain"""
    # Chain-specific balances - different chains have different balances
    chain_balances = {
        "ait-devnet": 100.5,
        "ait-testnet": 0.0,  # Different balance on testnet
        "mainnet": 0.0
    }
    
    balance = chain_balances.get(chain_id, 0.0)
    
    return JSONResponse({
        "chain_id": chain_id,
        "wallet_name": wallet_id,
        "balance": balance,
        "mode": "daemon",
        "token_symbol": f"AITBC-{chain_id.upper()}",  # Chain-specific token symbol
        "chain_isolated": True
    })

@app.post("/v1/wallets/migrate")
async def migrate_wallet():
    """Migrate a wallet from one chain to another"""
    return JSONResponse({
        "success": True,
        "source_wallet": {
            "chain_id": "ait-devnet",
            "wallet_id": "test-wallet",
            "public_key": "test-public-key",
            "address": "test-address"
        },
        "target_wallet": {
            "chain_id": "ait-testnet",
            "wallet_id": "test-wallet",
            "public_key": "test-public-key",
            "address": "test-address"
        },
        "migration_timestamp": datetime.now().isoformat()
    })

# Existing wallet endpoints (mock)
@app.get("/v1/wallets")
async def list_wallets():
    """List all wallets"""
    return JSONResponse({"items": []})

@app.post("/v1/wallets")
async def create_wallet():
    """Create a wallet"""
    return JSONResponse({"wallet_id": "test-wallet", "public_key": "test-key"})

@app.post("/v1/wallets/{wallet_id}/unlock")
async def unlock_wallet(wallet_id: str):
    """Unlock a wallet"""
    return JSONResponse({"wallet_id": wallet_id, "unlocked": True})

@app.post("/v1/wallets/{wallet_id}/sign")
async def sign_wallet(wallet_id: str):
    """Sign a message"""
    return JSONResponse({"wallet_id": wallet_id, "signature_base64": "dGVzdC1zaWduYXR1cmU="})

if __name__ == "__main__":
    print("Starting Simple Multi-Chain Wallet Daemon")
    print("Multi-chain endpoints are now available!")
    print("Available endpoints:")
    print("  GET  /health")
    print("  GET  /v1/chains")
    print("  POST /v1/chains")
    print("  GET  /v1/chains/{chain_id}/wallets")
    print("  POST /v1/chains/{chain_id}/wallets")
    print("  POST /v1/wallets/migrate")
    print("  And more...")
    
    uvicorn.run(app, host="0.0.0.0", port=8003, log_level="info")
