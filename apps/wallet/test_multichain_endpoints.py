#!/usr/bin/env python3
"""
Test Multi-Chain Endpoints

This script creates a minimal FastAPI app to test the multi-chain endpoints
without the complex dependencies that are causing issues.
"""

import json
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel

# Mock data for testing
chains_data = {
    "chains": [
        {
            "chain_id": "ait-devnet",
            "name": "AITBC Development Network",
            "status": "active",
            "coordinator_url": "http://localhost:8011",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "wallet_count": 0,
            "recent_activity": 0
        },
        {
            "chain_id": "ait-testnet",
            "name": "AITBC Test Network",
            "status": "active",
            "coordinator_url": "http://localhost:8012",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "wallet_count": 0,
            "recent_activity": 0
        }
    ],
    "total_chains": 2,
    "active_chains": 2
}

# Pydantic models
class ChainInfo(BaseModel):
    chain_id: str
    name: str
    status: str
    coordinator_url: str
    created_at: str
    updated_at: str
    wallet_count: int
    recent_activity: int

class ChainListResponse(BaseModel):
    chains: List[ChainInfo]
    total_chains: int
    active_chains: int

class WalletDescriptor(BaseModel):
    wallet_id: str
    chain_id: str
    public_key: str
    address: Optional[str] = None
    metadata: Dict[str, Any] = {}

class WalletListResponse(BaseModel):
    items: List[WalletDescriptor]

class WalletCreateRequest(BaseModel):
    chain_id: str
    wallet_id: str
    password: str
    metadata: Dict[str, Any] = {}

class WalletCreateResponse(BaseModel):
    wallet: WalletDescriptor

# Create FastAPI app
app = FastAPI(title="AITBC Wallet Daemon - Multi-Chain Test", debug=True)

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "env": "dev",
        "python_version": "3.13.5",
        "multi_chain": True
    }

# Multi-Chain endpoints
@app.get("/v1/chains", response_model=ChainListResponse)
async def list_chains():
    """List all blockchain chains"""
    return ChainListResponse(
        chains=[ChainInfo(**chain) for chain in chains_data["chains"]],
        total_chains=chains_data["total_chains"],
        active_chains=chains_data["active_chains"]
    )

@app.post("/v1/chains", response_model=ChainListResponse)
async def create_chain(chain_data: dict):
    """Create a new blockchain chain"""
    new_chain = {
        "chain_id": chain_data.get("chain_id"),
        "name": chain_data.get("name"),
        "status": "active",
        "coordinator_url": chain_data.get("coordinator_url"),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "wallet_count": 0,
        "recent_activity": 0
    }
    
    chains_data["chains"].append(new_chain)
    chains_data["total_chains"] += 1
    chains_data["active_chains"] += 1
    
    return ChainListResponse(
        chains=[ChainInfo(**chain) for chain in chains_data["chains"]],
        total_chains=chains_data["total_chains"],
        active_chains=chains_data["active_chains"]
    )

@app.get("/v1/chains/{chain_id}/wallets", response_model=WalletListResponse)
async def list_chain_wallets(chain_id: str):
    """List wallets in a specific chain"""
    # Return empty list for now
    return WalletListResponse(items=[])

@app.post("/v1/chains/{chain_id}/wallets", response_model=WalletCreateResponse)
async def create_chain_wallet(chain_id: str, request: WalletCreateRequest):
    """Create a wallet in a specific chain"""
    wallet = WalletDescriptor(
        wallet_id=request.wallet_id,
        chain_id=chain_id,
        public_key="test-public-key",
        address="test-address",
        metadata=request.metadata
    )
    
    return WalletCreateResponse(wallet=wallet)

@app.get("/v1/chains/{chain_id}/wallets/{wallet_id}")
async def get_chain_wallet_info(chain_id: str, wallet_id: str):
    """Get wallet information from a specific chain"""
    return WalletDescriptor(
        wallet_id=wallet_id,
        chain_id=chain_id,
        public_key="test-public-key",
        address="test-address"
    )

@app.post("/v1/chains/{chain_id}/wallets/{wallet_id}/unlock")
async def unlock_chain_wallet(chain_id: str, wallet_id: str, request: dict):
    """Unlock a wallet in a specific chain"""
    return {"wallet_id": wallet_id, "chain_id": chain_id, "unlocked": True}

@app.post("/v1/chains/{chain_id}/wallets/{wallet_id}/sign")
async def sign_chain_message(chain_id: str, wallet_id: str, request: dict):
    """Sign a message with a wallet in a specific chain"""
    return {
        "wallet_id": wallet_id,
        "chain_id": chain_id,
        "signature_base64": "dGVzdC1zaWduYXR1cmU="  # base64 "test-signature"
    }

@app.post("/v1/wallets/migrate")
async def migrate_wallet(request: dict):
    """Migrate a wallet from one chain to another"""
    return {
        "success": True,
        "source_wallet": {
            "chain_id": request.get("source_chain_id"),
            "wallet_id": request.get("wallet_id"),
            "public_key": "test-public-key",
            "address": "test-address"
        },
        "target_wallet": {
            "chain_id": request.get("target_chain_id"),
            "wallet_id": request.get("wallet_id"),
            "public_key": "test-public-key",
            "address": "test-address"
        },
        "migration_timestamp": datetime.now().isoformat()
    }

# Existing wallet endpoints (mock)
@app.get("/v1/wallets")
async def list_wallets():
    """List all wallets"""
    return {"items": []}

@app.post("/v1/wallets")
async def create_wallet(request: dict):
    """Create a wallet"""
    return {"wallet_id": request.get("wallet_id"), "public_key": "test-key"}

@app.post("/v1/wallets/{wallet_id}/unlock")
async def unlock_wallet(wallet_id: str, request: dict):
    """Unlock a wallet"""
    return {"wallet_id": wallet_id, "unlocked": True}

@app.post("/v1/wallets/{wallet_id}/sign")
async def sign_wallet(wallet_id: str, request: dict):
    """Sign a message"""
    return {"wallet_id": wallet_id, "signature_base64": "dGVzdC1zaWduYXR1cmU="}

if __name__ == "__main__":
    print("Starting Multi-Chain Wallet Daemon Test Server")
    print("Available endpoints:")
    print("  GET  /health")
    print("  GET  /v1/chains")
    print("  POST /v1/chains")
    print("  GET  /v1/chains/{chain_id}/wallets")
    print("  POST /v1/chains/{chain_id}/wallets")
    print("  POST /v1/wallets/migrate")
    print("  And more...")
    
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="info")
