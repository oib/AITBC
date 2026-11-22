#!/usr/bin/env python3
"""
AITBC Miner Management Module
Complete command-line interface for AI compute miner operations including:
- Miner Registration
- Status Management
- Job Polling & Execution
- Market Integration
- Payment Management
"""

import json
import os
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import requests

# Default configuration
DEFAULT_COORDINATOR_URL = os.getenv("COORDINATOR_URL", "http://127.0.0.1:8203")
DEFAULT_API_KEY = os.getenv("MINER_API_KEY", "")


def _admin_api_key(api_key: str) -> str:
    """Credential for admin-scoped calls (#2594).

    ``ADMIN_API_KEY`` is the fleet's real admin credential; the legacy
    ``miner_``→``admin_`` string rewrite stays only as a fallback for
    callers that have no admin key configured. Read at call time so a
    rotated env var takes effect without re-import.
    """
    return os.getenv("ADMIN_API_KEY") or api_key.replace("miner_", "admin_")


def _build_register_caps(
    gpu_memory: int | None,
    models: list | None,
    pricing: float | None,
    capabilities: str | None,
) -> dict[str, int | float | str | list]:
    # Build capabilities from arguments
    caps: dict[str, int | float | str | list] = {}

    if gpu_memory:
        caps["gpu_memory"] = gpu_memory
        caps["gpu_memory_gb"] = gpu_memory
    if models:
        caps["models"] = models
        caps["supported_models"] = models
    if pricing:
        caps["pricing_per_hour"] = pricing
        caps["price_per_hour"] = pricing
        caps["gpu"] = "AI-GPU"
        caps["gpu_count"] = 1
        caps["cuda_version"] = "12.0"

    # Override with capabilities JSON if provided
    if capabilities:
        caps.update(json.loads(capabilities))
    return caps


def _build_update_caps(
    gpu_memory: int | None,
    models: list | None,
    pricing: float | None,
    capabilities: str | None,
) -> dict[str, int | float | str | list]:
    # Build capabilities from arguments
    caps: dict[str, int | float | str | list] = {}
    if gpu_memory:
        caps["gpu_memory"] = gpu_memory
        caps["gpu_memory_gb"] = gpu_memory
    if models:
        caps["models"] = models
        caps["supported_models"] = models
    if pricing:
        caps["pricing_per_hour"] = pricing
        caps["price_per_hour"] = pricing

    # Override with capabilities JSON if provided
    if capabilities:
        caps.update(json.loads(capabilities))
    return caps


def register_miner(
    miner_id: str,
    wallet: str,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    capabilities: str | None = None,
    gpu_memory: int | None = None,
    models: list | None = None,
    pricing: float | None = None,
    concurrency: int = 1,
    region: str | None = None,
) -> dict | None:
    """Register miner as AI compute provider"""
    try:
        headers = {"X-Api-Key": api_key, "X-Miner-ID": miner_id, "Content-Type": "application/json"}

        caps = _build_register_caps(gpu_memory, models, pricing, capabilities)

        payload = {"wallet_address": wallet, "capabilities": caps, "concurrency": concurrency, "region": region}

        response = requests.post(f"{coordinator_url}/v1/miners/register", headers=headers, json=payload, timeout=30)

        if response.status_code == 200:
            result = response.json()
            return {
                "action": "register",
                "miner_id": miner_id,
                "status": "✅ Registered successfully",
                "session_token": result.get("session_token"),
                "coordinator_url": coordinator_url,
                "capabilities": caps,
            }
        else:
            return {
                "action": "register",
                "status": "❌ Registration failed",
                "error": response.text,
                "status_code": response.status_code,
            }

    except requests.exceptions.ConnectionError as e:
        return {"action": "register", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "register", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "register", "status": f"❌ HTTP error: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"action": "register", "status": f"❌ JSON decode error: {str(e)}"}
    except Exception as e:  # noqa: BLE001 - top-level CLI boundary reports the error in the status dict
        return {"action": "register", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def get_miner_status(
    miner_id: str, api_key: str = DEFAULT_API_KEY, coordinator_url: str = DEFAULT_COORDINATOR_URL
) -> dict | None:
    """Get miner status and statistics"""
    try:
        # Use admin API key to get miner status
        headers = {"X-Api-Key": _admin_api_key(api_key)}

        response = requests.get(f"{coordinator_url}/v1/admin/miners", headers=headers, timeout=30)

        if response.status_code == 200:
            miners = response.json().get("items", [])
            miner_info = next((m for m in miners if m["miner_id"] == miner_id), None)

            if miner_info:
                return {
                    "action": "status",
                    "miner_id": miner_id,
                    "status": f"✅ {miner_info['status']}",
                    "inflight": miner_info["inflight"],
                    "concurrency": miner_info["concurrency"],
                    "region": miner_info["region"],
                    "last_heartbeat": miner_info["last_heartbeat"],
                    "jobs_completed": miner_info["jobs_completed"],
                    "jobs_failed": miner_info["jobs_failed"],
                    "average_job_duration_ms": miner_info["average_job_duration_ms"],
                    "success_rate": (
                        miner_info["jobs_completed"] / max(1, miner_info["jobs_completed"] + miner_info["jobs_failed"]) * 100
                    ),
                }
            else:
                return {"action": "status", "miner_id": miner_id, "status": "❌ Miner not found"}
        else:
            return {"action": "status", "status": "❌ Failed to get status", "error": response.text}

    except requests.exceptions.ConnectionError as e:
        return {"action": "status", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "status", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "status", "status": f"❌ HTTP error: {str(e)}"}
    except (KeyError, StopIteration) as e:
        return {"action": "status", "status": f"❌ Data processing error: {str(e)}"}
    except Exception as e:  # noqa: BLE001 - top-level CLI boundary reports the error in the status dict
        return {"action": "status", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def send_heartbeat(
    miner_id: str,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    inflight: int = 0,
    status: str = "ONLINE",
) -> dict | None:
    """Send miner heartbeat"""
    try:
        headers = {"X-Api-Key": api_key, "X-Miner-ID": miner_id, "Content-Type": "application/json"}

        payload = {
            "inflight": inflight,
            "status": status,
            "metadata": {"timestamp": time.time(), "version": "1.0.0", "system_info": "AI Compute Miner"},
        }

        response = requests.post(f"{coordinator_url}/v1/miners/heartbeat", headers=headers, json=payload, timeout=30)

        if response.status_code == 200:
            return {
                "action": "heartbeat",
                "miner_id": miner_id,
                "status": "✅ Heartbeat sent successfully",
                "inflight": inflight,
                "miner_status": status,
            }
        else:
            return {"action": "heartbeat", "status": "❌ Heartbeat failed", "error": response.text}

    except requests.exceptions.ConnectionError as e:
        return {"action": "heartbeat", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "heartbeat", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "heartbeat", "status": f"❌ HTTP error: {str(e)}"}
    except Exception as e:  # noqa: BLE001 - top-level CLI boundary reports the error in the status dict
        return {"action": "heartbeat", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def poll_jobs(
    miner_id: str,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    max_wait: int = 30,
    auto_execute: bool = False,
) -> dict | None:
    """Poll for available jobs"""
    try:
        headers = {"X-Api-Key": api_key, "X-Miner-ID": miner_id, "Content-Type": "application/json"}

        payload = {"max_wait_seconds": max_wait}

        response = requests.post(f"{coordinator_url}/v1/miners/poll", headers=headers, json=payload, timeout=30)

        if response.status_code == 200 and response.content:
            job = response.json()
            result = {
                "action": "poll",
                "miner_id": miner_id,
                "status": "✅ Job assigned",
                "job_id": job.get("job_id"),
                "payload": job.get("payload"),
                "constraints": job.get("constraints"),
                "assigned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            if auto_execute:
                result["auto_execution"] = "🤖 Job execution would start here"
                result["execution_status"] = "Ready to execute"

            return result
        elif response.status_code == 204:
            return {"action": "poll", "miner_id": miner_id, "status": "⏸️ No jobs available", "message": "No jobs in queue"}
        else:
            return {"action": "poll", "status": "❌ Poll failed", "error": response.text}

    except requests.exceptions.ConnectionError as e:
        return {"action": "poll", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "poll", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "poll", "status": f"❌ HTTP error: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"action": "poll", "status": f"❌ JSON decode error: {str(e)}"}
    except Exception as e:  # noqa: BLE001 - top-level CLI boundary reports the error in the status dict
        return {"action": "poll", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def submit_job_result(
    job_id: str,
    miner_id: str,
    result: str,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    success: bool = True,
    duration: int | None = None,
    result_file: str | None = None,
) -> dict | None:
    """Submit job result"""
    try:
        headers = {"X-Api-Key": api_key, "X-Miner-ID": miner_id, "Content-Type": "application/json"}

        # Load result from file if specified
        if result_file:
            with open(result_file) as f:
                result = f.read()

        # #1816: JobResultSubmit is schema-allowlisted — result is an object
        # (no top-level "success" field); the flag maps onto result.status.
        payload = {
            "result": {"output": result, "status": "completed" if success else "failed"},
            "metrics": {"duration_ms": duration, "completed_at": time.time()},
        }

        response = requests.post(f"{coordinator_url}/v1/miners/{job_id}/result", headers=headers, json=payload, timeout=30)

        if response.status_code == 200:
            return {
                "action": "result",
                "job_id": job_id,
                "miner_id": miner_id,
                "status": "✅ Result submitted successfully",
                "success": success,
                "duration_ms": duration,
            }
        else:
            return {"action": "result", "status": "❌ Result submission failed", "error": response.text}

    except requests.exceptions.ConnectionError as e:
        return {"action": "result", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "result", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "result", "status": f"❌ HTTP error: {str(e)}"}
    except (OSError, FileNotFoundError, PermissionError) as e:
        return {"action": "result", "status": f"❌ File error: {type(e).__name__}: {str(e)}"}
    except Exception as e:  # noqa: BLE001 - top-level CLI boundary reports the error in the status dict
        return {"action": "result", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def _fetch_miner_record(miner_id: str, api_key: str, coordinator_url: str) -> tuple[dict | None, dict | None]:
    """Current admin view of one miner: ``(record, error_payload)``.

    Exactly one of the two is non-None. Used by ``update_capabilities``
    to merge partial updates onto the stored record — the PUT route
    replaces capabilities/concurrency/region wholesale, so a partial
    body would silently wipe the rest (#2537).
    """
    try:
        response = requests.get(
            f"{coordinator_url}/v1/admin/miners",
            headers={"X-Api-Key": _admin_api_key(api_key)},
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        return None, {"error": f"cannot read current miner record: {e}"}
    if response.status_code != 200:
        return None, {"error": f"cannot read current miner record: HTTP {response.status_code}"}
    try:
        miners = response.json().get("items", [])
    except ValueError:
        return None, {"error": "cannot read current miner record: invalid response"}
    record = next((m for m in miners if isinstance(m, dict) and m.get("miner_id") == miner_id), None)
    if record is None:
        return None, {"error": f"miner {miner_id} not found"}
    return record, None


def update_capabilities(
    miner_id: str,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    capabilities: str | None = None,
    gpu_memory: int | None = None,
    models: list | None = None,
    pricing: float | None = None,
    concurrency: int | None = None,
    region: str | None = None,
    wallet: str | None = None,
) -> dict | None:
    """Update miner capabilities.

    The PUT route replaces the stored record, so this merges the requested
    fields onto the miner's current capabilities/concurrency/region
    (#2537) — a partial update can no longer null out fields the caller
    did not mention or wipe capabilities it did not resend.
    """
    try:
        current, fetch_error = _fetch_miner_record(miner_id, api_key, coordinator_url)
        if current is None:
            return {"action": "update", "status": "❌ Update failed", **(fetch_error or {})}

        caps = _build_update_caps(gpu_memory, models, pricing, capabilities)
        merged_caps = dict(current.get("capabilities") or {})
        merged_caps.update(caps)

        payload = {
            "capabilities": merged_caps,
            "concurrency": concurrency if concurrency is not None else current.get("concurrency", 1),
            "region": region if region is not None else current.get("region"),
        }

        if wallet:
            payload["wallet_address"] = wallet

        headers = {"X-Api-Key": api_key, "X-Miner-ID": miner_id, "Content-Type": "application/json"}

        response = requests.put(
            f"{coordinator_url}/v1/miners/{miner_id}/capabilities", headers=headers, json=payload, timeout=30
        )

        if response.status_code == 200:
            return {
                "action": "update",
                "miner_id": miner_id,
                "status": "✅ Capabilities updated successfully",
                "updated_capabilities": merged_caps,
            }
        else:
            return {"action": "update", "status": "❌ Update failed", "error": response.text}

    except requests.exceptions.ConnectionError as e:
        return {"action": "update", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "update", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "update", "status": f"❌ HTTP error: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"action": "update", "status": f"❌ JSON decode error: {str(e)}"}
    except Exception as e:  # noqa: BLE001 - top-level CLI boundary reports the error in the status dict
        return {"action": "update", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


# Period spellings accepted by check_earnings → days of history.
_EARNINGS_PERIOD_DAYS = {"day": 1, "24h": 1, "week": 7, "7d": 7, "month": 30, "30d": 30}


def _earnings_error(miner_id: str, period: str, status: str) -> dict:
    """Failure payload for check_earnings — no fabricated zero totals (#2565)."""
    return {"action": "earnings", "miner_id": miner_id, "period": period, "status": status}


def check_earnings(
    miner_id: str, api_key: str = DEFAULT_API_KEY, coordinator_url: str = DEFAULT_COORDINATOR_URL, period: str = "all"
) -> dict | None:
    """Check miner earnings via POST /v1/miners/{id}/earnings (#2565).

    The route is POST-only; the old GET on /jobs returned 405 and the
    caller reported 0.00 earnings with a failure string.
    """
    headers = {"X-API-Key": api_key}
    params: dict[str, str] = {}
    days = _EARNINGS_PERIOD_DAYS.get(period)
    if days is not None:
        params["from_time"] = (datetime.now() - timedelta(days=days)).isoformat()

    try:
        response = requests.post(
            f"{coordinator_url}/v1/miners/{miner_id}/earnings",
            headers=headers,
            params=params,
            timeout=30,
        )
    except requests.exceptions.ConnectionError as e:
        return _earnings_error(miner_id, period, f"❌ Connection error: {e}")
    except requests.exceptions.Timeout as e:
        return _earnings_error(miner_id, period, f"❌ Request timeout: {e}")
    except requests.exceptions.RequestException as e:
        return _earnings_error(miner_id, period, f"❌ Request failed: {e}")

    if response.status_code != 200:
        return _earnings_error(miner_id, period, f"❌ Failed to query earnings: HTTP {response.status_code}")

    try:
        data = response.json()
    except ValueError as e:
        return _earnings_error(miner_id, period, f"❌ Invalid response from server: {e}")

    total = Decimal(str(data.get("total_earnings") or "0"))
    completed = int(data.get("completed_jobs") or 0)
    average = str(total / completed) if completed > 0 else "0"

    return {
        "action": "earnings",
        "miner_id": miner_id,
        "period": period,
        "status": "📊 Earnings calculated",
        "total_earnings": str(total),
        "pending_earnings": str(data.get("pending_earnings") or "0"),
        "paid_earnings": str(data.get("paid_earnings") or "0"),
        "jobs_completed": completed,
        "average_payment": average,
        "currency": data.get("currency") or "AITBC",
    }


def list_market_offers(
    miner_id: str | None = None,
    region: str | None = None,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
) -> dict | None:
    """List market offers"""
    try:
        admin_headers = {"X-Api-Key": _admin_api_key(api_key)}

        params = {}
        if region:
            params["region"] = region

        response = requests.get(f"{coordinator_url}/v1/market/miner-offers", headers=admin_headers, params=params, timeout=30)

        if response.status_code == 200:
            offers = response.json()

            # Filter by miner if specified — exact match on the offer's
            # miner identity field (#2595). The old substring scan over
            # str(o) matched "miner-1" inside "miner-10" and missed ids
            # with uppercase characters.
            if miner_id:
                offers = [
                    o
                    for o in offers
                    if isinstance(o, dict) and str(o.get("provider_id") or o.get("provider") or "") == miner_id
                ]

            return {
                "action": "market_list",
                "status": "✅ Offers retrieved",
                "offers": offers,
                "count": len(offers),
                "region_filter": region,
                "miner_filter": miner_id,
            }
        else:
            return {"action": "market_list", "status": "❌ Failed to get offers", "error": response.text}

    except requests.exceptions.ConnectionError as e:
        return {"action": "market_list", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "market_list", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "market_list", "status": f"❌ HTTP error: {str(e)}"}
    except Exception as e:  # noqa: BLE001 - top-level CLI boundary reports the error in the status dict
        return {"action": "market_list", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


def create_market_offer(
    miner_id: str,
    price: Decimal,
    api_key: str = DEFAULT_API_KEY,
    coordinator_url: str = DEFAULT_COORDINATOR_URL,
    capacity: int = 1,
    region: str | None = None,
) -> dict | None:
    """Create market offer"""
    try:
        admin_headers = {"X-Api-Key": _admin_api_key(api_key)}

        payload = {"miner_id": miner_id, "price": str(price), "capacity": capacity, "region": region}

        response = requests.post(f"{coordinator_url}/v1/market/offers", headers=admin_headers, json=payload, timeout=30)

        if response.status_code == 200:
            return {
                "action": "market_create",
                "miner_id": miner_id,
                "status": "✅ Offer created successfully",
                "price": str(price),
                "capacity": capacity,
                "region": region,
            }
        else:
            return {"action": "market_create", "status": "❌ Offer creation failed", "error": response.text}

    except requests.exceptions.ConnectionError as e:
        return {"action": "market_create", "status": f"❌ Connection error: {str(e)}"}
    except requests.exceptions.Timeout as e:
        return {"action": "market_create", "status": f"❌ Timeout error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        return {"action": "market_create", "status": f"❌ HTTP error: {str(e)}"}
    except Exception as e:  # noqa: BLE001 - top-level CLI boundary reports the error in the status dict
        return {"action": "market_create", "status": f"❌ Unexpected error: {type(e).__name__}: {str(e)}"}


# Main function for CLI integration
def miner_cli_dispatcher(action: str, **kwargs) -> dict[Any, Any]:
    """Main dispatcher for miner management CLI commands"""

    actions: dict[str, Any] = {
        "register": register_miner,
        "status": get_miner_status,
        "heartbeat": send_heartbeat,
        "poll": poll_jobs,
        "result": submit_job_result,
        "update": update_capabilities,
        "earnings": check_earnings,
        "market_list": list_market_offers,
        "market_create": create_market_offer,
    }

    if action in actions:
        result = actions[action](**kwargs)
        return result  # type: ignore[no-any-return]
    else:
        return {"action": action, "status": f"❌ Unknown action. Available: {', '.join(actions.keys())}"}
