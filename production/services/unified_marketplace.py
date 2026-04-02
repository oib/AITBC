#!/usr/bin/env python3
"""
Unified AITBC Marketplace Service
Combined GPU Resources and AI Services Marketplace
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
sys.path.insert(0, '/opt/aitbc/production/services')

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Import OpenClaw AI service
try:
    from openclaw_ai import OpenClawAIService
    OPENCLAW_AVAILABLE = True
except ImportError:
    OPENCLAW_AVAILABLE = False
    print("Warning: OpenClaw AI service not available")

# Production logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('/opt/aitbc/production/logs/marketplace/unified_marketplace.log'),
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

class AIService(BaseModel):
    id: str
    name: str
    type: str
    capabilities: list
    model: str
    price_per_task: float
    provider: str
    node_id: str
    rating: float
    tasks_completed: int
    status: str

class AITask(BaseModel):
    id: str
    service_id: str
    user_id: str
    task_data: dict
    price: float
    status: str
    result: Optional[dict] = None

class UnifiedMarketplace:
    """Unified marketplace for GPU resources and AI services"""
    
    def __init__(self):
        self.node_id = os.getenv('NODE_ID', 'aitbc')
        self.data_dir = Path(f'/opt/aitbc/production/data/marketplace/{self.node_id}')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize OpenClaw service if available
        self.openclaw_service = None
        if OPENCLAW_AVAILABLE:
            try:
                self.openclaw_service = OpenClawAIService()
                logger.info("OpenClaw AI service initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenClaw: {e}")
        
        # Marketplace data
        self.gpu_listings = {}
        self.bids = {}
        self.ai_services = {}
        self.ai_tasks = {}
        
        self._load_data()
        self._initialize_ai_services()
        
        logger.info(f"Unified marketplace initialized for node: {self.node_id}")
    
    def _load_data(self):
        """Load marketplace data from disk"""
        try:
            # Load GPU listings
            listings_file = self.data_dir / 'gpu_listings.json'
            if listings_file.exists():
                with open(listings_file, 'r') as f:
                    self.gpu_listings = json.load(f)
            
            # Load bids
            bids_file = self.data_dir / 'bids.json'
            if bids_file.exists():
                with open(bids_file, 'r') as f:
                    self.bids = json.load(f)
            
            # Load AI services
            services_file = self.data_dir / 'ai_services.json'
            if services_file.exists():
                with open(services_file, 'r') as f:
                    self.ai_services = json.load(f)
            
            # Load AI tasks
            tasks_file = self.data_dir / 'ai_tasks.json'
            if tasks_file.exists():
                with open(tasks_file, 'r') as f:
                    self.ai_tasks = json.load(f)
                    
            logger.info(f"Loaded {len(self.gpu_listings)} GPU listings, {len(self.bids)} bids, {len(self.ai_services)} AI services, {len(self.ai_tasks)} tasks")
            
        except Exception as e:
            logger.error(f"Failed to load marketplace data: {e}")
    
    def _save_data(self):
        """Save marketplace data to disk"""
        try:
            with open(self.data_dir / 'gpu_listings.json', 'w') as f:
                json.dump(self.gpu_listings, f, indent=2)
            
            with open(self.data_dir / 'bids.json', 'w') as f:
                json.dump(self.bids, f, indent=2)
            
            with open(self.data_dir / 'ai_services.json', 'w') as f:
                json.dump(self.ai_services, f, indent=2)
            
            with open(self.data_dir / 'ai_tasks.json', 'w') as f:
                json.dump(self.ai_tasks, f, indent=2)
                
            logger.debug("Marketplace data saved")
            
        except Exception as e:
            logger.error(f"Failed to save marketplace data: {e}")
    
    def _initialize_ai_services(self):
        """Initialize AI services from OpenClaw"""
        if not self.openclaw_service:
            # Add default Ollama services
            ollama_services = [
                {
                    'id': 'ollama-llama2-7b',
                    'name': 'Ollama Llama2 7B',
                    'type': 'ollama_inference',
                    'capabilities': ['text_generation', 'chat', 'completion'],
                    'model': 'llama2-7b',
                    'price_per_task': 3.0,
                    'provider': 'Ollama',
                    'node_id': self.node_id,
                    'rating': 4.8,
                    'tasks_completed': 0,
                    'status': 'available'
                },
                {
                    'id': 'ollama-llama2-13b',
                    'name': 'Ollama Llama2 13B',
                    'type': 'ollama_inference',
                    'capabilities': ['text_generation', 'chat', 'completion', 'analysis'],
                    'model': 'llama2-13b',
                    'price_per_task': 5.0,
                    'provider': 'Ollama',
                    'node_id': self.node_id,
                    'rating': 4.9,
                    'tasks_completed': 0,
                    'status': 'available'
                }
            ]
            
            for service in ollama_services:
                self.ai_services[service['id']] = service
            
            logger.info(f"Initialized {len(ollama_services)} default AI services")
            return
        
        # Add OpenClaw services
        try:
            openclaw_agents = self.openclaw_service.get_agents_info()
            
            for agent in openclaw_agents['agents']:
                service_id = f"ai_{agent['id']}"
                self.ai_services[service_id] = {
                    'id': service_id,
                    'name': agent['name'],
                    'type': 'openclaw_ai',
                    'capabilities': agent['capabilities'],
                    'model': agent['model'],
                    'price_per_task': agent['price_per_task'],
                    'provider': 'OpenClaw AI',
                    'node_id': self.node_id,
                    'rating': agent['rating'],
                    'tasks_completed': agent['tasks_completed'],
                    'status': 'available'
                }
            
            logger.info(f"Initialized {len(openclaw_agents['agents'])} OpenClaw AI services")
            
        except Exception as e:
            logger.error(f"Failed to initialize OpenClaw services: {e}")
    
    # GPU Marketplace Methods
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
    
    # AI Marketplace Methods
    def get_ai_services(self) -> dict:
        """Get all AI services"""
        return {
            'node_id': self.node_id,
            'total_services': len(self.ai_services),
            'available_services': len([s for s in self.ai_services.values() if s['status'] == 'available']),
            'services': list(self.ai_services.values())
        }
    
    def execute_ai_task(self, service_id: str, task_data: dict, user_id: str = 'anonymous') -> dict:
        """Execute an AI task"""
        if service_id not in self.ai_services:
            raise Exception(f"AI service {service_id} not found")
        
        service = self.ai_services[service_id]
        
        # Create task record
        task_id = f"task_{int(time.time())}_{len(self.ai_tasks)}"
        task = {
            'id': task_id,
            'service_id': service_id,
            'user_id': user_id,
            'task_data': task_data,
            'price': service['price_per_task'],
            'status': 'executing',
            'created_at': time.time()
        }
        
        self.ai_tasks[task_id] = task
        self._save_data()
        
        try:
            if service['type'] == 'openclaw_ai' and self.openclaw_service:
                # Execute with OpenClaw
                agent_id = service_id.replace('ai_', '')
                result = self.openclaw_service.execute_task(agent_id, task_data)
                
            elif service['type'] == 'ollama_inference':
                # Execute with Ollama (simulated)
                model = service['model']
                prompt = task_data.get('prompt', '')
                
                # Simulate API call to Ollama
                time.sleep(2)  # Simulate processing time
                
                result = {
                    'service_id': service_id,
                    'task_id': task_id,
                    'status': 'completed',
                    'result': f"""
Ollama {model} Response:

{prompt}

This response is generated by the Ollama {model} model running on {self.node_id}.
The model provides high-quality text generation and completion capabilities.

Generated at: {datetime.utcnow().isoformat()}
""",
                    'execution_time': 2.0,
                    'model': model
                }
            else:
                raise Exception(f"Unsupported service type: {service['type']}")
            
            # Update task and service
            task['status'] = 'completed'
            task['result'] = result
            task['completed_at'] = time.time()
            
            service['tasks_completed'] += 1
            self._save_data()
            
            logger.info(f"AI task completed: {task_id}")
            return result
            
        except Exception as e:
            task['status'] = 'failed'
            task['error'] = str(e)
            self._save_data()
            logger.error(f"AI task failed: {e}")
            raise
    
    def get_marketplace_stats(self) -> dict:
        """Get comprehensive marketplace statistics"""
        gpu_stats = {
            'total_gpus': len(self.gpu_listings),
            'available_gpus': len([g for g in self.gpu_listings.values() if g['status'] == 'available']),
            'total_bids': len(self.bids),
            'pending_bids': len([b for b in self.bids.values() if b['status'] == 'pending']),
            'total_value': sum(b['total_cost'] for b in self.bids.values())
        }
        
        ai_stats = {
            'total_services': len(self.ai_services),
            'available_services': len([s for s in self.ai_services.values() if s['status'] == 'available']),
            'total_tasks': len(self.ai_tasks),
            'completed_tasks': len([t for t in self.ai_tasks.values() if t['status'] == 'completed']),
            'total_revenue': sum(t['price'] for t in self.ai_tasks.values() if t['status'] == 'completed'])
        }
        
        return {
            'node_id': self.node_id,
            'gpu_marketplace': gpu_stats,
            'ai_marketplace': ai_stats,
            'total_listings': gpu_stats['total_gpus'] + ai_stats['total_services'],
            'total_active': gpu_stats['available_gpus'] + ai_stats['available_services']
        }

# Initialize marketplace
marketplace = UnifiedMarketplace()

# FastAPI app
app = FastAPI(
    title="AITBC Unified Marketplace",
    version="2.0.0",
    description="Unified marketplace for GPU resources and AI services"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "unified-marketplace",
        "version": "2.0.0",
        "node_id": marketplace.node_id,
        "stats": marketplace.get_marketplace_stats()
    }

# GPU Marketplace Endpoints
@app.post("/gpu/listings")
async def add_gpu_listing(listing: dict):
    """Add a new GPU listing"""
    try:
        gpu_id = marketplace.add_gpu_listing(listing)
        return {"gpu_id": gpu_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/gpu/bids")
async def create_bid(bid: dict):
    """Create a new bid"""
    try:
        bid_id = marketplace.create_bid(bid)
        return {"bid_id": bid_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/gpu/listings")
async def get_gpu_listings():
    """Get all GPU listings"""
    return {"listings": list(marketplace.gpu_listings.values())}

@app.get("/gpu/bids")
async def get_bids():
    """Get all bids"""
    return {"bids": list(marketplace.bids.values())}

# AI Marketplace Endpoints
@app.get("/ai/services")
async def get_ai_services():
    """Get all AI services"""
    return marketplace.get_ai_services()

@app.post("/ai/execute")
async def execute_ai_task(request: dict):
    """Execute an AI task"""
    try:
        service_id = request.get('service_id')
        task_data = request.get('task_data')
        user_id = request.get('user_id', 'anonymous')
        
        result = marketplace.execute_ai_task(service_id, task_data, user_id)
        return {"task_id": result.get('task_id'), "status": "executing", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ai/tasks")
async def get_ai_tasks():
    """Get all AI tasks"""
    return {"tasks": list(marketplace.ai_tasks.values())}

# Unified Marketplace Endpoints
@app.get("/stats")
async def get_stats():
    """Get comprehensive marketplace statistics"""
    return marketplace.get_marketplace_stats()

@app.get("/search")
async def search_marketplace(query: str = "", category: str = ""):
    """Search across GPU and AI services"""
    results = {
        "gpu_listings": [],
        "ai_services": []
    }
    
    # Search GPU listings
    for listing in marketplace.gpu_listings.values():
        if query.lower() in listing.get('gpu_type', '').lower() or query.lower() in listing.get('provider', '').lower():
            results["gpu_listings"].append(listing)
    
    # Search AI services
    for service in marketplace.ai_services.values():
        if query.lower() in service.get('name', '').lower() or any(query.lower() in cap.lower() for cap in service.get('capabilities', [])):
            results["ai_services"].append(service)
    
    return results

if __name__ == '__main__':
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv('MARKETPLACE_PORT', 8002)),
        workers=int(os.getenv('WORKERS', 1)),  # Fixed to 1 to avoid workers warning
        log_level="info"
    )
