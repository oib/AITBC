#!/usr/bin/env python3
"""
AITBC GPU Inference Miner Example

Registers a miner with the coordinator, polls for inference jobs, optionally
runs them through a local Ollama instance, and submits the result back.

Usage:
    export MINER_API_KEY="test-miner-key-32-characters-long-xxx"
    python examples/gpu_inference_miner.py --api-key "$MINER_API_KEY" --miner-id my-miner

Requirements:
    pip install httpx
    (Optional) Ollama running on http://localhost:11434 for real inference.
"""

import argparse
import logging
import os
import time
from typing import Any, cast

import httpx

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("gpu_miner")


def _now() -> str:
    """ISO timestamp for metrics."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def register_miner(client: httpx.Client, coordinator: str, api_key: str, miner_id: str, model: str) -> bool:
    """Register this miner with its capabilities."""
    payload = {
        "capabilities": {
            "gpu": {"model": "NVIDIA RTX 4090", "memory_gb": 24, "cuda_version": "12.4"},
            "compute": {
                "type": "GPU",
                "platform": "CUDA",
                "supported_tasks": ["inference"],
                "supported_models": [model],
                "max_concurrent_jobs": 1,
            },
        },
        "concurrency": 1,
        "region": os.getenv("MINER_REGION", "local"),
    }
    response = client.post(
        f"{coordinator}/v1/miners/register",
        headers={"X-Api-Key": api_key, "X-Miner-ID": miner_id, "Content-Type": "application/json"},
        json=payload,
    )
    if response.status_code == 200:
        logger.info("Miner registered: %s", response.json())
        return True
    logger.error("Registration failed: %s %s", response.status_code, response.text)
    return False


def send_heartbeat(client: httpx.Client, coordinator: str, api_key: str, miner_id: str) -> None:
    """Keep the miner session alive."""
    payload = {
        "status": "ONLINE",
        "inflight": 0,
        "metadata": {
            "last_seen": _now(),
            "gpu_utilization": 10,
            "gpu_memory_used": 1024,
            "gpu_temperature": 45,
        },
    }
    client.post(
        f"{coordinator}/v1/miners/heartbeat",
        headers={"X-Api-Key": api_key, "X-Miner-ID": miner_id, "Content-Type": "application/json"},
        json=payload,
    )


def run_ollama_inference(model: str, prompt: str) -> dict[str, Any] | None:
    """Call a local Ollama instance if it is reachable."""
    try:
        ollama = httpx.Client(base_url="http://localhost:11434", timeout=120)
        response = ollama.post("/api/generate", json={"model": model, "prompt": prompt, "stream": False})
        response.raise_for_status()
        data = response.json()
        return {
            "output": data.get("response", "").strip(),
            "model": model,
            "tokens_evaluated": data.get("eval_count", 0),
            "gpu_used": True,
        }
    except (httpx.RequestError, httpx.HTTPStatusError):
        return None


def execute_inference(job_id: str, payload: dict[str, Any], model: str) -> dict[str, Any]:
    """Run the inference job, preferring Ollama, falling back to a deterministic mock."""
    prompt = payload.get("prompt", "")
    requested_model = payload.get("model") or model

    result = run_ollama_inference(requested_model, prompt)
    if result is None:
        logger.warning("Ollama not available; returning mock result for demo.")
        result = {
            "output": f"[mock] Generated text for prompt: {prompt[:60]}...",
            "model": requested_model,
            "tokens_evaluated": 0,
            "gpu_used": False,
        }

    return result


def poll_job(client: httpx.Client, coordinator: str, api_key: str, miner_id: str) -> dict[str, Any] | None:
    """Poll the coordinator for the next job."""
    response = client.post(
        f"{coordinator}/v1/miners/poll",
        headers={"X-Api-Key": api_key, "X-Miner-ID": miner_id, "Content-Type": "application/json"},
        json={"max_wait_seconds": 5},
    )
    if response.status_code == 204:
        return None
    if response.status_code == 200:
        return cast(dict[str, Any], response.json())
    logger.error("Poll failed: %s %s", response.status_code, response.text)
    return None


def submit_result(
    client: httpx.Client,
    coordinator: str,
    api_key: str,
    miner_id: str,
    job_id: str,
    result: dict[str, Any],
) -> bool:
    """Submit the completed job result."""
    response = client.post(
        f"{coordinator}/v1/miners/{job_id}/result",
        headers={"X-Api-Key": api_key, "X-Miner-ID": miner_id, "Content-Type": "application/json"},
        json={
            "result": result,
            "metrics": {
                "execution_time_ms": 0,
                "gpu_utilization": 75 if result.get("gpu_used") else 0,
                "memory_used_mb": 4096,
            },
        },
    )
    if response.status_code == 200:
        logger.info("Result submitted for job %s", job_id)
        return True
    logger.error("Submit result failed: %s %s", response.status_code, response.text)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="AITBC GPU inference miner example")
    parser.add_argument("--coordinator", default="http://localhost:8203", help="Coordinator base URL")
    parser.add_argument("--api-key", default=os.getenv("MINER_API_KEY", ""), help="Miner API key")
    parser.add_argument("--miner-id", default="demo-gpu-miner", help="Unique miner ID")
    parser.add_argument("--model", default="llama2", help="Default inference model")
    parser.add_argument("--poll-interval", type=int, default=3, help="Seconds between polls")
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("--api-key or MINER_API_KEY is required")

    client = httpx.Client(timeout=15)
    try:
        if not register_miner(client, args.coordinator, args.api_key, args.miner_id, args.model):
            raise SystemExit("Could not register miner")

        logger.info("Polling for inference jobs...")
        while True:
            try:
                job = poll_job(client, args.coordinator, args.api_key, args.miner_id)
                if job:
                    job_id = job["job_id"]
                    payload = job.get("payload", {})
                    logger.info("Received job %s: %s", job_id, payload.get("type", "unknown"))

                    result = execute_inference(job_id, payload, args.model)
                    submit_result(client, args.coordinator, args.api_key, args.miner_id, job_id, result)
                    logger.info("Job %s completed: %s", job_id, result.get("output", "")[:80])
                else:
                    send_heartbeat(client, args.coordinator, args.api_key, args.miner_id)

                time.sleep(args.poll_interval)
            except KeyboardInterrupt:
                logger.info("Shutting down miner")
                break
            except Exception as exc:
                logger.error("Miner loop error: %s", exc)
                time.sleep(args.poll_interval)
    finally:
        client.close()


if __name__ == "__main__":
    main()
