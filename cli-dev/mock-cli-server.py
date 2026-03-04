#!/usr/bin/env python3

"""
CLI Mock Server for Testing
Provides mock responses for CLI testing without affecting production
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
import json
from datetime import datetime

app = FastAPI(title="CLI Mock Server", version="1.0.0")

@app.get("/health")
async def mock_health():
    return {
        "status": "healthy",
        "service": "coordinator-api",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/v1/health")
async def mock_v1_health():
    return {
        "status": "ok",
        "env": "development",
        "python_version": "3.13.5"
    }

@app.get("/v1/marketplace/gpus")
async def mock_marketplace_gpus():
    return [
        {
            "id": "gpu-001",
            "model": "NVIDIA-RTX-4060Ti",
            "memory": "16GB",
            "price_per_hour": 0.001,
            "available": True,
            "miner_id": "test-miner-001"
        },
        {
            "id": "gpu-002", 
            "model": "NVIDIA-RTX-3080",
            "memory": "10GB",
            "price_per_hour": 0.002,
            "available": False,
            "miner_id": "test-miner-002"
        }
    ]

@app.get("/v1/marketplace/offers")
async def mock_marketplace_offers():
    return [
        {
            "id": "offer-001",
            "gpu_id": "gpu-001",
            "price": 0.001,
            "miner_id": "test-miner-001",
            "status": "active"
        }
    ]

@app.get("/v1/agent/workflows")
async def mock_agent_workflows():
    return [
        {
            "id": "workflow-001",
            "name": "test-workflow",
            "status": "running",
            "created_at": datetime.now().isoformat()
        }
    ]

@app.get("/v1/blockchain/status")
async def mock_blockchain_status():
    return {
        "status": "connected",
        "height": 12345,
        "hash": "0x1234567890abcdef",
        "timestamp": datetime.now().isoformat(),
        "tx_count": 678
    }

if __name__ == "__main__":
    print("Starting CLI Mock Server on port 8001...")
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
