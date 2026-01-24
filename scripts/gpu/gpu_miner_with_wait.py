#!/usr/bin/env python3
"""
GPU Miner Client with retry logic for AITBC
"""

import json
import time
import httpx
import logging
import sys
from datetime import datetime

# Configuration
COORDINATOR_URL = "http://127.0.0.1:8000"
MINER_ID = "localhost-gpu-miner"
AUTH_TOKEN = "REDACTED_MINER_KEY"
HEARTBEAT_INTERVAL = 15
MAX_RETRIES = 10
RETRY_DELAY = 30

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# GPU capabilities (RTX 4060 Ti)
GPU_CAPABILITIES = {
    "gpu": {
        "model": "NVIDIA GeForce RTX 4060 Ti",
        "memory_gb": 16,
        "cuda_version": "12.4",
        "compute_capability": "8.9",
        "driver_version": "550.163.01"
    },
    "compute": {
        "type": "GPU",
        "platform": "CUDA",
        "supported_tasks": ["inference", "training", "stable-diffusion", "llama"],
        "max_concurrent_jobs": 1
    }
}

def wait_for_coordinator():
    """Wait for coordinator to be available"""
    for i in range(MAX_RETRIES):
        try:
            response = httpx.get(f"{COORDINATOR_URL}/v1/health", timeout=5)
            if response.status_code == 200:
                logger.info("Coordinator is available!")
                return True
        except:
            pass
        
        logger.info(f"Waiting for coordinator... ({i+1}/{MAX_RETRIES})")
        time.sleep(RETRY_DELAY)
    
    logger.error("Coordinator not available after max retries")
    return False

def register_miner():
    """Register the miner with the coordinator"""
    register_data = {
        "capabilities": GPU_CAPABILITIES,
        "concurrency": 1,
        "region": "localhost"
    }
    
    headers = {
        "X-Api-Key": AUTH_TOKEN,
        "Content-Type": "application/json"
    }
    
    try:
        response = httpx.post(
            f"{COORDINATOR_URL}/v1/miners/register?miner_id={MINER_ID}",
            json=register_data,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Successfully registered miner: {data}")
            # Don't require session_token for demo registry
            return data.get("session_token", "demo-token")
        else:
            logger.error(f"Registration failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error registering miner: {e}")
        return None

def send_heartbeat():
    """Send heartbeat to coordinator"""
    heartbeat_data = {
        "inflight": 0,
        "status": "ONLINE",
        "metadata": {
            "last_seen": datetime.utcnow().isoformat(),
            "gpu_utilization": 9,
            "gpu_memory_used": 2682,
            "gpu_temperature": 43
        }
    }
    
    headers = {
        "X-Api-Key": AUTH_TOKEN,
        "Content-Type": "application/json"
    }
    
    try:
        response = httpx.post(
            f"{COORDINATOR_URL}/v1/miners/heartbeat?miner_id={MINER_ID}",
            json=heartbeat_data,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            logger.info("Heartbeat sent successfully")
        else:
            logger.error(f"Heartbeat failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        logger.error(f"Error sending heartbeat: {e}")

def poll_for_jobs():
    """Poll for available jobs"""
    poll_data = {
        "max_wait_seconds": 5
    }
    
    headers = {
        "X-Api-Key": AUTH_TOKEN,
        "Content-Type": "application/json"
    }
    
    try:
        response = httpx.post(
            f"{COORDINATOR_URL}/v1/miners/poll",
            json=poll_data,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            job = response.json()
            logger.info(f"Received job: {job}")
            return job
        elif response.status_code == 204:
            logger.info("No jobs available")
            return None
        elif response.status_code in (404, 405):
            # Coordinator/registry may not implement job polling (e.g. demo registry).
            # Keep running (heartbeats still work) but don't spam error logs.
            return None
        else:
            logger.error(f"Poll failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error polling for jobs: {e}")
        return None

def main():
    """Main miner loop"""
    logger.info("Starting GPU Miner Client...")
    
    # Wait for coordinator
    if not wait_for_coordinator():
        sys.exit(1)
    
    # Register with coordinator
    session_token = register_miner()
    if not session_token:
        logger.error("Failed to register, exiting")
        sys.exit(1)
    
    logger.info("Miner registered successfully, starting main loop...")
    
    # Main loop
    last_heartbeat = 0
    last_poll = 0
    
    try:
        while True:
            current_time = time.time()
            
            # Send heartbeat
            if current_time - last_heartbeat >= HEARTBEAT_INTERVAL:
                send_heartbeat()
                last_heartbeat = current_time
            
            # Poll for jobs
            if current_time - last_poll >= 3:
                job = poll_for_jobs()
                if job:
                    logger.info(f"Would execute job: {job}")
                last_poll = current_time
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down miner...")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
