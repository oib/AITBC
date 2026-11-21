"""
Real GPU Miner Client for AITBC - runs on host with actual GPU
"""

import asyncio
import os
import subprocess
import sys
import time
import urllib.parse
from datetime import UTC, datetime
from functools import partial
from typing import Any

import requests

from aitbc.aitbc_logging import configure_logging, get_logger
from aitbc.exceptions import NetworkError
from aitbc.media_guard import ffmpeg_input_guard
from aitbc.network import AITBCHTTPClient
from aitbc.utils.env import subprocess_env

import agent_task_executor
import ipfs_pinning_sweeper

# Job-execution phase lives in miner_job_execution (#1860); every moved name is
# re-exported here so ``production_miner.<name>`` keeps resolving for callers
# and for the tests' monkeypatch seams.
from miner_job_execution import (
    _FFMPEG_DEFAULT_MAX_OUTPUT_BYTES as _FFMPEG_DEFAULT_MAX_OUTPUT_BYTES,
    _FFMPEG_MAX_OUTPUT_MB_ENV as _FFMPEG_MAX_OUTPUT_MB_ENV,
    _GPU_COMPUTE_DEFAULT_MAX_SECONDS as _GPU_COMPUTE_DEFAULT_MAX_SECONDS,
    _GPU_COMPUTE_DEFAULT_SECONDS as _GPU_COMPUTE_DEFAULT_SECONDS,
    _GPU_COMPUTE_MAX_ENV as _GPU_COMPUTE_MAX_ENV,
    _MEDIA_DEFAULT_MAX_BYTES as _MEDIA_DEFAULT_MAX_BYTES,
    _MEDIA_MAX_BYTES_ENV as _MEDIA_MAX_BYTES_ENV,
    _MEDIA_MAX_REDIRECTS as _MEDIA_MAX_REDIRECTS,
    _MEDIA_TOTAL_DEADLINE_S as _MEDIA_TOTAL_DEADLINE_S,
    _OPS_ERRORS as _OPS_ERRORS,
    _SAFE_NAME_RE as _SAFE_NAME_RE,
    _check_media_url as _check_media_url,
    _duration_number as _duration_number,
    _execute_gpu_compute as _execute_gpu_compute,
    _execute_inference as _execute_inference,
    _execute_reencode as _execute_reencode,
    _execute_transcribe as _execute_transcribe,
    _ffmpeg_max_output_bytes as _ffmpeg_max_output_bytes,
    _fetch_http_media as _fetch_http_media,
    _gpu_compute_max_seconds as _gpu_compute_max_seconds,
    _gpu_compute_requested_seconds as _gpu_compute_requested_seconds,
    _job_deadline as _job_deadline,
    _media_max_bytes as _media_max_bytes,
    _require_safe_name as _require_safe_name,
    _safe_name as _safe_name,
    _shop_access_headers as _shop_access_headers,
    _stream_to_file as _stream_to_file,
    _write_data_uri as _write_data_uri,
    execute_job as execute_job,
)

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
# #2305: the region this miner registers under. Protected gpu_compute jobs carry
# constraints.region copied from the market GPU row, and dispatch silently skips
# a miner whose region differs, so the value must match MINER_GPU_REGION.
MINER_REGION = os.environ.get("MINER_REGION", "").strip() or "localhost"
# #2301: seconds between market GPU registry re-registers (self-heals a deleted
# row and corrects region/price drift without a miner restart).
MARKET_GPU_REREGISTER_INTERVAL = float(os.environ.get("MINER_GPU_REREGISTER_SECONDS", "300") or 300)
# #2305: minimum seconds between "poll skipped, at capacity" warnings.
_CAPACITY_WARN_INTERVAL = 60.0
_last_capacity_warn = 0.0
# #2305: consecutive job-poll failures are counted so a coordinator outage
# shows up in the journal instead of looking like a silent stall, and the
# poll cadence backs off while failures persist.
POLL_RETRY_MAX_SECONDS = 30.0
POLL_FAILURE_WARN_EVERY = 10
_poll_failures = 0
MAX_RETRIES = 10
RETRY_DELAY = 30
# In-memory set of job IDs currently running in worker threads. Used to report
# accurate inflight counts to the coordinator and to respect max_concurrent_jobs.
ACTIVE_JOB_IDS: set[str] = set()


def _claim_job_slot(job_id: str) -> bool:
    """Claim a job slot; False when the job is already running locally.

    The coordinator can re-offer a job that is still executing here (poll
    overlap, redelivery); without this check the miner would run it twice and
    submit a duplicate result (#1485).
    """
    if job_id in ACTIVE_JOB_IDS:
        return False
    ACTIVE_JOB_IDS.add(job_id)
    return True


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
    {
        "service_type": "ipfs",
        "model": "ipfs-host",
        "price": "0.01",
        "unit": "per_day",
        "description": "Island IPFS hosting",
    },
]
OFFER_PUBLISH_INTERVAL = 300
# Minimum seconds between pool-hub re-register attempts after a heartbeat 401
# (#2240): a miner that booted while the pool hub was down must re-register
# once the hub returns, without hammering /v1/miners/register every heartbeat.
POOL_HUB_REREGISTER_INTERVAL = 300.0
# time.time() deadline before which another re-register is not attempted.
_pool_hub_reregister_not_before = 0.0
# Default offers whose backing service must answer /health before the offer is
# published (#2099/#1549): the units are not deployed on every shop node, and
# an active offer with no backend sells a job that can never run.
_OFFER_BACKENDS = {
    "whisper": ("WHISPER_SERVICE_URL", "http://127.0.0.1:8110"),
    "ffmpeg": ("FFMPEG_SERVICE_URL", "http://127.0.0.1:8230"),
}
OFFER_BACKEND_PROBE_TIMEOUT = 3.0
# Provider-side IPFS hosting: pin CIDs for market ipfs jobs assigned to
# this miner so paid storage is actually stored locally (island daemon).
IPFS_PIN_SWEEP_INTERVAL = int(os.environ.get("IPFS_PIN_SWEEP_INTERVAL", "120"))
# Agent-to-agent paid delegation: poll the coordinator inbox for TaskRequest /
# TaskAccept messages and execute them against the local services.
AGENT_EXECUTOR_ENABLED = os.environ.get("AGENT_EXECUTOR_ENABLED", "false").lower() in ("true", "1", "yes")
AGENT_EXECUTOR_SWEEP_INTERVAL = int(os.environ.get("AGENT_EXECUTOR_SWEEP_INTERVAL", "30"))
AITBC_CLI = "/opt/aitbc/venv/bin/aitbc"


async def offer_publish_cycle(ollama_models: list[str]) -> bool:
    """One offer-publish cycle. When the island reports degraded (flag
    ISLAND_DEFER_ENABLED on the miner's own env, default off) the submits
    are skipped and one line is logged with the deferred count."""
    from aitbc.island_deferral import should_defer

    if should_defer("offer-publish"):
        logger.info("Deferred %d default offer(s) — island-degraded", len(DEFAULT_SOFTWARE_OFFERS))
        return False
    await asyncio.to_thread(publish_default_offers, ollama_models)
    return True


def _offer_backend_up(service_type: str) -> bool:
    """True when the service behind a default offer answers /health.

    Service types without a registered backend probe (ollama has its own model
    check, ipfs its own daemon) are not gated here.
    """
    probe = _OFFER_BACKENDS.get(service_type)
    if probe is None:
        return True
    env_name, default_url = probe
    url = os.environ.get(env_name, default_url).rstrip("/") + "/health"
    try:
        return requests.get(url, timeout=OFFER_BACKEND_PROBE_TIMEOUT).status_code == 200
    except _OPS_ERRORS:
        return False


def publish_default_offers(ollama_models: list[str]) -> None:
    """Publish default Whisper, FFmpeg and Ollama software offers.

    This is the shop-side equivalent of running `aitbc market offer` for each
    supported default service. The CLI skips the transaction when an identical
    active offer already exists, so this can be called every refresh cycle
    without creating duplicate listings.
    """
    published_tx = False
    deferred = 0
    for offer in DEFAULT_SOFTWARE_OFFERS:
        if published_tx:
            deferred += 1
            logger.info(
                "Deferring default offer %s/%s to next cycle (one nonce per cycle)",
                offer["service_type"],
                offer["model"],
            )
            continue
        if offer["service_type"] == "ollama" and offer["model"] not in ollama_models:
            logger.info("Skipping default offer for Ollama model %s (not available)", offer["model"])
            continue
        if not _offer_backend_up(offer["service_type"]):
            logger.warning(
                "Skipping default offer %s/%s: backend not reachable (#2099)", offer["service_type"], offer["model"]
            )
            continue
        cmd = [
            AITBC_CLI,
            "market",
            "offer",
            "--service-type",
            offer["service_type"],
            "--model-or-variant",
            offer["model"],
            "--price",
            offer["price"],
            "--unit",
            offer["unit"],
            "--description",
            offer["description"],
        ]
        try:
            # Ensure `aitbc market offer` uses the same address the coordinator expects
            # for provider payouts, because the default wallet may not exist or may
            # have insufficient balance to pay the listing fee.
            # `aitbc market offer` is a config-driven CLI child, not a leaf
            # tool: it legitimately needs the service's AITBC_*/SHOP_*/MINER_*
            # configuration — but not the blockchain-secrets.env secrets (#1760).
            env = subprocess_env(include_prefixes=("AITBC_", "SHOP_", "MINER_"))
            if MINER_WALLET_ADDRESS:
                env.setdefault("SHOP_WALLET_ADDRESS", MINER_WALLET_ADDRESS)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
            if result.returncode == 0:
                if "skipping" in (result.stdout or "").lower():
                    logger.info("Default offer unchanged: %s/%s", offer["service_type"], offer["model"])
                else:
                    logger.info("Published default offer: %s/%s", offer["service_type"], offer["model"])
                    published_tx = True
            else:
                logger.warning(
                    "Default offer %s/%s failed (rc=%s): stderr=%s stdout=%s",
                    offer["service_type"],
                    offer["model"],
                    result.returncode,
                    result.stderr[:500],
                    result.stdout[:500],
                )
        except _OPS_ERRORS as e:
            logger.warning("Error publishing default offer %s/%s: %s", offer["service_type"], offer["model"], e)
    if deferred:
        logger.info("Deferred %d default offer(s) to next refresh", deferred)


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
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            env=subprocess_env(),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except _OPS_ERRORS as e:
        logger.error("Failed to detect CUDA/driver version: %s", e)
    return None


def _max_concurrent_jobs() -> int:
    """Concurrent-job ceiling advertised to the coordinator.

    Reads MINER_MAX_CONCURRENT_JOBS on every call so a capacity change only
    needs a service restart. Values below 1 clamp to 1; an unparseable value
    falls back to 1 -- a bogus env var must never zero out mining.
    """
    raw = os.environ.get("MINER_MAX_CONCURRENT_JOBS", "1")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        logger.warning("Invalid MINER_MAX_CONCURRENT_JOBS=%r; defaulting to 1", raw)
        return 1


def build_gpu_capabilities() -> dict:
    gpu_info = get_gpu_info()
    cuda_version = detect_cuda_version() or "unknown"
    model = gpu_info["name"] if gpu_info else "Unknown GPU"
    memory_total = gpu_info["memory_total"] if gpu_info else 0
    arch = classify_architecture(model) if model else "unknown"
    edge_optimized = arch in {"ada_lovelace", "ampere", "turing"}
    ollama_available, models = check_ollama()
    return {  # not-money: ratio, threshold or configuration default — not an amount of money
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
        "region": MINER_REGION,
        "platform": "CUDA" if gpu_info else "CPU",
        "supported_tasks": ["inference", "training", "stable-diffusion", "llama", "transcribe", "reencode", "hermes"],
        "max_concurrent_jobs": _max_concurrent_jobs(),
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
            env=subprocess_env(),
        )
        if result.returncode == 0:
            info = result.stdout.strip().split(", ")
            return {"name": info[0], "memory_total": int(info[1]), "memory_used": int(info[2]), "utilization": int(info[3])}
    except _OPS_ERRORS as e:
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
    capabilities = build_gpu_capabilities()
    register_data = {
        "capabilities": capabilities,
        "concurrency": capabilities.get("max_concurrent_jobs", 1),
        "region": capabilities.get("region", MINER_REGION),
    }
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


def register_market_gpu() -> str | None:
    """Opt-in (#2291): list this miner's GPU in the coordinator market registry.

    Off unless ``MINER_REGISTER_GPU=1``. The route is idempotent per
    (miner, model, resource), so calling it on every start is safe. Failure
    is non-fatal: the miner still serves jobs without a marketplace row.
    """
    if os.environ.get("MINER_REGISTER_GPU", "").strip() != "1":
        return None
    gpu_info = get_gpu_info()
    if not gpu_info:
        logger.warning("MINER_REGISTER_GPU=1 but no GPU detected; skipping market GPU registration")
        return None
    specs = {
        "name": gpu_info["name"],
        "memory_gb": max(1, int(gpu_info["memory_total"]) // 1024),
        "price_per_hour": os.environ.get("MINER_GPU_PRICE_PER_HOUR", "0.05"),
        "region": os.environ.get("MINER_GPU_REGION", "").strip() or MINER_REGION,
    }
    resource_id = os.environ.get("MINER_GPU_RESOURCE_ID")
    if resource_id:
        specs["resource_id"] = resource_id
    headers = {"X-Api-Key": AUTH_TOKEN, "X-Miner-ID": MINER_ID, "Content-Type": "application/json"}
    try:
        client = AITBCHTTPClient(base_url=COORDINATOR_URL, headers=headers, timeout=10)
        response = client.post("/v1/market/gpu/register", json={"gpu": specs})
    except NetworkError as e:
        logger.warning("Market GPU registration failed: %s", e)
        return None
    gpu_id = response.get("gpu_id") if isinstance(response, dict) else None
    logger.info("Market GPU registered: %s", gpu_id)
    return gpu_id


def send_heartbeat():
    """Send heartbeat to coordinator with real GPU stats"""
    gpu_info = get_gpu_info()
    arch = classify_architecture(gpu_info["name"]) if gpu_info else "unknown"
    latency_ms = measure_coordinator_latency()
    inflight_count = len(ACTIVE_JOB_IDS)
    if gpu_info:
        heartbeat_data = {
            "status": "ONLINE",
            "inflight": inflight_count,
            "current_jobs": inflight_count,
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
            "inflight": inflight_count,
            "current_jobs": inflight_count,
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


def _total_ram_gb() -> float:
    """Host RAM in GiB, measured — never a hardcoded advertisement (#1484)."""
    try:
        return round(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / (1024**3), 1)
    except (ValueError, OSError, AttributeError):
        pass
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / (1024 * 1024), 1)
    except OSError:
        pass
    return 0.0


def build_pool_hub_register_data():
    """Build the payload the pool hub expects for miner registration."""
    gpu_info = get_gpu_info()
    caps = build_gpu_capabilities()
    return {  # not-money: ratio, threshold or configuration default — not an amount of money
        "miner_id": MINER_ID,
        "api_key": AUTH_TOKEN,
        "addr": MINER_ENDPOINT,
        "proto": "http",
        "gpu_vram_gb": (gpu_info["memory_total"] / 1024) if gpu_info else 0.0,
        "gpu_name": gpu_info["name"] if gpu_info else None,
        "cpu_cores": os.cpu_count() or 1,
        "ram_gb": _total_ram_gb(),
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
    inflight_count = len(ACTIVE_JOB_IDS)
    if gpu_info:
        return {
            "status": "active",
            "current_jobs": inflight_count,
            "gpu_utilization": gpu_info["utilization"],
            "memory_used": gpu_info["memory_used"],
            "memory_total": gpu_info["memory_total"],
            "network_latency_ms": latency_ms,
        }
    return {
        "status": "active",
        "current_jobs": inflight_count,
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


def send_pool_hub_heartbeat() -> str:
    """Send heartbeat to the pool hub.

    Returns ``"ok"`` on success, ``"unauthorized"`` on HTTP 401 (the pool hub
    does not know this miner's api key — it was never registered, e.g. the
    hub was down at miner boot, #2240), or ``"error"`` for anything else.
    Uses ``requests`` directly — like ``poll_for_jobs`` — so the status code
    is inspectable; ``AITBCHTTPClient`` wraps every failure in ``NetworkError``
    and loses it.
    """
    heartbeat_data = build_pool_hub_heartbeat_data()
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            f"{POOL_HUB_URL.rstrip('/')}/v1/miners/heartbeat", json=heartbeat_data, headers=headers, timeout=5
        )
    except _OPS_ERRORS as e:
        logger.error("Pool hub heartbeat error: %s", e)
        return "error"
    if response.status_code == 401:
        logger.error("Pool hub heartbeat rejected (401): miner is not registered with the pool hub")
        return "unauthorized"
    if response.ok:
        logger.info("Pool hub heartbeat sent")
        return "ok"
    logger.error("Pool hub heartbeat failed: HTTP %s", response.status_code)
    return "error"


def _download_media(url: str, dest: str) -> None:
    """Download an audio/video file from a URL (or data URI) to a local path."""
    try:
        cap = _media_max_bytes()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == "data":
            _write_data_uri(parsed, dest, cap)
            return
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"unsupported URL scheme: {parsed.scheme}")
        _fetch_http_media(url, dest, cap, time.monotonic() + _MEDIA_TOTAL_DEADLINE_S)
    except _OPS_ERRORS as e:
        raise RuntimeError(f"Failed to download media from {url}: {e}") from e


def _run_whisper(
    audio_path: str,
    model: str = "base",
    *,
    deterministic: bool = False,
    seed: int | None = None,
    access_headers: dict[str, str] | None = None,
) -> str:
    """Transcribe an audio file with the local Whisper service and return the text."""
    try:
        whisper_url = os.environ.get("WHISPER_SERVICE_URL", "http://127.0.0.1:8110").rstrip("/") + "/transcribe"
        with open(audio_path, "rb") as f:
            files = {"file": f}
            data = {"model": model, "task": "transcribe"}
            if deterministic:
                data["deterministic"] = "true"
            if seed is not None:
                data["seed"] = str(seed)
            resp = requests.post(whisper_url, files=files, data=data, headers=access_headers, timeout=180)
            resp.raise_for_status()
            result = resp.json()
        return str(result.get("text", "")).strip()
    except _OPS_ERRORS as e:
        raise RuntimeError(f"Whisper transcription failed: {e}") from e


def _run_ffmpeg(input_path: str, output_path: str, output_format: str | None = None) -> dict[str, Any]:
    """Re-encode a media file with FFmpeg. Returns summary metadata."""
    fmt = output_format or os.path.splitext(output_path)[1].lstrip(".") or "mp4"
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                *ffmpeg_input_guard(),
                "-i",
                input_path,
                "-f",
                fmt,
                # -fs bounds the output file itself (#1932 F7): bitrate is
                # capped but duration is not — ffmpeg exits non-zero at the
                # limit, which surfaces as a normal job failure.
                "-fs",
                str(_ffmpeg_max_output_bytes()),
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
            env=subprocess_env(),
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
        raise RuntimeError(f"FFmpeg re-encode failed: {e.stderr}") from e
    except _OPS_ERRORS as e:
        raise RuntimeError(f"FFmpeg re-encode error: {e}") from e


def _submit_success(job_id, output, execution_time, extra=None):
    gpu_after = get_gpu_info()
    extra = extra or {}
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
    submit_result(job_id, result)
    logger.info("Job %s completed in %ss", job_id, execution_time)


def _submit_failure(job_id, error_message):
    logger.error("Job execution error: %s", error_message)
    submit_result(job_id, {"result": {"status": "failed", "error": error_message}})


def _gpu_snapshot() -> dict[str, Any]:
    """Return a lightweight nvidia-smi snapshot, or an error dict."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            env=subprocess_env(),
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            if len(parts) >= 4:
                return {
                    "name": parts[0],
                    "utilization": int(parts[1]),
                    "memory_used_mb": int(parts[2]),
                    "memory_total_mb": int(parts[3]),
                }
    except _OPS_ERRORS as e:
        logger.warning("nvidia-smi snapshot failed: %s", e)
    return {}


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


def _note_poll_result(ok: bool) -> None:
    """Track consecutive job-poll failures (#2305).

    A successful exchange — a claimed job or an empty 204 — resets the
    counter; failures increment it. A WARNING fires every
    ``POLL_FAILURE_WARN_EVERY``-th failure and once on recovery, so a stall
    is visible in ``journalctl -u aitbc-miner`` while heartbeats keep
    flowing.
    """
    global _poll_failures
    if ok:
        if _poll_failures:
            logger.warning("Job poll recovered after %d consecutive failure(s)", _poll_failures)
        _poll_failures = 0
        return
    _poll_failures += 1
    if _poll_failures % POLL_FAILURE_WARN_EVERY == 0:
        logger.warning("Job poll failed %d time(s) in a row; backing off and retrying", _poll_failures)


def _poll_interval_seconds() -> float:
    """Seconds between poll cycles: 3s normally, exponential backoff capped
    at ``POLL_RETRY_MAX_SECONDS`` while polls keep failing (#2305)."""
    if _poll_failures <= 0:
        return 3.0
    return float(min(POLL_RETRY_MAX_SECONDS, 3.0 * 2 ** min(_poll_failures, 4)))


def poll_for_jobs():
    """Poll for available jobs"""
    poll_data = {"max_wait_seconds": 5}
    headers = {"X-Api-Key": AUTH_TOKEN, "X-Miner-ID": MINER_ID, "Content-Type": "application/json"}
    try:
        url = f"{COORDINATOR_URL}/v1/miners/poll"
        response = requests.post(url, json=poll_data, headers=headers, timeout=10)
        if response.status_code == 204:
            _note_poll_result(True)
            return None
        response.raise_for_status()
        job = response.json()
        if job and job.get("job_id"):
            logger.info("Received job: %s", job)
            _note_poll_result(True)
            return job
        else:
            _note_poll_result(True)
            return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 204:
            logger.debug("No jobs available (204 No Content)")
            _note_poll_result(True)
            return None
        _note_poll_result(False)
        logger.error("HTTP error polling for jobs: %s", e)
        return None
    except _OPS_ERRORS as e:
        _note_poll_result(False)
        logger.error("Error polling for jobs: %s", e)
        return None


async def _initialize() -> tuple[list, int] | None:
    """Startup sequence: GPU/Ollama probes, coordinator wait, miner + pool-hub
    registration, default offer publish. Returns (models, max_concurrent_jobs)
    or None when a fatal prerequisite failed."""
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
        return None
    session_token = register_miner()
    if not session_token:
        logger.error("Failed to register, exiting")
        return None
    logger.info("Miner registered successfully, starting main loop...")
    register_market_gpu()

    # Pool hub registration is best-effort: the miner still serves jobs if the
    # pool hub is unreachable, but visibility is required for discovery.
    pool_hub_registered = register_pool_hub()
    if not pool_hub_registered:
        logger.warning("Pool hub registration failed; continuing without pool-hub visibility")

    # Publish default Whisper/FFmpeg/Ollama software offers on startup so the
    # shop is discoverable through `aitbc market list` immediately.
    await asyncio.to_thread(publish_default_offers, models)

    capabilities = build_gpu_capabilities()
    max_concurrent_jobs = int(capabilities.get("max_concurrent_jobs", 1))
    return models, max_concurrent_jobs


async def _periodic_heartbeats(
    current_time: float, last_heartbeat: float, last_pool_hub_heartbeat: float, last_offer_publish: float, models: list
) -> tuple[float, float, float]:
    """Fire whichever heartbeat/publish interval has elapsed; returns the
    updated last-fired timestamps."""
    global _pool_hub_reregister_not_before
    if current_time - last_heartbeat >= HEARTBEAT_INTERVAL:
        send_heartbeat()
        last_heartbeat = current_time
    if current_time - last_pool_hub_heartbeat >= HEARTBEAT_INTERVAL:
        pool_hub_status = send_pool_hub_heartbeat()
        last_pool_hub_heartbeat = current_time
        # #2240: a 401 means the pool hub has no row for this miner's api key
        # (registration failed at boot, or the hub lost its state). Re-register
        # — throttled by POOL_HUB_REREGISTER_INTERVAL — so the miner becomes
        # visible again without a manual restart.
        if pool_hub_status == "unauthorized" and current_time >= _pool_hub_reregister_not_before:
            _pool_hub_reregister_not_before = current_time + POOL_HUB_REREGISTER_INTERVAL
            await asyncio.to_thread(register_pool_hub)
    if current_time - last_offer_publish >= OFFER_PUBLISH_INTERVAL:
        await offer_publish_cycle(models)
        last_offer_publish = current_time
    return last_heartbeat, last_pool_hub_heartbeat, last_offer_publish


async def _ipfs_sweep() -> None:
    """Best-effort IPFS pin sweep; failures are logged, never fatal."""
    try:
        await asyncio.to_thread(ipfs_pinning_sweeper.sweep_once, MINER_WALLET_ADDRESS)
    except Exception:
        logger.exception("IPFS hosting sweep failed")


async def _agent_executor_sweep() -> None:
    """Best-effort agent-task sweep; failures are logged, never fatal."""
    try:
        offer_map = {o["service_type"]: o for o in DEFAULT_SOFTWARE_OFFERS}
        stats = await asyncio.to_thread(agent_task_executor.sweep_once, MINER_WALLET_ADDRESS, offer_map)
        if any(stats.values()):
            logger.info("Agent executor sweep: %s", stats)
    except Exception:
        logger.exception("Agent executor sweep failed")


def _on_job_done(job_id: str, task: asyncio.Task) -> None:
    ACTIVE_JOB_IDS.discard(job_id)


def _warn_at_capacity(max_concurrent_jobs: int) -> None:
    """Rate-limited WARNING for a skipped poll (#2305).

    A slot that is never released makes the loop skip every poll while
    heartbeats keep flowing; at DEBUG that looked like a silent stall.
    """
    global _last_capacity_warn
    now = time.time()
    if now - _last_capacity_warn >= _CAPACITY_WARN_INTERVAL:
        _last_capacity_warn = now
        logger.warning(
            "At max capacity (%s/%s jobs: %s); skipping polls until a slot frees",
            len(ACTIVE_JOB_IDS),
            max_concurrent_jobs,
            sorted(ACTIVE_JOB_IDS),
        )


def fetch_running_jobs():
    """#2315: fetch this miner's RUNNING jobs in AssignedJob shape.

    ``/v1/miners/poll`` delivers a job only inside the claim response; a
    lost or failed response strands the row RUNNING coordinator-side with
    no local record. This read-only reconcile listing lets the miner
    redispatch what it never received (or forgot across a restart).
    """
    headers = {"X-Api-Key": AUTH_TOKEN, "X-Miner-ID": MINER_ID}
    try:
        url = f"{COORDINATOR_URL}/v1/miners/{MINER_ID}/running-jobs"
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        return [j for j in jobs if isinstance(j, dict) and j.get("job_id")]
    except _OPS_ERRORS as e:
        logger.error("Error fetching running jobs: %s", e)
        return []


def _dispatch_job(job: dict, models: list) -> None:
    """Atomic slot claim + worker-thread dispatch shared by the poll and
    reconcile paths. The claim is atomic (check-and-add with no await in
    between, on the single event-loop thread — #1485); if task creation
    itself fails, release the slot so the job is not locked out until
    restart."""
    job_id = job.get("job_id")
    if job_id and not _claim_job_slot(job_id):
        logger.debug("Job %s already running locally; skipping duplicate dispatch", job_id)
        return
    if not job_id:
        return
    # Run the blocking, potentially slow model execution in a
    # worker thread so heartbeats and the next poll continue.
    try:
        task = asyncio.create_task(asyncio.to_thread(execute_job, job, models))
    except Exception:
        ACTIVE_JOB_IDS.discard(job_id)
        raise
    task.add_done_callback(partial(_on_job_done, job_id))


def _reconcile_running_jobs(models: list, max_concurrent_jobs: int) -> None:
    """#2315: re-dispatch RUNNING jobs the coordinator says are ours but
    that this process does not hold — covers both the lost-poll-response
    case and jobs forgotten across a restart. ``_claim_job_slot`` dedups
    jobs already executing locally; capacity is respected per dispatch."""
    for job in fetch_running_jobs():
        if len(ACTIVE_JOB_IDS) >= max_concurrent_jobs:
            return
        _dispatch_job(job, models)


def _poll_and_dispatch(models: list, max_concurrent_jobs: int) -> None:
    """One poll cycle: capacity-guarded reconcile + job fetch, atomic slot
    claim, and worker-thread dispatch so heartbeats keep running.

    Any unexpected exception is logged and swallowed (#2305): the poll loop
    must keep retrying through coordinator outages instead of letting one
    bad cycle kill the main loop while heartbeats keep flowing.
    """
    # Only poll if we have capacity; the coordinator also checks
    # inflight, but a local guard avoids thundering-herd polls and
    # reflects the actual thread count.
    if len(ACTIVE_JOB_IDS) >= max_concurrent_jobs:
        _warn_at_capacity(max_concurrent_jobs)
        return
    try:
        _reconcile_running_jobs(models, max_concurrent_jobs)
        # Reconcile may have filled every slot; polling now would claim a job
        # server-side that cannot be dispatched locally until next cycle.
        if len(ACTIVE_JOB_IDS) >= max_concurrent_jobs:
            return
        job = poll_for_jobs()
        if job:
            _dispatch_job(job, models)
    except Exception:
        _note_poll_result(False)
        logger.exception("Job poll/dispatch cycle failed; will retry next cycle")


async def main():
    """Main miner loop"""
    logger.info("Starting Real GPU Miner Client on Host...")
    init = await _initialize()
    if init is None:
        return
    models, max_concurrent_jobs = init

    last_heartbeat = 0.0
    last_pool_hub_heartbeat = 0.0
    last_poll = 0.0
    last_ipfs_sweep = 0.0
    last_agent_sweep = 0.0
    last_market_gpu_register = time.time()

    # Set the initial publish time so the first loop iteration does not
    # immediately re-publish all default offers (time.time() - 0 is >> 300s).
    last_offer_publish = time.time()
    try:
        while True:
            current_time = time.time()
            last_heartbeat, last_pool_hub_heartbeat, last_offer_publish = await _periodic_heartbeats(
                current_time, last_heartbeat, last_pool_hub_heartbeat, last_offer_publish, models
            )
            if current_time - last_ipfs_sweep >= IPFS_PIN_SWEEP_INTERVAL:
                await _ipfs_sweep()
                last_ipfs_sweep = current_time
            if AGENT_EXECUTOR_ENABLED and current_time - last_agent_sweep >= AGENT_EXECUTOR_SWEEP_INTERVAL:
                await _agent_executor_sweep()
                last_agent_sweep = current_time
            if current_time - last_market_gpu_register >= MARKET_GPU_REREGISTER_INTERVAL:
                await asyncio.to_thread(register_market_gpu)
                last_market_gpu_register = current_time
            if current_time - last_poll >= _poll_interval_seconds():
                _poll_and_dispatch(models, max_concurrent_jobs)
                last_poll = current_time
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down miner...")
    except _OPS_ERRORS as e:
        logger.error("Error in main loop: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
