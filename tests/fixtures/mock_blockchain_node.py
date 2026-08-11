#!/usr/bin/env python3
"""
Mock blockchain node server for testing purposes.
Implements the minimal API endpoints required by the test suite.
"""

import time
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Create FastAPI app
app = FastAPI(title="Mock Blockchain Node", version="0.1.0")

# Mock state
mock_chain_state = {
    "height": 100,
    "hash": "0xabcdef1234567890",
    "balances": {
        "aitbc1alice00000000000000000000000000000000000": 1000,
        "aitbc1bob0000000000000000000000000000000000000": 500,
        "aitbc1charl0000000000000000000000000000000000": 100,
    },
    "transactions": [],
}


@app.get("/openapi.json")
async def openapi():
    """Return OpenAPI spec"""
    return {"openapi": "3.0.0", "info": {"title": "AITBC Blockchain API", "version": "0.1.0"}, "paths": {}}


@app.get("/rpc/head")
async def get_chain_head():
    """Get current chain head"""
    return JSONResponse(mock_chain_state)


@app.get("/rpc/balance/{address}")
async def get_balance(address: str):
    """Balance breakdown for an address, in compute-seconds.

    V23-42: this served `/rpc/getBalance/{address}` returning `{"balance": n}` — a route and a
    shape the real node has never had. It matched the coordinator's client, which is the wrong
    thing for a mock to match: the client and the mock agreed with each other and neither
    agreed with the server, so the suite was green against a fiction.
    """
    balance = mock_chain_state["balances"].get(address, 0)
    return JSONResponse(
        {
            "address": address,
            "available_balance": balance,
            "staked": 0,
            "bridge_locked": 0,
            "total_balance": balance,
        }
    )


@app.post("/rpc/faucet")
async def faucet(request: dict[str, Any]):
    """Mint test tokens to an address (devnet only). Was `/rpc/admin/mintFaucet` — see above."""
    address = request.get("address")
    amount = request.get("amount", 3600000000)

    if address in mock_chain_state["balances"]:
        mock_chain_state["balances"][address] += amount
    else:
        mock_chain_state["balances"][address] = amount

    return JSONResponse(
        {
            "success": True,
            "address": address,
            "amount": amount,
            "tx_hash": f"0x{abs(hash((address, amount))):064x}"[:66],
            "message": "Faucet transaction completed",
        }
    )


@app.post("/rpc/transaction")
async def send_transaction(request: dict[str, Any]):
    """Submit a transaction. Was `/rpc/sendTx`, returning `tx_hash` — neither is what the node
    does: the route is `/rpc/transaction` and the key is `transaction_hash`, which is what
    `cli/aitbc_cli/commands/transactions.py` reads back."""
    # Generate mock transaction hash
    tx_hash = f"0x{hash(str(request)) % 1000000000000000000000000000000000000000000000000000000000000000:x}"

    # Add to transactions list
    mock_chain_state["transactions"].append(
        {"hash": tx_hash, "type": request.get("type", "TRANSFER"), "sender": request.get("sender"), "timestamp": time.time()}
    )

    return JSONResponse({"success": True, "transaction_hash": tx_hash, "message": "Transaction submitted to mempool"})


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
