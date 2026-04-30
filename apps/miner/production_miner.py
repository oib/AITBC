#!/usr/bin/env python3
"""
Real GPU Miner Client for AITBC - runs on host with actual GPU
"""

import json
import time
import sys
import subprocess
import os
from datetime import datetime, UTC
from typing import Dict, Optional

from aitbc import get_logger, AITBCHTTPClient, NetworkError

# Configuration
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://127.0.0.1:8001")
MINER_ID = os.environ.get("MINER_API_KEY", "miner_test")
AUTH_TOKEN = os.environ.get("MINER_API_KEY", "miner_test")
HEARTBEAT_INTERVAL = 15
MAX_RETRIES = 10
RETRY_DELAY = 30

# Initialize HTTP client
coordinator_client = AITBCHTTPClient(
    base_url=COORDINATOR_URL,
    headers={"X-Api-Key": AUTH_TOKEN, "Content-Type": "application/json"},
    timeout=30
)

# Setup logging with explicit configuration
LOG_PATH = "/var/log/aitbc/production_miner.log"
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

class FlushHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        FlushHandler(sys.stdout),
        logging.FileHandler(LOG_PATH)
    ]
)
logger = get_logger(__name__)

# Force stdout to be unbuffered
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

ARCH_MAP = {
    "4090": "ada_lovelace",
    "4080": "ada_lovelace",
    "4070": "ada_lovelace",
    "4060": "ada_lovelace",
    "3090": "ampere",
    "3080": "ampere",
    "3070": "ampere",
    "3060": "ampere",
    "2080": "turing",
    "2070": "turing",
    "2060": "turing",
    "1080": "pascal",
    "1070": "pascal",
    "1060": "pascal",
}


def classify_architecture(name: str) -> str:
    upper = name.upper()
    for key, arch in ARCH_MAP.items():
        if key in upper:
            return arch
    if "A100" in upper or "V100" in upper or "P100" in upper:
        return "datacenter"
    return "unknown"


def detect_cuda_version() -> Optional[str]:
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.error(f"Failed to detect CUDA/driver version: {e}")
    return None


def build_gpu_capabilities() -> Dict:
    gpu_info = get_gpu_info()
    cuda_version = detect_cuda_version() or "unknown"
    model = gpu_info["name"] if gpu_info else "Unknown GPU"
    memory_total = gpu_info["memory_total"] if gpu_info else 0
    arch = classify_architecture(model) if model else "unknown"
    edge_optimized = arch in {"ada_lovelace", "ampere", "turing"}

    return {
        "gpu": {
            "model": model,
            "architecture": arch,
            "consumer_grade": True,
            "edge_optimized": edge_optimized,
            "memory_gb": memory_total,
            "cuda_version": cuda_version,
            "platform": "CUDA",
            "supported_tasks": ["inference", "training", "stable-diffusion", "llama"],
            "max_concurrent_jobs": 1
        }
    }


def measure_coordinator_latency() -> float:
    start = time.time()
    try:
        client = AITBCHTTPClient(base_url=COORDINATOR_URL, timeout=3)
        resp = client.get("/health")
        if resp:
            return (time.time() - start) * 1000
    except NetworkError:
        pass
    return -1.0


def get_gpu_info():
    """Get real GPU information"""
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used,utilization.gpu', 
                               '--format=csv,noheader,nounits'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            info = result.stdout.strip().split(', ')
            return {
                "name": info[0],
                "memory_total": int(info[1]),
                "memory_used": int(info[2]),
                "utilization": int(info[3])
            }
    except Exception as e:
        logger.error(f"Failed to get GPU info: {e}")
    return None

def check_ollama():
    """Check if Ollama is running and has models"""
    try:
        client = AITBCHTTPClient(base_url="http://localhost:11434", timeout=5)
        response = client.get("/api/tags")
        if response:
            models = response.get('models', [])
            model_names = [m['name'] for m in models]
            logger.info(f"Ollama running with models: {model_names}")
            return True, model_names
        else:
            logger.error("Ollama not responding")
            return False, []
    except NetworkError as e:
        logger.error(f"Ollama check failed: {e}")
        return False, []

def wait_for_coordinator():
    """Wait for coordinator to be available"""
    for i in range(MAX_RETRIES):
        try:
            client = AITBCHTTPClient(base_url=COORDINATOR_URL, timeout=5)
            response = client.get("/health")
            if response:
                logger.info("Coordinator is available!")
                return True
        except NetworkError:
            pass

        logger.info(f"Waiting for coordinator... ({i+1}/{MAX_RETRIES})")
        time.sleep(RETRY_DELAY)

    logger.error("Coordinator not available after max retries")
    return False

def register_miner():
    """Register the miner with the coordinator"""
    register_data = {
        "capabilities": build_gpu_capabilities(),
        "concurrency": 1,
        "region": "localhost"
    }

    headers = {
        "X-Api-Key": AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    try:
        client = AITBCHTTPClient(base_url=COORDINATOR_URL, headers=headers, timeout=10)
        response = client.post(f"/v1/miners/register?miner_id={MINER_ID}", json=register_data)

        if response:
            logger.info(f"Successfully registered miner: {response}")
            return response.get("session_token", "demo-token")
        else:
            logger.error("Registration failed")
            return None

    except NetworkError as e:
        logger.error(f"Registration error: {e}")
        return None

def send_heartbeat():
    """Send heartbeat to coordinator with real GPU stats"""
    gpu_info = get_gpu_info()
    arch = classify_architecture(gpu_info["name"]) if gpu_info else "unknown"
    latency_ms = measure_coordinator_latency()

    if gpu_info:
        heartbeat_data = {
            "status": "active",
            "current_jobs": 0,
            "last_seen": datetime.now(datetime.UTC).isoformat(),
            "gpu_utilization": gpu_info["utilization"],
            "memory_used": gpu_info["memory_used"],
            "memory_total": gpu_info["memory_total"],
            "architecture": arch,
            "edge_optimized": arch in {"ada_lovelace", "ampere", "turing"},
            "network_latency_ms": latency_ms,
        }
    else:
        heartbeat_data = {
            "status": "active",
            "current_jobs": 0,
            "last_seen": datetime.now(datetime.UTC).isoformat(),
            "gpu_utilization": 0,
            "memory_used": 0,
            "memory_total": 0,
            "architecture": "unknown",
            "edge_optimized": False,
            "network_latency_ms": latency_ms,
        }

    headers = {
        "X-Api-Key": AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    try:
        client = AITBCHTTPClient(base_url=COORDINATOR_URL, headers=headers, timeout=5)
        response = client.post(f"/v1/miners/heartbeat?miner_id={MINER_ID}", json=heartbeat_data)

        if response:
            logger.info(f"Heartbeat sent (GPU: {gpu_info['utilization'] if gpu_info else 'N/A'}%)")
        else:
            logger.error("Heartbeat failed")

    except NetworkError as e:
        logger.error(f"Heartbeat error: {e}")

def execute_job(job, available_models):
    """Execute a job using real GPU resources"""
    job_id = job.get('job_id')
    payload = job.get('payload', {})
    
    logger.info(f"Executing job {job_id}: {payload}")
    
    try:
        if payload.get('type') == 'inference':
            # Get the prompt and model
            prompt = payload.get('prompt', '')
            model = payload.get('model', 'llama3.2:latest')
            
            # Check if model is available
            if model not in available_models:
                # Use first available model
                if available_models:
                    model = available_models[0]
                    logger.info(f"Using available model: {model}")
                else:
                    raise Exception("No models available in Ollama")
            
            # Call Ollama API for real GPU inference
            logger.info(f"Running inference on GPU with model: {model}")
            start_time = time.time()

            ollama_client = AITBCHTTPClient(base_url="http://localhost:11434", timeout=60)
            ollama_response = ollama_client.post(
                "/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                }
            )

            if ollama_response:
                result = ollama_response
                output = result.get('response', '')
                execution_time = time.time() - start_time
                
                # Get GPU stats after execution
                gpu_after = get_gpu_info()
                
                # Submit result back to coordinator
                submit_result(job_id, {
                    "result": {
                        "status": "completed",
                        "output": output,
                        "model": model,
                        "tokens_processed": result.get('eval_count', 0),
                        "execution_time": execution_time,
                        "gpu_used": True
                    },
                    "metrics": {
                        "gpu_utilization": gpu_after["utilization"] if gpu_after else 0,
                        "memory_used": gpu_after["memory_used"] if gpu_after else 0,
                        "memory_peak": max(gpu_after["memory_used"] if gpu_after else 0, 2048)
                    }
                })
                
                logger.info(f"Job {job_id} completed in {execution_time:.2f}s")
                return True
            else:
                logger.error("Ollama error")
                submit_result(job_id, {
                    "result": {
                        "status": "failed",
                        "error": "Ollama error"
                    }
                })
                return False
        else:
            # Unsupported job type
            logger.error(f"Unsupported job type: {payload.get('type')}")
            submit_result(job_id, {
                "result": {
                    "status": "failed",
                    "error": f"Unsupported job type: {payload.get('type')}"
                }
            })
            return False
            
    except Exception as e:
        logger.error(f"Job execution error: {e}")
        submit_result(job_id, {
            "result": {
                "status": "failed",
                "error": str(e)
            }
        })
        return False

def submit_result(job_id, result):
    """Submit job result to coordinator"""
    headers = {
        "X-Api-Key": AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    try:
        client = AITBCHTTPClient(base_url=COORDINATOR_URL, headers=headers, timeout=10)
        response = client.post(f"/v1/miners/{job_id}/result", json=result)

        if response:
            logger.info(f"Result submitted for job {job_id}")
        else:
            logger.error("Result submission failed")

    except NetworkError as e:
        logger.error(f"Result submission error: {e}")

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
        client = AITBCHTTPClient(base_url=COORDINATOR_URL, headers=headers, timeout=10)
        response = client.post("/v1/miners/poll", json=poll_data)

        if response:
            job = response
            logger.info(f"Received job: {job}")
            return job
        else:
            return None

    except NetworkError as e:
        logger.error(f"Error polling for jobs: {e}")
        return None

def main():
    """Main miner loop"""
    logger.info("Starting Real GPU Miner Client on Host...")
    
    # Check GPU availability
    gpu_info = get_gpu_info()
    if not gpu_info:
        logger.error("GPU not available, exiting")
        # sys.exit(1)
    
    logger.info(f"GPU detected: {gpu_info['name']} ({gpu_info['memory_total']}MB)")
    
    # Check Ollama
    ollama_available, models = check_ollama()
    if not ollama_available:
        logger.error("Ollama not available - please install and start Ollama")
        # sys.exit(1)

    logger.info(f"Ollama models available: {', '.join(models)}")
    
    # Wait for coordinator
    if not wait_for_coordinator():
        logger.error("Coordinator not available")
        return
    
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
            if current_time - last_poll >= 3:
                job = poll_for_jobs()
                if job:
                    # Execute the job with real GPU
                    execute_job(job, models)
                last_poll = current_time
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down miner...")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        # sys.exit(1)

if __name__ == "__main__":
    main()
