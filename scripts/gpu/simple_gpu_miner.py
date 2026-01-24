#!/usr/bin/env python3
"""
Simple GPU Miner Client for AITBC
Registers GPU with coordinator and sends heartbeats
"""

import json
import time
import httpx
import logging
from datetime import datetime

# Configuration
COORDINATOR_URL = "http://localhost:8000"
MINER_ID = "localhost-gpu-miner"
AUTH_TOKEN = "REDACTED_MINER_KEY"
HEARTBEAT_INTERVAL = 15

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

def register_miner():
    """Register the miner with the coordinator"""
    register_data = {
        "capabilities": GPU_CAPABILITIES,
        "concurrency": 1,
        "region": "localhost"
    }
    
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = httpx.post(
            f"{COORDINATOR_URL}/miners/register",
            json=register_data,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Successfully registered miner: {data}")
            return data.get("session_token")
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
            "gpu_utilization": 9,  # Current GPU utilization from nvidia-smi
            "gpu_memory_used": 2682,  # MB
            "gpu_temperature": 43
        }
    }
    
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = httpx.post(
            f"{COORDINATOR_URL}/miners/heartbeat",
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
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = httpx.post(
            f"{COORDINATOR_URL}/miners/poll",
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
        else:
            logger.error(f"Poll failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error polling for jobs: {e}")
        return None

def main():
    """Main miner loop"""
    logger.info("Starting GPU Miner Client...")
    
    # Register with coordinator
    session_token = register_miner()
    if not session_token:
        logger.error("Failed to register, exiting")
        return
    
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
            if current_time - last_poll >= 3:  # Poll every 3 seconds
                job = poll_for_jobs()
                if job:
                    # TODO: Execute job
                    logger.info(f"Would execute job: {job}")
                last_poll = current_time
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down miner...")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")

if __name__ == "__main__":
    main()
