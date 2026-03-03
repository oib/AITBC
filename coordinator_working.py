#!/usr/bin/env python3
"""
Simple working coordinator API for GPU miner
"""

import logging
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
from pydantic import BaseModel
import time

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AITBC Coordinator API - Working",
    version="0.1.0",
    description="Simple working coordinator service for GPU miner",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"]
)

# Simple in-memory storage
miners: Dict[str, Dict[str, Any]] = {}
jobs: Dict[str, Dict[str, Any]] = {}

# Pydantic models
class MinerRegister(BaseModel):
    miner_id: str
    capabilities: list[str] = []
    region: str = "default"
    concurrency: int = 1

class MinerHeartbeat(BaseModel):
    miner_id: str
    status: str = "online"
    inflight: int = 0

class JobSubmit(BaseModel):
    prompt: str
    model: str = "gemma3:1b"
    priority: str = "normal"

# Basic auth (simple for testing)
API_KEY = "miner_test"

def verify_api_key(api_key: Optional[str] = Header(None), x_api_key: Optional[str] = Header(None)):
    key = api_key or x_api_key
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")
    return key

@app.get("/health", tags=["health"], summary="Service healthcheck")
async def health() -> dict[str, str]:
    """Health check endpoint"""
    return {"status": "ok", "service": "coordinator-api"}

@app.get("/v1/health", tags=["health"], summary="Service healthcheck")
async def health_v1() -> dict[str, str]:
    """Health check endpoint v1"""
    return {"status": "ok", "service": "coordinator-api"}

@app.post("/v1/miners/register", tags=["miner"], summary="Register or update miner")
async def register_miner(
    request: dict,
    api_key: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    miner_id: Optional[str] = None
) -> dict[str, str]:
    """Register a miner"""
    key = api_key or x_api_key
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")
    
    # Get miner_id from query parameter or request body
    mid = miner_id or request.get("miner_id", "miner_test")
    
    # Register the miner with simple data
    miners[mid] = {
        "id": mid,
        "capabilities": ["gpu"],
        "region": request.get("region", "localhost"),
        "concurrency": request.get("concurrency", 1),
        "status": "online",
        "inflight": 0,
        "last_heartbeat": time.time(),
        "session_token": f"token_{mid}_{int(time.time())}"
    }
    
    logger.info(f"Miner {mid} registered")
    return {"status": "ok", "session_token": miners[mid]["session_token"]}

@app.post("/v1/miners/heartbeat", tags=["miner"], summary="Send miner heartbeat")
async def miner_heartbeat(
    request: dict,
    api_key: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    miner_id: Optional[str] = None
) -> dict[str, str]:
    """Receive miner heartbeat"""
    key = api_key or x_api_key
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")
    
    # Get miner_id from query parameter or request body
    mid = miner_id or request.get("miner_id", "miner_test")
    
    if mid not in miners:
        raise HTTPException(status_code=404, detail="miner not registered")
    
    miners[mid].update({
        "status": request.get("status", "online"),
        "inflight": request.get("current_jobs", 0),
        "last_heartbeat": time.time()
    })
    
    return {"status": "ok"}

@app.post("/v1/miners/poll", tags=["miner"], summary="Poll for next job")
async def poll_for_job(
    request: dict,
    api_key: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    miner_id: Optional[str] = None
) -> Dict[str, Any]:
    """Poll for next job"""
    key = api_key or x_api_key
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")
    
    # For now, return no jobs (empty response)
    return {"status": "no_jobs"}

@app.get("/", tags=["root"], summary="Root endpoint")
async def root() -> dict[str, str]:
    """Root endpoint"""
    return {"service": "AITBC Coordinator API", "status": "running"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting working coordinator API on port 9080")
    uvicorn.run(app, host="127.0.0.1", port=9080)
