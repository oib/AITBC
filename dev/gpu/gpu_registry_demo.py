#!/usr/bin/env python3
"""
Simple GPU Registry Server for demonstration
"""

from datetime import UTC, datetime
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="GPU Registry Demo")

# In-memory storage
registered_gpus: dict[str, dict] = {}


class GPURegistration(BaseModel):
    capabilities: dict[str, Any]
    concurrency: int = 1
    region: str | None = None


class Heartbeat(BaseModel):
    inflight: int = 0
    status: str = "ONLINE"
    metadata: dict[str, Any] = {}


@app.get("/")
async def root():
    return {"message": "GPU Registry Demo", "registered_gpus": len(registered_gpus)}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/miners/register")
async def register_gpu(miner_id: str, gpu_data: GPURegistration):
    """Register a GPU miner"""
    registered_gpus[miner_id] = {
        "id": miner_id,
        "registered_at": datetime.now(UTC).isoformat(),
        "last_heartbeat": datetime.now(UTC).isoformat(),
        **gpu_data.dict(),
    }
    return {"status": "ok", "message": f"GPU {miner_id} registered successfully"}


@app.post("/miners/heartbeat")
async def heartbeat(miner_id: str, heartbeat_data: Heartbeat):
    """Receive heartbeat from GPU miner"""
    if miner_id not in registered_gpus:
        raise HTTPException(status_code=404, detail="GPU not registered")

    registered_gpus[miner_id]["last_heartbeat"] = datetime.now(UTC).isoformat()
    registered_gpus[miner_id]["status"] = heartbeat_data.status
    registered_gpus[miner_id]["metadata"] = heartbeat_data.metadata

    return {"status": "ok"}


@app.get("/miners/list")
async def list_gpus():
    """List all registered GPUs"""
    return {"gpus": list(registered_gpus.values())}


@app.get("/miners/{miner_id}")
async def get_gpu(miner_id: str):
    """Get details of a specific GPU"""
    if miner_id not in registered_gpus:
        raise HTTPException(status_code=404, detail="GPU not registered")
    return registered_gpus[miner_id]


if __name__ == "__main__":
    print("Starting GPU Registry Demo on http://localhost:8091")
    uvicorn.run(app, host="0.0.0.0", port=8091)
