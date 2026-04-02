#!/usr/bin/env python3
"""
Production Marketplace Service
Real marketplace with database persistence and API
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, '/opt/aitbc/apps/coordinator-api/src')

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Production logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('/var/log/aitbc/production/marketplace/marketplace.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Pydantic models
class GPUListing(BaseModel):
    id: str
    provider: str
    gpu_type: str
    memory_gb: int
    price_per_hour: float
    status: str
    specs: dict

class Bid(BaseModel):
    id: str
    gpu_id: str
    agent_id: str
    bid_price: float
    duration_hours: int
    total_cost: float
    status: str

class ProductionMarketplace:
    """Production-grade marketplace with persistence"""
    
    def __init__(self):
        self.data_dir = Path('/var/lib/aitbc/data/marketplace')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing data
        self._load_data()
        
        logger.info("Production marketplace initialized")
    
    def _load_data(self):
        """Load marketplace data from disk"""
        self.gpu_listings = {}
        self.bids = {}
        
        listings_file = self.data_dir / 'gpu_listings.json'
        bids_file = self.data_dir / 'bids.json'
        
        try:
            if listings_file.exists():
                with open(listings_file, 'r') as f:
                    self.gpu_listings = json.load(f)
            
            if bids_file.exists():
                with open(bids_file, 'r') as f:
                    self.bids = json.load(f)
                    
            logger.info(f"Loaded {len(self.gpu_listings)} GPU listings and {len(self.bids)} bids")
            
        except Exception as e:
            logger.error(f"Failed to load marketplace data: {e}")
    
    def _save_data(self):
        """Save marketplace data to disk"""
        try:
            listings_file = self.data_dir / 'gpu_listings.json'
            bids_file = self.data_dir / 'bids.json'
            
            with open(listings_file, 'w') as f:
                json.dump(self.gpu_listings, f, indent=2)
            
            with open(bids_file, 'w') as f:
                json.dump(self.bids, f, indent=2)
                
            logger.debug("Marketplace data saved")
            
        except Exception as e:
            logger.error(f"Failed to save marketplace data: {e}")
    
    def add_gpu_listing(self, listing: dict) -> str:
        """Add a new GPU listing"""
        try:
            gpu_id = f"gpu_{int(time.time())}_{len(self.gpu_listings)}"
            listing['id'] = gpu_id
            listing['created_at'] = time.time()
            listing['status'] = 'available'
            
            self.gpu_listings[gpu_id] = listing
            self._save_data()
            
            logger.info(f"GPU listing added: {gpu_id}")
            return gpu_id
            
        except Exception as e:
            logger.error(f"Failed to add GPU listing: {e}")
            raise
    
    def create_bid(self, bid_data: dict) -> str:
        """Create a new bid"""
        try:
            bid_id = f"bid_{int(time.time())}_{len(self.bids)}"
            bid_data['id'] = bid_id
            bid_data['created_at'] = time.time()
            bid_data['status'] = 'pending'
            
            self.bids[bid_id] = bid_data
            self._save_data()
            
            logger.info(f"Bid created: {bid_id}")
            return bid_id
            
        except Exception as e:
            logger.error(f"Failed to create bid: {e}")
            raise
    
    def get_marketplace_stats(self) -> dict:
        """Get marketplace statistics"""
        return {
            'total_gpus': len(self.gpu_listings),
            'available_gpus': len([g for g in self.gpu_listings.values() if g['status'] == 'available']),
            'total_bids': len(self.bids),
            'pending_bids': len([b for b in self.bids.values() if b['status'] == 'pending']),
            'total_value': sum(b['total_cost'] for b in self.bids.values())
        }

# Initialize marketplace
marketplace = ProductionMarketplace()

# FastAPI app
app = FastAPI(
    title="AITBC Production Marketplace",
    version="1.0.0",
    description="Production-grade GPU marketplace"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "production-marketplace",
        "timestamp": datetime.utcnow().isoformat(),
        "stats": marketplace.get_marketplace_stats()
    }

@app.post("/gpu/listings")
async def add_gpu_listing(listing: dict):
    """Add a new GPU listing"""
    try:
        gpu_id = marketplace.add_gpu_listing(listing)
        return {"gpu_id": gpu_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/bids")
async def create_bid(bid: dict):
    """Create a new bid"""
    try:
        bid_id = marketplace.create_bid(bid)
        return {"bid_id": bid_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_stats():
    """Get marketplace statistics"""
    return marketplace.get_marketplace_stats()

if __name__ == '__main__':
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv('MARKETPLACE_PORT', 8002)),
        workers=int(os.getenv('WORKERS', 4)),
        log_level="info"
    )
