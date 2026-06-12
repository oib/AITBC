#!/usr/bin/env python3
"""
Real GPU Miner Client for AITBC - runs on host with actual GPU
"""

import logging
import os
import subprocess
import sys
import time
from datetime import UTC, datetime

import httpx

# Configuration
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://127.0.0.1:8001")
MINER_ID = os.environ.get("MINER_API_KEY", "miner_test")
AUTH_TOKEN = os.environ.get("MINER_API_KEY", "miner_test")
HEARTBEAT_INTERVAL = 15
MAX_RETRIES = 10
RETRY_DELAY = 30

# Setup logging with explicit configuration
LOG_PATH = "/var/log/aitbc/host_gpu_miner.log"
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
logger = logging.getLogger(__name__)

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


def detect_cuda_version() -> str | None:
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.error("Failed to detect CUDA/driver version: %s", e)
    return None


def build_gpu_capabilities() -> dict:
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
        resp = httpx.get(f"{COORDINATOR_URL}/v1/health", timeout=3)
        if resp.status_code == 200:
            return (time.time() - start) * 1000
    except Exception:
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
        logger.error("Failed to get GPU info: %s", e)
    return None

def check_ollama():
    """Check if Ollama is running and has models"""
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            model_names = [m['name'] for m in models]
            logger.info("Ollama running with models: %s", model_names)
            return True, model_names
        else:
            logger.error("Ollama not responding")
            return False, []
    except Exception as e:
        logger.error("Ollama check failed: %s", e)
        return False, []

def wait_for_coordinator():
    """Wait for coordinator to be available"""
    for i in range(MAX_RETRIES):
        try:
            response = httpx.get(f"{COORDINATOR_URL}/v1/health", timeout=5)
            if response.status_code == 200:
                logger.info("Coordinator is available!")
                return True
        except Exception:
            pass

        logger.info("Waiting for coordinator... (%s/%s)", i+1, MAX_RETRIES)
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
        response = httpx.post(
            f"{COORDINATOR_URL}/v1/miners/register?miner_id={MINER_ID}",
            json=register_data,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            logger.info("Successfully registered miner: %s", data)
            return data.get("session_token", "demo-token")
        else:
            logger.error("Registration failed: %s - %s", response.status_code, response.text)
            return None

    except Exception as e:
        logger.error("Registration error: %s", e)
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
            "last_seen": datetime.now(UTC).isoformat(),
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
            "last_seen": datetime.now(UTC).isoformat(),
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
        response = httpx.post(
            f"{COORDINATOR_URL}/v1/miners/heartbeat?miner_id={MINER_ID}",
            json=heartbeat_data,
            headers=headers,
            timeout=5
        )

        if response.status_code == 200:
            logger.info("Heartbeat sent (GPU: %s%%)", gpu_info['utilization'] if gpu_info else 'N/A')
        else:
            logger.error("Heartbeat failed: %s - %s", response.status_code, response.text)

    except Exception as e:
        logger.error("Heartbeat error: %s", e)

def execute_job(job, available_models):
    """Execute a job using real GPU resources"""
    job_id = job.get('job_id')
    payload = job.get('payload', {})

    logger.info("Executing job %s: %s", job_id, payload)

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
                    logger.info("Using available model: %s", model)
                else:
                    raise Exception("No models available in Ollama")

            # Call Ollama API for real GPU inference
            logger.info("Running inference on GPU with model: %s", model)
            start_time = time.time()

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

                logger.info("Job %s completed in %.2fs", job_id, execution_time)
                return True
            else:
                logger.error("Ollama error: %s", ollama_response.status_code)
                submit_result(job_id, {
                    "result": {
                        "status": "failed",
                        "error": "Ollama error: %s" % ollama_response.text
                    }
                })
                return False
        else:
            # Unsupported job type
            logger.error("Unsupported job type: %s", payload.get('type'))
            submit_result(job_id, {
                "result": {
                    "status": "failed",
                    "error": "Unsupported job type: %s" % payload.get('type')
                }
            })
            return False

    except Exception as e:
        logger.error("Job execution error: %s", e)
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
        response = httpx.post(
            f"{COORDINATOR_URL}/v1/miners/{job_id}/result",
            json=result,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            logger.info("Result submitted for job %s", job_id)
        else:
            logger.error("Result submission failed: %s - %s", response.status_code, response.text)

    except Exception as e:
        logger.error("Result submission error: %s", e)

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
            logger.info("Received job: %s", job)
            return job
        elif response.status_code == 204:
            return None
        else:
            logger.error("Poll failed: %s - %s", response.status_code, response.text)
            return None

    except Exception as e:
        logger.error("Error polling for jobs: %s", e)
        return None

def main():
    """Main miner loop"""
    logger.info("Starting Real GPU Miner Client on Host...")

    # Check GPU availability
    gpu_info = get_gpu_info()
    if not gpu_info:
        logger.error("GPU not available, exiting")
        sys.exit(1)

    logger.info("GPU detected: %s (%sMB)", gpu_info['name'], gpu_info['memory_total'])

    # Check Ollama
    ollama_available, models = check_ollama()
    if not ollama_available:
        logger.error("Ollama not available - please install and start Ollama")
        sys.exit(1)

    logger.info("Ollama models available: %s", ', '.join(models))

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
                    # Execute the job with real GPU
                    execute_job(job, models)
                last_poll = current_time

            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Shutting down miner...")
    except Exception as e:
        logger.error("Error in main loop: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
