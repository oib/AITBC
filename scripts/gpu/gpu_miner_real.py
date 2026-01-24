#!/usr/bin/env python3
"""
Real GPU Miner Client for AITBC with Ollama integration
"""

import json
import time
import httpx
import logging
import sys
import subprocess
import os
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
        "platform": "CUDA",
        "supported_tasks": ["inference", "training", "stable-diffusion", "llama"],
        "max_concurrent_jobs": 1
    }
}

def check_gpu_available():
    """Check if GPU is available"""
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            gpu_info = result.stdout.strip().split(', ')
            logger.info(f"GPU detected: {gpu_info[0]}, Memory: {gpu_info[1]}MB")
            return True
        else:
            logger.error("nvidia-smi failed")
            return False
    except Exception as e:
        logger.error(f"GPU check failed: {e}")
        return False

def check_ollama():
    """Check if Ollama is running"""
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            logger.info(f"Ollama running with {len(models)} models")
            return True
        else:
            logger.error("Ollama not responding")
            return False
    except Exception as e:
        logger.error(f"Ollama check failed: {e}")
        return False

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
            return data.get("session_token", "demo-token")
        else:
            logger.error(f"Registration failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return None

def send_heartbeat():
    """Send heartbeat to coordinator"""
    heartbeat_data = {
        "status": "active",
        "current_jobs": 0,
        "last_seen": datetime.utcnow().isoformat(),
        "gpu_utilization": 45,  # Simulated
        "memory_used": 8192,    # Simulated
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
        logger.error(f"Heartbeat error: {e}")

def execute_job(job):
    """Execute a job using GPU resources"""
    job_id = job.get('job_id')
    payload = job.get('payload', {})
    
    logger.info(f"Executing job {job_id}: {payload}")
    
    try:
        if payload.get('type') == 'inference':
            # Use Ollama for inference
            prompt = payload.get('prompt', '')
            model = payload.get('model', 'llama3.2:latest')
            
            # Call Ollama API
            ollama_response = httpx.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=60
            )
            
            if ollama_response.status_code == 200:
                result = ollama_response.json()
                output = result.get('response', '')
                
                # Submit result back to coordinator
                submit_result(job_id, {
                    "status": "completed",
                    "output": output,
                    "model": model,
                    "tokens_processed": result.get('eval_count', 0),
                    "execution_time": result.get('total_duration', 0) / 1000000000,  # Convert to seconds
                    "gpu_used": True
                })
                
                logger.info(f"Job {job_id} completed successfully")
                return True
            else:
                logger.error(f"Ollama error: {ollama_response.status_code}")
                submit_result(job_id, {
                    "status": "failed",
                    "error": f"Ollama error: {ollama_response.text}"
                })
                return False
        else:
            # Unsupported job type
            logger.error(f"Unsupported job type: {payload.get('type')}")
            submit_result(job_id, {
                "status": "failed",
                "error": f"Unsupported job type: {payload.get('type')}"
            })
            return False
            
    except Exception as e:
        logger.error(f"Job execution error: {e}")
        submit_result(job_id, {
            "status": "failed",
            "error": str(e)
        })
        return False

def submit_result(job_id, result):
    """Submit job result to coordinator"""
    headers = {
        "X-Api-Key": AUTH_TOKEN,
        "Content-Type": "application/json"
    }
    
    try:
        response = httpx.post(
            f"{COORDINATOR_URL}/v1/jobs/{job_id}/result",
            json=result,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info(f"Result submitted for job {job_id}")
        else:
            logger.error(f"Result submission failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        logger.error(f"Result submission error: {e}")

def poll_for_jobs():
    """Poll for available jobs"""
    poll_data = {
        "miner_id": MINER_ID,
        "capabilities": GPU_CAPABILITIES,
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
        else:
            logger.error(f"Poll failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error polling for jobs: {e}")
        return None

def main():
    """Main miner loop"""
    logger.info("Starting Real GPU Miner Client...")
    
    # Check GPU availability (optional)
    gpu_available = check_gpu_available()
    if not gpu_available:
        logger.warning("GPU not available - will run in CPU mode")
    
    # Check Ollama
    if not check_ollama():
        logger.warning("Ollama not available - inference jobs will fail")
    
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
                    # Execute the job
                    execute_job(job)
                last_poll = current_time
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down miner...")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
