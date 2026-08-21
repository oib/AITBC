"""
Real GPU Miner Client for AITBC - runs on host with actual GPU
"""

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from datetime import UTC, datetime
from typing import Any

import requests

from aitbc.aitbc_logging import configure_logging, get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AITBCHTTPClient

COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://127.0.0.1:8107")
# Pool Hub runs on the hub node. Shop/follower miners may set HUB_POOL_HUB_URL
# to reach it, or fall back to a local pool-hub for hub deployments.
POOL_HUB_URL = os.environ.get("POOL_HUB_URL") or os.environ.get("HUB_POOL_HUB_URL") or "http://127.0.0.1:8210"
# Public endpoint for this miner (used by the pool hub registry, not the client).
MINER_ENDPOINT = os.environ.get("MINER_ENDPOINT", "http://localhost:8101")
MINER_ID = os.environ.get("MINER_ID", "")
AUTH_TOKEN = os.environ.get("MINER_AUTH_TOKEN", os.environ.get("MINER_API_KEY", ""))
if not MINER_ID:
    raise RuntimeError("MINER_ID environment variable must be set — refusing to start without a public miner identifier")
if not AUTH_TOKEN:
    raise RuntimeError(
        "MINER_AUTH_TOKEN or MINER_API_KEY environment variable must be set — refusing to start with empty credentials"
    )
if MINER_ID == AUTH_TOKEN:
    raise RuntimeError("MINER_ID and the auth token must not be the same value; use separate MINER_ID and MINER_AUTH_TOKEN")
HEARTBEAT_INTERVAL = 15
MAX_RETRIES = 10
RETRY_DELAY = 30
coordinator_client = AITBCHTTPClient(
    base_url=COORDINATOR_URL, headers={"X-Api-Key": AUTH_TOKEN, "Content-Type": "application/json"}, timeout=30
)

# Use the canonical AITBC logging setup: JournalFormatter for console (no
# redundant timestamp — journalctl already adds one) and StructuredFormatter
# for the rotated log file (requires LOG_DIR env var, set in the unit file).
configure_logging(level="INFO", service_name="miner", to_file=True)
logger = get_logger(__name__)
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
sys.stderr.reconfigure(line_buffering=True)  # type: ignore[union-attr]
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
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], capture_output=True, text=True, timeout=5
        )
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
    ollama_available, models = check_ollama()
    return {
        "gpus": [
            {
                "name": model,
                "memory_mb": memory_total,
                "architecture": arch,
                "consumer_grade": True,
                "edge_optimized": edge_optimized,
            }
        ]
        if gpu_info
        else [],
        "cuda": cuda_version,
        "models": models if ollama_available else [],
        "price": 0.01,
        "region": "localhost",
        "platform": "CUDA" if gpu_info else "CPU",
        "supported_tasks": ["inference", "training", "stable-diffusion", "llama", "transcribe", "reencode"],
        "max_concurrent_jobs": 1,
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
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            info = result.stdout.strip().split(", ")
            return {"name": info[0], "memory_total": int(info[1]), "memory_used": int(info[2]), "utilization": int(info[3])}
    except Exception as e:
        logger.error("Failed to get GPU info: %s", e)
    return None


def check_ollama():
    """Check if Ollama is running and has models"""
    try:
        client = AITBCHTTPClient(base_url="http://localhost:11434", timeout=5)
        response = client.get("/api/tags")
        if response:
            models = response.get("models", [])
            model_names = [m["name"] for m in models]
            logger.info("Ollama running with models: %s", model_names)
            return (True, model_names)
        else:
            logger.error("Ollama not responding")
            return (False, [])
    except NetworkError as e:
        logger.error("Ollama check failed: %s", e)
        return (False, [])


async def wait_for_coordinator():
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
        logger.info("Waiting for coordinator... (%s/%s)", i + 1, MAX_RETRIES)
        await asyncio.sleep(RETRY_DELAY)
    logger.error("Coordinator not available after max retries")
    return False


def register_miner():
    """Register the miner with the coordinator"""
    register_data = {"capabilities": build_gpu_capabilities(), "concurrency": 1, "region": "localhost"}
    headers = {"X-Api-Key": AUTH_TOKEN, "X-Miner-ID": MINER_ID, "Content-Type": "application/json"}
    try:
        client = AITBCHTTPClient(base_url=COORDINATOR_URL, headers=headers, timeout=10)
        response = client.post("/v1/miners/register", json=register_data)
        if response:
            logger.info("Successfully registered miner: %s", response)
            token = response.get("session_token")
            if not token:
                logger.error("Registration succeeded but no session_token returned by coordinator")
                return None
            return token
        else:
            logger.error("Registration failed")
            return None
    except NetworkError as e:
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
    headers = {"X-Api-Key": AUTH_TOKEN, "X-Miner-ID": MINER_ID, "Content-Type": "application/json"}
    try:
        client = AITBCHTTPClient(base_url=COORDINATOR_URL, headers=headers, timeout=5)
        response = client.post("/v1/miners/heartbeat", json=heartbeat_data)
        if response:
            logger.info("Heartbeat sent (GPU: %s%%)", gpu_info["utilization"] if gpu_info else "N/A")
        else:
            logger.error("Heartbeat failed")
    except NetworkError as e:
        logger.error("Heartbeat error: %s", e)


def build_pool_hub_register_data():
    """Build the payload the pool hub expects for miner registration."""
    gpu_info = get_gpu_info()
    arch = classify_architecture(gpu_info["name"]) if gpu_info else "unknown"
    caps = build_gpu_capabilities()
    return {
        "miner_id": MINER_ID,
        "api_key": AUTH_TOKEN,
        "addr": MINER_ENDPOINT,
        "proto": "http",
        "gpu_vram_gb": (gpu_info["memory_total"] / 1024) if gpu_info else 0.0,
        "gpu_name": gpu_info["name"] if gpu_info else None,
        "cpu_cores": os.cpu_count() or 1,
        "ram_gb": 16.0,
        "max_parallel": caps.get("max_concurrent_jobs", 1),
        "base_price": str(caps.get("price", 0.01)),
        "tags": {"platform": caps.get("platform", "CPU"), "cuda": caps.get("cuda", "unknown")},
        "capabilities": caps.get("supported_tasks", ["inference"]),
        "region": caps.get("region", "localhost"),
    }


def build_pool_hub_heartbeat_data():
    """Build the payload the pool hub expects for a heartbeat."""
    gpu_info = get_gpu_info()
    latency_ms = measure_coordinator_latency()
    if gpu_info:
        return {
            "status": "active",
            "current_jobs": 0,
            "gpu_utilization": gpu_info["utilization"],
            "memory_used": gpu_info["memory_used"],
            "memory_total": gpu_info["memory_total"],
            "network_latency_ms": latency_ms,
        }
    return {
        "status": "active",
        "current_jobs": 0,
        "gpu_utilization": 0,
        "memory_used": 0,
        "memory_total": 0,
        "network_latency_ms": latency_ms,
    }


def register_pool_hub():
    """Register the miner with the pool hub so it appears in pool-hub status."""
    register_data = build_pool_hub_register_data()
    headers = {"Content-Type": "application/json"}
    try:
        client = AITBCHTTPClient(base_url=POOL_HUB_URL, headers=headers, timeout=10)
        response = client.post("/v1/miners/register", json=register_data)
        if response:
            logger.info("Successfully registered miner with pool hub: %s", response)
            return True
        logger.error("Pool hub registration failed: empty response")
        return False
    except NetworkError as e:
        logger.error("Pool hub registration error: %s", e)
        return False


def send_pool_hub_heartbeat():
    """Send heartbeat to the pool hub."""
    heartbeat_data = build_pool_hub_heartbeat_data()
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        client = AITBCHTTPClient(base_url=POOL_HUB_URL, headers=headers, timeout=5)
        response = client.post("/v1/miners/heartbeat", json=heartbeat_data)
        if response:
            logger.info("Pool hub heartbeat sent")
        else:
            logger.error("Pool hub heartbeat failed")
    except NetworkError as e:
        logger.error("Pool hub heartbeat error: %s", e)


def build_tee_quote(job):
    """Generate a simulated TEE attestation quote when the job requires one."""
    constraints = job.get("constraints") or {}
    if not (constraints.get("tee_attestation_required") or constraints.get("tee_enclave_id")):
        return None
    try:
        import base64
        from aitbc.tee import QuoteGenerator

        enclave_id = constraints.get("tee_enclave_id") or os.getenv("TEE_ENCLAVE_ID", "aitbc-miner-tee")
        job_id = job.get("job_id", "unknown-job")
        quote = QuoteGenerator(enclave_id).generate(quote_id=job_id, measurement=enclave_id)
        return base64.b64encode(quote.quote_blob).decode("ascii")
    except Exception as e:
        logger.warning("Failed to generate TEE quote for job %s: %s", job.get("job_id"), e)
        return None


def _download_media(url: str, dest: str) -> None:
    """Download an audio/video file from a URL to a local path."""
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as e:
        raise Exception(f"Failed to download media from {url}: {e}") from e


def _run_whisper(audio_path: str, model: str = "base") -> str:
    """Transcribe an audio file with OpenAI Whisper and return the text."""
    try:
        import whisper

        w = whisper.load_model(model)
        result = w.transcribe(audio_path, fp16=False)
        return result.get("text", "").strip()
    except Exception as e:
        raise Exception(f"Whisper transcription failed: {e}") from e


def _run_ffmpeg(input_path: str, output_path: str, output_format: str | None = None) -> dict[str, Any]:
    """Re-encode a media file with FFmpeg. Returns summary metadata."""
    fmt = output_format or os.path.splitext(output_path)[1].lstrip(".") or "mp4"
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, f"-f", fmt, output_path],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
        size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        return {
            "output_format": fmt,
            "output_path": output_path,
            "output_size_bytes": size,
            "stdout": result.stdout,
            "stderr": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFmpeg re-encode failed: {e.stderr}") from e
    except Exception as e:
        raise Exception(f"FFmpeg re-encode error: {e}") from e


def _submit_success(job_id, output, execution_time, extra=None):
    gpu_after = get_gpu_info()
    result = {
        "result": {
            "status": "completed",
            "output": output,
            "execution_time": execution_time,
            "gpu_used": bool(gpu_after),
            **(extra or {}),
        },
        "metrics": {
            "gpu_utilization": gpu_after["utilization"] if gpu_after else 0,
            "memory_used": gpu_after["memory_used"] if gpu_after else 0,
            "memory_peak": max(gpu_after["memory_used"] if gpu_after else 0, 2048),
            "duration_ms": int(execution_time * 1000),
        },
    }
    submit_result(job_id, result)
    logger.info("Job %s completed in %ss", job_id, execution_time)


def _submit_failure(job_id, error_message):
    logger.error("Job execution error: %s", error_message)
    submit_result(job_id, {"result": {"status": "failed", "error": error_message}})


def execute_job(job, available_models):
    """Execute a job using real GPU resources"""
    job_id = job.get("job_id")
    payload = job.get("payload", {})
    logger.info("Executing job %s: %s", job_id, payload)
    job_type = payload.get("type")
    if job_type is None and "model" in payload and ("prompt" in payload):
        job_type = "inference"

    try:
        if job_type == "inference":
            return _execute_inference(job, available_models)
        if job_type == "transcribe":
            return _execute_transcribe(job)
        if job_type == "reencode":
            return _execute_reencode(job)
        logger.error("Unsupported job type: %s", job_type)
        _submit_failure(job_id, f"Unsupported job type: {job_type}")
        return False
    except Exception as e:
        logger.error("Job execution error: %s", e)
        _submit_failure(job_id, str(e))
        return False


def _execute_inference(job, available_models):
    job_id = job.get("job_id")
    payload = job.get("payload", {})
    prompt = payload.get("prompt", "")
    model = payload.get("model", "llama3.2:latest")
    if model not in available_models:
        if available_models:
            model = available_models[0]
            logger.info("Using available model: %s", model)
        else:
            raise Exception("No models available in Ollama")
    logger.info("Running inference on GPU with model: %s", model)
    start_time = time.time()
    ollama_client = AITBCHTTPClient(base_url="http://localhost:11434", timeout=60)
    ollama_response = ollama_client.post("/api/generate", json={"model": model, "prompt": prompt, "stream": False})
    if ollama_response:
        result = ollama_response
        output = result.get("response", "")
        execution_time = time.time() - start_time
        tee_quote = build_tee_quote(job)
        extra = {"model": model, "tokens_processed": result.get("eval_count", 0)}
        if tee_quote:
            extra["tee_quote"] = tee_quote
            logger.info("Attaching TEE quote for job %s", job_id)
        _submit_success(job_id, output, execution_time, extra)
        return True
    logger.error("Ollama error")
    _submit_failure(job_id, "Ollama error")
    return False


def _execute_transcribe(job):
    job_id = job.get("job_id")
    payload = job.get("payload", {})
    url = payload.get("url") or payload.get("input")
    if not url:
        raise Exception("Transcribe job requires 'url' or 'input' in payload")
    model = payload.get("model", "base")
    logger.info("Running transcription with model: %s", model)
    start_time = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        ext = os.path.splitext(url.split("?")[0])[1] or ".wav"
        input_path = os.path.join(tmp, f"input{ext}")
        _download_media(url, input_path)
        text = _run_whisper(input_path, model)
    execution_time = time.time() - start_time
    _submit_success(job_id, text, execution_time, {"model": model, "transcription": text})
    return True


def _execute_reencode(job):
    job_id = job.get("job_id")
    payload = job.get("payload", {})
    url = payload.get("url") or payload.get("input")
    if not url:
        raise Exception("Re-encode job requires 'url' or 'input' in payload")
    output_format = payload.get("output_format") or payload.get("format") or "mp4"
    logger.info("Running re-encode to format: %s", output_format)
    start_time = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        input_ext = os.path.splitext(url.split("?")[0])[1] or ".bin"
        input_path = os.path.join(tmp, f"input{input_ext}")
        _download_media(url, input_path)
        output_path = os.path.join(tmp, f"output.{output_format}")
        summary = _run_ffmpeg(input_path, output_path, output_format)
    execution_time = time.time() - start_time
    _submit_success(job_id, summary["stderr"], execution_time, summary)
    return True


def submit_result(job_id, result):
    """Submit job result to coordinator"""
    headers = {"X-Api-Key": AUTH_TOKEN, "X-Miner-ID": MINER_ID, "Content-Type": "application/json"}
    try:
        client = AITBCHTTPClient(base_url=COORDINATOR_URL, headers=headers, timeout=10)
        response = client.post(f"/v1/miners/{job_id}/result", json=result)
        if response:
            logger.info("Result submitted for job %s", job_id)
        else:
            logger.error("Result submission failed")
    except NetworkError as e:
        logger.error("Result submission error: %s", e)


def poll_for_jobs():
    """Poll for available jobs"""
    poll_data = {"max_wait_seconds": 5}
    headers = {"X-Api-Key": AUTH_TOKEN, "X-Miner-ID": MINER_ID, "Content-Type": "application/json"}
    try:
        url = f"{COORDINATOR_URL}/v1/miners/poll"
        response = requests.post(url, json=poll_data, headers=headers, timeout=10)
        if response.status_code == 204:
            return None
        response.raise_for_status()
        job = response.json()
        if job and job.get("job_id"):
            logger.info("Received job: %s", job)
            return job
        else:
            return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 204:
            logger.debug("No jobs available (204 No Content)")
            return None
        logger.error("HTTP error polling for jobs: %s", e)
        return None
    except Exception as e:
        logger.error("Error polling for jobs: %s", e)
        return None


async def main():
    """Main miner loop"""
    logger.info("Starting Real GPU Miner Client on Host...")
    gpu_info = get_gpu_info()
    if not gpu_info:
        logger.warning("GPU not available, running in CPU-only mode")
        gpu_info = {"name": "CPU-Only", "memory_total": 0, "memory_used": 0, "utilization": 0}
    else:
        logger.info("GPU detected: %s (%sMB)", gpu_info["name"], gpu_info["memory_total"])
    ollama_available, models = check_ollama()
    if not ollama_available:
        logger.warning("Ollama not available - miner will not be able to execute inference jobs")
        models = []
    else:
        logger.info("Ollama models available: %s", ", ".join(models))
    if not await wait_for_coordinator():
        logger.error("Coordinator not available")
        return
    session_token = register_miner()
    if not session_token:
        logger.error("Failed to register, exiting")
        return
    logger.info("Miner registered successfully, starting main loop...")

    # Pool hub registration is best-effort: the miner still serves jobs if the
    # pool hub is unreachable, but visibility is required for discovery.
    pool_hub_registered = register_pool_hub()
    if not pool_hub_registered:
        logger.warning("Pool hub registration failed; continuing without pool-hub visibility")

    last_heartbeat = 0.0
    last_pool_hub_heartbeat = 0.0
    last_poll = 0.0
    try:
        while True:
            current_time = time.time()
            if current_time - last_heartbeat >= HEARTBEAT_INTERVAL:
                send_heartbeat()
                last_heartbeat = current_time
            if current_time - last_pool_hub_heartbeat >= HEARTBEAT_INTERVAL:
                send_pool_hub_heartbeat()
                last_pool_hub_heartbeat = current_time
            if current_time - last_poll >= 3:
                job = poll_for_jobs()
                if job:
                    execute_job(job, models)
                last_poll = current_time
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down miner...")
    except Exception as e:
        logger.error("Error in main loop: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
