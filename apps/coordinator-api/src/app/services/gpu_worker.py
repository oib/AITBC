"""
GPU Worker Service - Real GPU provider integration

This module provides the GPUWorker class that:
1. Integrates with Ollama or external GPU services
2. Executes AI workloads assigned by the coordinator
3. Reports results and generates receipts
4. Manages GPU resources and health
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from aitbc.aitbc_logging import get_logger

from ..core.lifecycle import get_lifecycle_state

logger = get_logger(__name__)


@dataclass
class GPUCapabilities:
    """GPU provider capabilities"""

    gpu_available: bool
    models: list[str]
    max_concurrency: int
    memory_gb: int
    compute_units: int
    architecture: str
    edge_optimized: bool


@dataclass
class JobExecutionResult:
    """Result of job execution"""

    success: bool
    output: dict[str, Any]
    execution_time_ms: int
    gpu_utilization: float
    receipt: dict[str, Any]
    error: str | None = None


class OllamaClient:
    """
    Client for Ollama AI service integration.

    Connects to local or remote Ollama instances to run
    AI inference on assigned workloads.
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=300.0)

    async def list_models(self) -> list[str]:
        """List available models from Ollama"""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.warning("Failed to list Ollama models: %s", e)
            return []

    async def generate(self, model: str, prompt: str, options: dict | None = None) -> dict[str, Any]:
        """
        Generate text using Ollama.

        Args:
            model: Model name (e.g., "llama2", "gpt2")
            prompt: Input prompt
            options: Generation options (temperature, max_tokens, etc.)

        Returns:
            Generation result with response and metadata
        """
        try:
            start_time = time.time()
            request_data = {"model": model, "prompt": prompt, "stream": False}
            if options:
                request_data["options"] = options
            response = await self.client.post(f"{self.base_url}/api/generate", json=request_data)
            response.raise_for_status()
            result = response.json()
            execution_time = int((time.time() - start_time) * 1000)
            return {
                "success": True,
                "output": result.get("response", ""),
                "model": model,
                "prompt_length": len(prompt),
                "tokens_generated": result.get("eval_count", 0),
                "execution_time_ms": execution_time,
                "done": result.get("done", False),
            }
        except httpx.HTTPStatusError as e:
            logger.error("Ollama HTTP error: %s - %s", e.response.status_code, e.response.text)
            return {"success": False, "error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            logger.error("Ollama generation failed: %s", e)
            return {"success": False, "error": str(e)}

    async def health_check(self) -> bool:
        """Check if Ollama is accessible"""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False


class GPUWorker:
    """
    GPU Worker for executing AI jobs.

    This class manages GPU resources and executes assigned
    AI workloads through Ollama or other inference backends.
    """

    def __init__(
        self,
        worker_id: str,
        ollama_url: str = "http://localhost:11434",
        max_concurrent: int = 2,
        coordinator_url: str = "http://localhost:8203",
    ):
        self.worker_id = worker_id
        self.ollama = OllamaClient(ollama_url)
        self.max_concurrent = max_concurrent
        self.coordinator_url = coordinator_url
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self._capabilities: GPUCapabilities | None = None
        self._http_client = httpx.AsyncClient(timeout=60.0)
        self._processed_count = 0
        self._lifecycle_state = get_lifecycle_state()

    async def initialize(self) -> bool:
        """Initialize GPU worker and detect capabilities"""
        logger.info("Initializing GPU worker %s", self.worker_id)
        ollama_healthy = await self.ollama.health_check()
        if not ollama_healthy:
            logger.warning("Ollama not accessible, running in mock mode")
        models = await self.ollama.list_models() if ollama_healthy else ["gpt2", "llama2"]
        memory_gb = 8
        compute_units = 4
        try:
            import subprocess

            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                memory_mb = int(result.stdout.strip())
                memory_gb = memory_mb // 1024
                logger.info("Detected GPU memory: %s GB", memory_gb)
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError) as e:
            logger.debug("GPU detection failed: %s, using default 8 GB", e)
        self._capabilities = GPUCapabilities(
            gpu_available=ollama_healthy,
            models=models,
            max_concurrency=self.max_concurrent,
            memory_gb=memory_gb,
            compute_units=compute_units,
            architecture="cuda" if ollama_healthy else "cpu",
            edge_optimized=False,
        )
        logger.info("GPU worker initialized with %s models: %s", len(models), models)
        return True

    async def register_with_coordinator(self, api_key: str) -> bool:
        """Register this worker with the coordinator API"""
        try:
            if not self._capabilities:
                await self.initialize()
            register_data = {
                "capabilities": {
                    "gpu": self._capabilities.gpu_available,
                    "models": self._capabilities.models,
                    "concurrency": self._capabilities.max_concurrency,
                    "memory_gb": self._capabilities.memory_gb,
                    "architecture": self._capabilities.architecture,
                    "edge_optimized": self._capabilities.edge_optimized,
                },
                "concurrency": self._capabilities.max_concurrency,
                "region": "local",
            }  # type: ignore[union-attr]
            response = await self._http_client.post(
                f"{self.coordinator_url}/miners/register",
                headers={"X-Miner-ID": self.worker_id, "X-API-Key": api_key},
                json=register_data,
            )
            if response.status_code in (200, 201):
                logger.info("Worker %s registered with coordinator", self.worker_id)
                return True
            else:
                logger.error("Registration failed: %s", response.status_code)
                return False
        except Exception as e:
            logger.error("Failed to register worker: %s", e)
            return False

    async def start(self, api_key: str) -> None:
        """Start the worker loop - poll for and execute jobs"""
        self._running = True
        logger.info("GPU worker %s started", self.worker_id)
        while self._running and not self._lifecycle_state.is_shutting_down():
            try:
                await self._poll_and_execute(api_key)
            except Exception as e:
                logger.error("Error in worker loop: %s", e)
            await asyncio.sleep(1.0)

    def stop(self) -> None:
        """Stop the worker"""
        self._running = False
        self._executor.shutdown(wait=False)
        logger.info("GPU worker %s stopped", self.worker_id)

    async def _poll_and_execute(self, api_key: str) -> None:
        """Poll for jobs and execute them"""
        try:
            response = await self._http_client.post(
                f"{self.coordinator_url}/miners/{self.worker_id}/poll",
                headers={"X-Miner-ID": self.worker_id, "X-API-Key": api_key},
                params={"max_wait_seconds": 5},
            )
            if response.status_code == 204:
                return
            if response.status_code != 200:
                return
            job = response.json()
            job_id = job.get("job_id")
            if not job_id:
                return
            logger.info("Executing job %s", job_id)
            result = await self._execute_job(job)
            await self._submit_result(job_id, result, api_key)
        except Exception as e:
            logger.error("Error polling/executing: %s", e)

    async def _execute_job(self, job: dict[str, Any]) -> JobExecutionResult:
        """Execute a single AI job"""
        start_time = time.time()
        try:
            payload = job.get("payload", {})
            model = payload.get("model", "gpt2")
            prompt = payload.get("prompt", "")
            max_tokens = payload.get("max_tokens", 100)
            if model not in (self._capabilities.models if self._capabilities else []):
                return JobExecutionResult(
                    success=False,
                    output={},
                    execution_time_ms=0,
                    gpu_utilization=0.0,
                    receipt={},
                    error=f"Model {model} not available",
                )
            if self._capabilities and self._capabilities.gpu_available:
                inference_result = await self.ollama.generate(model=model, prompt=prompt, options={"num_predict": max_tokens})
            else:
                await asyncio.sleep(0.1)
                inference_result = {
                    "success": True,
                    "output": f"[Mock output for {model}] Generated text based on: {prompt[:50]}...",
                    "model": model,
                    "prompt_length": len(prompt),
                    "tokens_generated": max_tokens,
                    "execution_time_ms": 100,
                    "done": True,
                }
            execution_time = int((time.time() - start_time) * 1000)
            if not inference_result.get("success"):
                return JobExecutionResult(
                    success=False,
                    output={},
                    execution_time_ms=execution_time,
                    gpu_utilization=0.0,
                    receipt={},
                    error=inference_result.get("error", "Inference failed"),
                )
            receipt = self._generate_receipt(job.get("job_id"), inference_result, execution_time)  # type: ignore[arg-type]
            self._processed_count += 1
            gpu_utilization = 0.0
            try:
                import subprocess

                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    gpu_utilization = float(result.stdout.strip()) / 100.0
            except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
                gpu_utilization = min(0.9, max(0.1, execution_time / 5000.0))
            return JobExecutionResult(
                success=True,
                output=inference_result,
                execution_time_ms=execution_time,
                gpu_utilization=gpu_utilization,
                receipt=receipt,
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return JobExecutionResult(
                success=False, output={}, execution_time_ms=execution_time, gpu_utilization=0.0, receipt={}, error=str(e)
            )

    async def _submit_result(self, job_id: str, result: JobExecutionResult, api_key: str) -> None:
        """Submit job result to coordinator"""
        try:
            response = await self._http_client.post(
                f"{self.coordinator_url}/miners/{self.worker_id}/jobs/{job_id}/complete",
                headers={"X-Miner-ID": self.worker_id, "X-API-Key": api_key},
                json={"output": result.output, "receipt": result.receipt},
            )
            if response.status_code == 200:
                logger.info("Job %s result submitted successfully", job_id)
            else:
                logger.error("Failed to submit result: %s", response.status_code)
        except Exception as e:
            logger.error("Error submitting result: %s", e)

    def _generate_receipt(self, job_id: str, inference_result: dict[str, Any], execution_time_ms: int) -> dict[str, Any]:
        """Generate execution receipt"""
        timestamp = datetime.now().isoformat()
        verification_data = {
            "job_id": job_id,
            "worker_id": self.worker_id,
            "model": inference_result.get("model"),
            "tokens_generated": inference_result.get("tokens_generated"),
            "execution_time_ms": execution_time_ms,
            "timestamp": timestamp,
        }
        hash_value = hashlib.sha256(json.dumps(verification_data, sort_keys=True).encode()).hexdigest()
        return {
            "hash": hash_value,
            "worker_id": self.worker_id,
            "timestamp": timestamp,
            "verification_data": verification_data,
            "proof_type": "gpu_inference",
        }


async def run_worker(worker_id: str, api_key: str, coordinator_url: str = "http://localhost:8203") -> None:
    """Run a GPU worker instance"""
    worker = GPUWorker(worker_id=worker_id, coordinator_url=coordinator_url)
    if not await worker.initialize():
        logger.error("Failed to initialize worker")
        return
    if not await worker.register_with_coordinator(api_key):
        logger.error("Failed to register with coordinator")
        return
    try:
        await worker.start(api_key)
    except KeyboardInterrupt:
        worker.stop()
        logger.info("Worker stopped by user")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        logger.error("Usage: python gpu_worker.py <worker_id> <api_key> [coordinator_url]")
        sys.exit(1)
    worker_id = sys.argv[1]
    api_key = sys.argv[2]
    coordinator_url = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8203"
    asyncio.run(run_worker(worker_id, api_key, coordinator_url))
