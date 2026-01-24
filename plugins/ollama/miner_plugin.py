#!/usr/bin/env python3
"""
AITBC Ollama Miner Plugin - Mines AITBC by processing LLM inference jobs
"""

import asyncio
import httpx
import logging
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional

# Import the Ollama service
from service import ollama_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OllamaMiner:
    """Miner plugin that processes LLM jobs using Ollama"""
    
    def __init__(self, coordinator_url: str, api_key: str, miner_id: str):
        self.coordinator_url = coordinator_url
        self.api_key = api_key
        self.miner_id = miner_id
        self.client = httpx.Client()
        self.running = False
        
    async def register(self):
        """Register the miner with Ollama capabilities"""
        
        # Get available models
        models = await ollama_service.get_models()
        model_list = [m["name"] for m in models]
        
        capabilities = {
            "service": "ollama",
            "gpu": {
                "model": "NVIDIA GeForce RTX 4060 Ti",
                "memory_gb": 16,
                "cuda_version": "12.1"
            },
            "ollama": {
                "models": model_list,
                "total_models": len(model_list),
                "supports_chat": True,
                "supports_generate": True
            },
            "compute": {
                "type": "GPU",
                "platform": "CUDA + Ollama",
                "supported_tasks": ["inference", "chat", "completion", "code-generation"],
                "max_concurrent_jobs": 2
            }
        }
        
        try:
            response = self.client.post(
                f"{self.coordinator_url}/v1/miners/register?miner_id={self.miner_id}",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": self.api_key
                },
                json={"capabilities": capabilities}
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Registered Ollama miner with {len(model_list)} models")
                return True
            else:
                logger.error(f"❌ Registration failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Registration error: {e}")
            return False
    
    async def process_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Process an LLM inference job"""
        
        payload = job.get("payload", {})
        job_type = payload.get("type", "generate")
        model = payload.get("model", "llama3.2:latest")
        
        logger.info(f"Processing {job_type} job with model: {model}")
        
        try:
            if job_type == "generate":
                result = await ollama_service.generate(
                    model=model,
                    prompt=payload.get("prompt", ""),
                    system_prompt=payload.get("system_prompt"),
                    temperature=payload.get("temperature", 0.7),
                    max_tokens=payload.get("max_tokens")
                )
            elif job_type == "chat":
                result = await ollama_service.chat(
                    model=model,
                    messages=payload.get("messages", []),
                    temperature=payload.get("temperature", 0.7),
                    max_tokens=payload.get("max_tokens")
                )
            else:
                result = {
                    "success": False,
                    "error": f"Unknown job type: {job_type}"
                }
            
            if result["success"]:
                # Add job metadata
                result["job_id"] = job["job_id"]
                result["processed_at"] = datetime.now().isoformat()
                result["miner_id"] = self.miner_id
                
                # Calculate earnings (cost + markup)
                cost = result.get("cost", 0.001)
                earnings = cost * 1.5  # 50% markup
                result["aitbc_earned"] = earnings
                
                logger.info(f"✅ Job completed - Earned: {earnings} AITBC")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Job processing failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "job_id": job["job_id"]
            }
    
    async def submit_result(self, job_id: str, result: Dict[str, Any]) -> bool:
        """Submit job result to coordinator"""
        
        payload = {
            "result": {
                "status": "completed" if result["success"] else "failed",
                "output": result.get("text", result.get("error", "")),
                "model": result.get("model"),
                "tokens": result.get("total_tokens", 0),
                "duration": result.get("duration_seconds", 0),
                "cost": result.get("cost", 0),
                "aitbc_earned": result.get("aitbc_earned", 0)
            },
            "metrics": {
                "compute_time": result.get("duration_seconds", 0),
                "energy_used": 0.05,
                "aitbc_earned": result.get("aitbc_earned", 0)
            }
        }
        
        try:
            response = self.client.post(
                f"{self.coordinator_url}/v1/miners/{job_id}/result",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": self.api_key
                },
                json=payload
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"❌ Failed to submit result: {e}")
            return False
    
    async def send_heartbeat(self):
        """Send heartbeat with GPU stats"""
        
        # Get GPU utilization (simplified)
        heartbeat_data = {
            "status": "ONLINE",
            "inflight": 0,
            "metadata": {
                "last_seen": datetime.now().isoformat(),
                "gpu_utilization": 65,
                "gpu_memory_used": 10000,
                "gpu_temperature": 70,
                "ollama_models": len(await ollama_service.get_models()),
                "service": "ollama"
            }
        }
        
        try:
            response = self.client.post(
                f"{self.coordinator_url}/v1/miners/heartbeat?miner_id={self.miner_id}",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": self.api_key
                },
                json=heartbeat_data
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"❌ Heartbeat failed: {e}")
            return False
    
    async def mine(self, max_jobs: Optional[int] = None):
        """Main mining loop"""
        
        logger.info("🚀 Starting Ollama miner...")
        
        # Register
        if not await self.register():
            return
        
        jobs_completed = 0
        last_heartbeat = time.time()
        
        self.running = True
        
        try:
            while self.running and (max_jobs is None or jobs_completed < max_jobs):
                
                # Send heartbeat every 30 seconds
                if time.time() - last_heartbeat > 30:
                    await self.send_heartbeat()
                    last_heartbeat = time.time()
                
                # Poll for jobs
                response = self.client.post(
                    f"{self.coordinator_url}/v1/miners/poll",
                    headers={
                        "Content-Type": "application/json",
                        "X-Api-Key": self.api_key
                    },
                    json={"max_wait_seconds": 5}
                )
                
                if response.status_code == 200:
                    job = response.json()
                    logger.info(f"📋 Got job: {job['job_id']}")
                    
                    # Process job
                    result = await self.process_job(job)
                    
                    # Submit result
                    if await self.submit_result(job['job_id'], result):
                        jobs_completed += 1
                        total_earned = sum(r.get("aitbc_earned", 0) for r in [result])
                        logger.info(f"💰 Total earned: {total_earned} AITBC")
                
                elif response.status_code == 204:
                    logger.debug("💤 No jobs available")
                    await asyncio.sleep(3)
                else:
                    logger.error(f"❌ Poll failed: {response.status_code}")
                    await asyncio.sleep(5)
                
        except KeyboardInterrupt:
            logger.info("⏹️  Mining stopped by user")
        
        finally:
            self.running = False
            logger.info(f"✅ Mining complete - Jobs processed: {jobs_completed}")

# Main execution
if __name__ == "__main__":
    import sys
    
    coordinator_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
    api_key = sys.argv[2] if len(sys.argv) > 2 else "REDACTED_MINER_KEY"
    miner_id = sys.argv[3] if len(sys.argv) > 3 else "ollama-miner"
    
    # Create and run miner
    miner = OllamaMiner(coordinator_url, api_key, miner_id)
    
    # Run the miner
    asyncio.run(miner.mine())
