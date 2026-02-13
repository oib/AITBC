#!/usr/bin/env python3
"""
Mock blockchain node server for testing purposes.
Implements the minimal API endpoints required by the test suite.
"""

import json
import threading
import time
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

# Create FastAPI app
app = FastAPI(title="Mock Blockchain Node", version="0.1.0")

# Mock state
mock_chain_state = {
    "height": 100,
    "hash": "0xabcdef1234567890",
    "balances": {
        "aitbc1alice00000000000000000000000000000000000": 1000,
        "aitbc1bob0000000000000000000000000000000000000": 500,
        "aitbc1charl0000000000000000000000000000000000": 100
    },
    "transactions": []
}

@app.get("/openapi.json")
async def openapi():
    """Return OpenAPI spec"""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "AITBC Blockchain API",
            "version": "0.1.0"
        },
        "paths": {}
    }

@app.get("/rpc/head")
async def get_chain_head():
    """Get current chain head"""
    return JSONResponse(mock_chain_state)

@app.get("/rpc/getBalance/{address}")
async def get_balance(address: str):
    """Get balance for an address"""
    balance = mock_chain_state["balances"].get(address, 0)
    return JSONResponse({"balance": balance})

@app.post("/rpc/admin/mintFaucet")
async def mint_faucet(request: Dict[str, Any]):
    """Mint tokens to an address (devnet only)"""
    address = request.get("address")
    amount = request.get("amount", 0)
    
    if address in mock_chain_state["balances"]:
        mock_chain_state["balances"][address] += amount
    else:
        mock_chain_state["balances"][address] = amount
    
    return JSONResponse({"success": True, "new_balance": mock_chain_state["balances"][address]})

@app.post("/rpc/sendTx")
async def send_transaction(request: Dict[str, Any]):
    """Send a transaction"""
    # Generate mock transaction hash
    tx_hash = f"0x{hash(str(request)) % 1000000000000000000000000000000000000000000000000000000000000000:x}"
    
    # Add to transactions list
    mock_chain_state["transactions"].append({
        "hash": tx_hash,
        "type": request.get("type", "TRANSFER"),
        "sender": request.get("sender"),
        "timestamp": time.time()
    })
    
    return JSONResponse({"tx_hash": tx_hash, "status": "pending"})

@app.get("/health")
async def health():
    """Health check endpoint"""
    return JSONResponse({"status": "ok", "height": mock_chain_state["height"]})

def run_mock_server(port: int):
    """Run the mock server on specified port"""
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    print(f"Starting mock blockchain node on port {port}")
    run_mock_server(port)
