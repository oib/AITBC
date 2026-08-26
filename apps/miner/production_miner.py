"""
Real GPU Miner Client for AITBC - runs on host with actual GPU
"""

import asyncio
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse

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
# G2: the address escrow releases are paid to. The coordinator will not hand this
# miner an escrowed job unless it matches the escrow's provider, so an unset value
# means the miner only ever sees unpriced work.
MINER_WALLET_ADDRESS = os.environ.get("MINER_WALLET_ADDRESS", "")
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

# Default software service offers the shop publishes on startup and refreshes
# periodically. These match the canonical `aitbc market offer` command.
DEFAULT_SOFTWARE_OFFERS = [
    {
        "service_type": "whisper",
        "model": "base",
        "price": "0.02",
        "unit": "per_audio_min",
        "description": "Default Whisper base transcription",
    },
    {
        "service_type": "ffmpeg",
        "model": "h264-transcode",
        "price": "0.005",
        "unit": "per_processing_hour",
        "description": "Default FFmpeg h264 transcoding",
    },
    {
        "service_type": "ollama",
        "model": "llama3.2:3b",
        "price": "0.001",
        "unit": "per_1k_tokens",
        "description": "Default Ollama llama3.2:3b inference",
    },
]
OFFER_PUBLISH_INTERVAL = 300
AITBC_CLI = "/opt/aitbc/venv/bin/aitbc"


def publish_default_offers(ollama_models: list[str]) -> None:
    """Publish default Whisper, FFmpeg and Ollama software offers.

    This is the shop-side equivalent of running `aitbc market offer` for each
    supported default service. It is idempotent: the marketplace service
    updates an existing offer with the same (service_type, model) key.
    """
    for offer in DEFAULT_SOFTWARE_OFFERS:
        if offer["service_type"] == "ollama" and offer["model"] not in ollama_models:
            logger.info("Skipping default offer for Ollama model %s (not available)", offer["model"])
            continue
        cmd = [
            AITBC_CLI,
            "market",
            "offer",
            offer["service_type"],
            offer["model"],
            offer["price"],
            "--unit",
            offer["unit"],
            "--description",
            offer["description"],
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                logger.info("Published default offer: %s/%s", offer["service_type"], offer["model"])
            else:
                logger.warning(
                    "Default offer %s/%s failed (rc=%s): stderr=%s stdout=%s",
                    offer["service_type"],
                    offer["model"],
                    result.returncode,
                    result.stderr[:500],
                    result.stdout[:500],
                )
        except Exception as e:
            logger.warning("Error publishing default offer %s/%s: %s", offer["service_type"], offer["model"], e)


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
    if MINER_WALLET_ADDRESS:
        register_data["wallet_address"] = MINER_WALLET_ADDRESS
    else:
        logger.warning("MINER_WALLET_ADDRESS is not set; the coordinator will not assign escrowed (paid) jobs to this miner")
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
            "status": "ONLINE",
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
            "status": "ONLINE",
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
    """Generate a signed TEE attestation quote when the job requires one.

    Produces the same base64 JSON envelope that ``aitbc tee attest`` returns,
    so the coordinator can parse it with ``AttestationQuote.from_base64()`` and
    verify the signature before escrow release.
    """
    constraints = job.get("constraints") or {}
    if not (constraints.get("tee_attestation_required") or constraints.get("tee_enclave_id")):
        return None
    try:
        from aitbc.tee import QuoteGenerator, load_or_create_signing_key

        enclave_id = str(
            constraints.get("tee_enclave_id")
            or constraints.get("required_enclave_measurement")
            or os.getenv("TEE_ENCLAVE_ID", "aitbc-miner-tee")
        )
        job_id = job.get("job_id", "unknown-job")
        quote_id = f"tee-{job_id}-{enclave_id}-{datetime.now(UTC).isoformat()}"
        # Security fix (2026-08-24), part 4: without TEE_SIGNING_KEY_FILE this
        # still signs with a fresh random key every call, same as before --
        # harmless today since nothing is registered to pin against, but it
        # means 'aitbc tee register' only protects future quotes once this is
        # set to a persistent path (see 'aitbc tee keygen').
        key_path = os.getenv("TEE_SIGNING_KEY_FILE", "")
        signing_key = load_or_create_signing_key(key_path) if key_path else None
        quote = QuoteGenerator(enclave_id, signing_key=signing_key).generate(
            quote_id=quote_id, enclave_id=enclave_id, measurement=enclave_id, report_data=job_id.encode()
        )
        return quote.to_base64()
    except Exception as e:
        logger.warning("Failed to generate TEE quote for job %s: %s", job.get("job_id"), e)
        return None


def _download_media(url: str, dest: str) -> None:
    """Download an audio/video file from a URL to a local path."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"unsupported URL scheme: {parsed.scheme}")
        with requests.get(url, timeout=30, stream=True) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        raise Exception(f"Failed to download media from {url}: {e}") from e


def _run_whisper(audio_path: str, model: str = "base") -> str:
    """Transcribe an audio file with OpenAI Whisper and return the text."""
    try:
        import whisper

        w = whisper.load_model(model)
        result = w.transcribe(audio_path, fp16=False)
        return str(result.get("text", "")).strip()
    except Exception as e:
        raise Exception(f"Whisper transcription failed: {e}") from e


def _run_ffmpeg(input_path: str, output_path: str, output_format: str | None = None) -> dict[str, Any]:
    """Re-encode a media file with FFmpeg. Returns summary metadata."""
    fmt = output_format or os.path.splitext(output_path)[1].lstrip(".") or "mp4"
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-f", fmt, output_path],
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


def _submit_success(job_id, output, execution_time, extra=None, tee_quote=None):
    gpu_after = get_gpu_info()
    # Pop tee_quote from extra if it was placed there by older callers.
    extra = extra or {}
    tee_quote = tee_quote or extra.pop("tee_quote", None)
    result = {
        "result": {
            "status": "completed",
            "output": output,
            "execution_time": execution_time,
            "gpu_used": bool(gpu_after),
            **extra,
        },
        "metrics": {
            "gpu_utilization": gpu_after["utilization"] if gpu_after else 0,
            "memory_used": gpu_after["memory_used"] if gpu_after else 0,
            "memory_peak": max(gpu_after["memory_used"] if gpu_after else 0, 2048),
            "duration_ms": int(execution_time * 1000),
        },
    }
    if tee_quote:
        result["tee_quote"] = tee_quote
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
    ollama_client = AITBCHTTPClient(base_url="http://localhost:11434", timeout=180)
    ollama_payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 24,
            "temperature": 0.7,
        },
    }
    ollama_response = ollama_client.post("/api/generate", json=ollama_payload)
    if ollama_response:
        result = ollama_response
        output = result.get("response", "")
        execution_time = time.time() - start_time
        tee_quote = build_tee_quote(job)
        extra = {"model": model, "tokens_processed": result.get("eval_count", 0)}
        if tee_quote:
            logger.info("Attaching TEE quote for job %s", job_id)
        _submit_success(job_id, output, execution_time, extra, tee_quote=tee_quote)
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
    tee_quote = build_tee_quote(job)
    if tee_quote:
        logger.info("Attaching TEE quote for job %s", job_id)
    _submit_success(job_id, text, execution_time, {"model": model, "transcription": text}, tee_quote=tee_quote)
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
    tee_quote = build_tee_quote(job)
    if tee_quote:
        logger.info("Attaching TEE quote for job %s", job_id)
    _submit_success(job_id, summary["stderr"], execution_time, summary, tee_quote=tee_quote)
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

    # Publish default Whisper/FFmpeg/Ollama software offers on startup so the
    # shop is discoverable through `aitbc market list` immediately.
    await asyncio.to_thread(publish_default_offers, models)

    last_heartbeat = 0.0
    last_pool_hub_heartbeat = 0.0
    last_poll = 0.0
    # Set the initial publish time so the first loop iteration does not
    # immediately re-publish all default offers (time.time() - 0 is >> 300s).
    last_offer_publish = time.time()
    try:
        while True:
            current_time = time.time()
            if current_time - last_heartbeat >= HEARTBEAT_INTERVAL:
                send_heartbeat()
                last_heartbeat = current_time
            if current_time - last_pool_hub_heartbeat >= HEARTBEAT_INTERVAL:
                send_pool_hub_heartbeat()
                last_pool_hub_heartbeat = current_time
            if current_time - last_offer_publish >= OFFER_PUBLISH_INTERVAL:
                await asyncio.to_thread(publish_default_offers, models)
                last_offer_publish = current_time
            if current_time - last_poll >= 3:
                job = poll_for_jobs()
                if job:
                    # Run the blocking, potentially slow model execution in a
                    # worker thread so heartbeats and the next poll continue.
                    asyncio.create_task(asyncio.to_thread(execute_job, job, models))
                last_poll = current_time
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down miner...")
    except Exception as e:
        logger.error("Error in main loop: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
