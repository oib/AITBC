#!/usr/bin/env python3
"""
AITBC Agent-First GPU Marketplace
Miners register GPU offerings, choose chains, and confirm deals
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI(
    title="AITBC Agent-First GPU Marketplace",
    description="GPU trading marketplace where miners register offerings and confirm deals",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage (replace with database in production)
gpu_offerings = {}
marketplace_deals = {}
miner_registrations = {}
chain_offerings = {}

# Supported chains
SUPPORTED_CHAINS = ["ait-devnet", "ait-testnet", "ait-mainnet"]

class GPUOffering(BaseModel):
    miner_id: str
    gpu_model: str
    gpu_memory: int
    cuda_cores: int
    price_per_hour: float
    available_hours: int
    chains: List[str]
    capabilities: List[str]
    min_rental_hours: int = 1
    max_concurrent_jobs: int = 1

class DealRequest(BaseModel):
    offering_id: str
    buyer_id: str
    rental_hours: int
    chain: str
    special_requirements: Optional[str] = None

class DealConfirmation(BaseModel):
    deal_id: str
    miner_confirmation: bool
    chain: str

class MinerRegistration(BaseModel):
    miner_id: str
    wallet_address: str
    preferred_chains: List[str]
    gpu_specs: Dict[str, Any]
    pricing_model: str = "hourly"

@app.get("/health")
async def health_check():
    return JSONResponse({
        "status": "ok",
        "service": "agent-marketplace",
        "version": "1.0.0",
        "supported_chains": SUPPORTED_CHAINS,
        "total_offerings": len(gpu_offerings),
        "active_deals": len([d for d in marketplace_deals.values() if d["status"] == "active"]),
        "timestamp": datetime.now().isoformat()
    })

@app.get("/api/v1/chains")
async def get_supported_chains():
    return JSONResponse({
        "chains": [
            {
                "chain_id": chain,
                "name": chain.replace("ait-", "").upper(),
                "status": "active" if chain == "ait-devnet" else "available",
                "offerings_count": len([o for o in gpu_offerings.values() if chain in o["chains"]])
            }
            for chain in SUPPORTED_CHAINS
        ]
    })

@app.post("/api/v1/miners/register")
async def register_miner(registration: MinerRegistration):
    """Register a miner in the marketplace"""
    miner_id = registration.miner_id
    
    if miner_id in miner_registrations:
        # Update existing registration
        miner_registrations[miner_id].update(registration.model_dump())
    else:
        # New registration
        miner_registrations[miner_id] = registration.model_dump()
        miner_registrations[miner_id]["registered_at"] = datetime.now().isoformat()
    
    return JSONResponse({
        "success": True,
        "miner_id": miner_id,
        "status": "registered",
        "registered_chains": registration.preferred_chains,
        "message": "Miner registered successfully in marketplace"
    })

@app.post("/api/v1/offerings/create")
async def create_gpu_offering(offering: GPUOffering):
    """Miners create GPU offerings with chain selection"""
    offering_id = str(uuid.uuid4())
    
    # Validate chains
    invalid_chains = [c for c in offering.chains if c not in SUPPORTED_CHAINS]
    if invalid_chains:
        raise HTTPException(status_code=400, detail=f"Invalid chains: {invalid_chains}")
    
    # Store offering
    gpu_offerings[offering_id] = {
        "offering_id": offering_id,
        "created_at": datetime.now().isoformat(),
        "status": "available",
        **offering.model_dump()
    }
    
    # Update chain offerings
    for chain in offering.chains:
        if chain not in chain_offerings:
            chain_offerings[chain] = []
        chain_offerings[chain].append(offering_id)
    
    return JSONResponse({
        "success": True,
        "offering_id": offering_id,
        "status": "created",
        "chains": offering.chains,
        "price_per_hour": offering.price_per_hour,
        "message": "GPU offering created successfully"
    })

@app.get("/api/v1/offerings")
async def get_gpu_offerings(chain: Optional[str] = None, gpu_model: Optional[str] = None):
    """Get available GPU offerings, filtered by chain and model"""
    filtered_offerings = gpu_offerings.copy()
    
    if chain:
        filtered_offerings = {
            k: v for k, v in filtered_offerings.items()
            if chain in v["chains"] and v["status"] == "available"
        }
    
    if gpu_model:
        filtered_offerings = {
            k: v for k, v in filtered_offerings.items()
            if gpu_model.lower() in v["gpu_model"].lower()
        }
    
    return JSONResponse({
        "offerings": list(filtered_offerings.values()),
        "total_count": len(filtered_offerings),
        "filters": {
            "chain": chain,
            "gpu_model": gpu_model
        }
    })

@app.get("/api/v1/offerings/{offering_id}")
async def get_gpu_offering(offering_id: str):
    """Get specific GPU offering details"""
    if offering_id not in gpu_offerings:
        raise HTTPException(status_code=404, detail="Offering not found")
    
    offering = gpu_offerings[offering_id]
    return JSONResponse(offering)

@app.post("/api/v1/deals/request")
async def request_deal(deal_request: DealRequest):
    """Buyers request GPU deals"""
    offering_id = deal_request.offering_id
    
    if offering_id not in gpu_offerings:
        raise HTTPException(status_code=404, detail="GPU offering not found")
    
    offering = gpu_offerings[offering_id]
    
    if offering["status"] != "available":
        raise HTTPException(status_code=400, detail="GPU offering not available")
    
    if deal_request.chain not in offering["chains"]:
        raise HTTPException(status_code=400, detail="Chain not supported by this offering")
    
    # Calculate total cost
    total_cost = offering["price_per_hour"] * deal_request.rental_hours
    
    # Create deal
    deal_id = str(uuid.uuid4())
    marketplace_deals[deal_id] = {
        "deal_id": deal_id,
        "offering_id": offering_id,
        "buyer_id": deal_request.buyer_id,
        "miner_id": offering["miner_id"],
        "chain": deal_request.chain,
        "rental_hours": deal_request.rental_hours,
        "total_cost": total_cost,
        "special_requirements": deal_request.special_requirements,
        "status": "pending_confirmation",
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=1)).isoformat()
    }
    
    return JSONResponse({
        "success": True,
        "deal_id": deal_id,
        "status": "pending_confirmation",
        "total_cost": total_cost,
        "expires_at": marketplace_deals[deal_id]["expires_at"],
        "message": "Deal request sent to miner for confirmation"
    })

@app.post("/api/v1/deals/{deal_id}/confirm")
async def confirm_deal(deal_id: str, confirmation: DealConfirmation):
    """Miners confirm or reject deal requests"""
    if deal_id not in marketplace_deals:
        raise HTTPException(status_code=404, detail="Deal not found")
    
    deal = marketplace_deals[deal_id]
    
    if deal["status"] != "pending_confirmation":
        raise HTTPException(status_code=400, detail="Deal cannot be confirmed")
    
    if confirmation.chain != deal["chain"]:
        raise HTTPException(status_code=400, detail="Chain mismatch")
    
    if confirmation.miner_confirmation:
        # Accept deal
        deal["status"] = "confirmed"
        deal["confirmed_at"] = datetime.now().isoformat()
        deal["starts_at"] = datetime.now().isoformat()
        deal["ends_at"] = (datetime.now() + timedelta(hours=deal["rental_hours"])).isoformat()
        
        # Update offering status
        offering_id = deal["offering_id"]
        if offering_id in gpu_offerings:
            gpu_offerings[offering_id]["status"] = "occupied"
        
        message = "Deal confirmed successfully"
    else:
        # Reject deal
        deal["status"] = "rejected"
        deal["rejected_at"] = datetime.now().isoformat()
        message = "Deal rejected by miner"
    
    return JSONResponse({
        "success": True,
        "deal_id": deal_id,
        "status": deal["status"],
        "miner_confirmation": confirmation.miner_confirmation,
        "message": message
    })

@app.get("/api/v1/deals")
async def get_deals(miner_id: Optional[str] = None, buyer_id: Optional[str] = None):
    """Get deals, filtered by miner or buyer"""
    filtered_deals = marketplace_deals.copy()
    
    if miner_id:
        filtered_deals = {
            k: v for k, v in filtered_deals.items()
            if v["miner_id"] == miner_id
        }
    
    if buyer_id:
        filtered_deals = {
            k: v for k, v in filtered_deals.items()
            if v["buyer_id"] == buyer_id
        }
    
    return JSONResponse({
        "deals": list(filtered_deals.values()),
        "total_count": len(filtered_deals)
    })

@app.get("/api/v1/miners/{miner_id}/offerings")
async def get_miner_offerings(miner_id: str):
    """Get all offerings for a specific miner"""
    miner_offerings = {
        k: v for k, v in gpu_offerings.items()
        if v["miner_id"] == miner_id
    }
    
    return JSONResponse({
        "miner_id": miner_id,
        "offerings": list(miner_offerings.values()),
        "total_count": len(miner_offerings)
    })

@app.get("/api/v1/chains/{chain}/offerings")
async def get_chain_offerings(chain: str):
    """Get all offerings for a specific chain"""
    if chain not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")
    
    chain_offering_ids = chain_offerings.get(chain, [])
    chain_offs = {
        k: v for k, v in gpu_offerings.items()
        if k in chain_offering_ids and v["status"] == "available"
    }
    
    return JSONResponse({
        "chain": chain,
        "offerings": list(chain_offs.values()),
        "total_count": len(chain_offs)
    })

@app.delete("/api/v1/offerings/{offering_id}")
async def remove_offering(offering_id: str):
    """Miners remove their GPU offerings"""
    if offering_id not in gpu_offerings:
        raise HTTPException(status_code=404, detail="Offering not found")
    
    offering = gpu_offerings[offering_id]
    
    # Remove from chain offerings
    for chain in offering["chains"]:
        if chain in chain_offerings and offering_id in chain_offerings[chain]:
            chain_offerings[chain].remove(offering_id)
    
    # Remove offering
    del gpu_offerings[offering_id]
    
    return JSONResponse({
        "success": True,
        "message": "GPU offering removed successfully"
    })

@app.get("/api/v1/stats")
async def get_marketplace_stats():
    """Get marketplace statistics"""
    active_offerings = len([o for o in gpu_offerings.values() if o["status"] == "available"])
    active_deals = len([d for d in marketplace_deals.values() if d["status"] in ["confirmed", "active"]])
    
    chain_stats = {}
    for chain in SUPPORTED_CHAINS:
        chain_offerings = len([o for o in gpu_offerings.values() if chain in o["chains"] and o["status"] == "available"])
        chain_deals = len([d for d in marketplace_deals.values() if d["chain"] == chain and d["status"] in ["confirmed", "active"]])
        
        chain_stats[chain] = {
            "offerings": chain_offerings,
            "active_deals": chain_deals,
            "total_gpu_hours": sum([o["available_hours"] for o in gpu_offerings.values() if chain in o["chains"]])
        }
    
    return JSONResponse({
        "total_offerings": active_offerings,
        "active_deals": active_deals,
        "registered_miners": len(miner_registrations),
        "supported_chains": SUPPORTED_CHAINS,
        "chain_stats": chain_stats,
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005, log_level="info")
