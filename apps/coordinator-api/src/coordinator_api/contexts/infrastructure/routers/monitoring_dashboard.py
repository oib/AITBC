"""
Monitoring Dashboard
Provides a unified dashboard for the node's deployed services
"""

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import AITBCError, NetworkError
from aitbc.network import AITBCHTTPClient
from aitbc.rate_limiting import rate_limit

from ....storage import get_session

logger = get_logger(__name__)
router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# Expected failure surface for the monitoring endpoints: filesystem/JSON,
# data-shape, runtime, lazy in-function imports (psutil, sqlmodel domain
# modules), SQLAlchemy session errors and the aitbc error hierarchy
# (AITBCHTTPClient re-raises RateLimitError / CircuitBreakerOpenError
# unwrapped). BaseExceptions still propagate.
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    IndexError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
    SQLAlchemyError,
    AITBCError,
)
# The retired "enhanced services" list (multimodal :8002, gpu_multimodal
# :8003, modality_optimization :8004, adaptive_learning :8005,
# market_enhanced :8202, agent_enhanced :8007) read a healthy fleet as
# unhealthy — none of those units exist post-#1549 (#2409). The default is
# now the core services that actually answer /health on a hub deployment;
# deployments with a different roster override it wholesale via
# MONITORING_DASHBOARD_SERVICES (JSON object keyed by service id, same shape
# as below) — there is no way to probe "whatever systemd thinks is running"
# from inside this process.
_DEFAULT_SERVICES = {
    "market": {
        "name": "Market Service",
        "port": 8102,
        "url": "http://localhost:8102",
        "description": "Market transactions",
    },
    "trading": {
        "name": "Trading Service",
        "port": 8104,
        "url": "http://localhost:8104",
        "description": "Trading and explorer operations",
    },
    "governance": {
        "name": "Governance Service",
        "port": 8105,
        "url": "http://localhost:8105",
        "description": "Governance transactions",
    },
    "explorer": {
        "name": "Blockchain Explorer",
        "port": 8100,
        "url": "http://localhost:8100",
        "description": "Blockchain explorer API",
    },
    "pool_hub": {
        "name": "Pool Hub",
        "port": 8210,
        "url": "http://localhost:8210",
        "description": "GPU pool hub",
    },
}


def _dashboard_services() -> dict[str, Any]:
    """The probed service map: env override wins, else the deployed default."""
    raw = os.getenv("MONITORING_DASHBOARD_SERVICES", "").strip()
    if not raw:
        return _DEFAULT_SERVICES
    try:
        parsed = json.loads(raw)
    except ValueError:
        logger.warning("MONITORING_DASHBOARD_SERVICES is not valid JSON — using defaults")
        return _DEFAULT_SERVICES
    if not isinstance(parsed, dict) or not parsed:
        logger.warning("MONITORING_DASHBOARD_SERVICES must be a non-empty object — using defaults")
        return _DEFAULT_SERVICES
    return parsed


SERVICES = _dashboard_services()


@router.get("/dashboard", tags=["monitoring"], summary="Enhanced Services Dashboard")
@rate_limit(rate=200, per=60)
async def monitoring_dashboard(request: Request) -> dict[str, Any]:
    """
    Unified monitoring dashboard for all enhanced services
    """
    try:
        health_data = await collect_all_health_data()
        overall_metrics = calculate_overall_metrics(health_data)
        dashboard_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "overall_status": overall_metrics["overall_status"],
            "services": health_data,
            "metrics": overall_metrics,
            "summary": {
                "total_services": len(SERVICES),
                "healthy_services": len([s for s in health_data.values() if s.get("status") == "healthy"]),
                "degraded_services": len([s for s in health_data.values() if s.get("status") == "degraded"]),
                "unhealthy_services": len([s for s in health_data.values() if s.get("status") == "unhealthy"]),
                "last_updated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            },
        }
        logger.info("Monitoring dashboard data collected successfully")
        return dashboard_data
    except _OPS_ERRORS as e:
        logger.error("Failed to generate monitoring dashboard: %s", e)
        return {
            "error": "Failed to generate dashboard",
            "timestamp": datetime.now(UTC).isoformat(),
            "services": SERVICES,
            "overall_status": "error",
            "summary": {
                "total_services": len(SERVICES),
                "healthy_services": 0,
                "degraded_services": 0,
                "unhealthy_services": len(SERVICES),
                "last_updated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            },
        }


@router.get("/dashboard/summary", tags=["monitoring"], summary="Services Summary")
@rate_limit(rate=200, per=60)
async def services_summary(request: Request) -> dict[str, Any]:
    """
    Quick summary of all services status
    """
    try:
        health_data = await collect_all_health_data()
        summary: dict[str, Any] = {"timestamp": datetime.now(UTC).isoformat(), "services": {}}
        for service_id, service_info in SERVICES.items():
            health = health_data.get(service_id, {})
            summary["services"][service_id] = {
                "name": service_info["name"],
                "port": service_info["port"],
                "status": health.get("status", "unknown"),
                "description": service_info.get("description", ""),
                "icon": service_info.get("icon", ""),
                "last_check": health.get("timestamp"),
            }
        return summary
    except _OPS_ERRORS as e:
        logger.error("Failed to generate services summary: %s", e)
        return {"error": "Failed to generate summary", "timestamp": datetime.now(UTC).isoformat()}


@router.get("/dashboard/metrics", tags=["monitoring"], summary="System Metrics")
@rate_limit(rate=200, per=60)
def system_metrics(request: Request) -> dict[str, Any]:
    """
    System-wide performance metrics
    """
    try:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        network = psutil.net_io_counters()
        metrics = {
            "timestamp": datetime.now(UTC).isoformat(),
            "system": {
                "cpu_percent": cpu_percent,
                "cpu_count": psutil.cpu_count(),
                "memory_percent": memory.percent,
                "memory_total_gb": round(memory.total / 1024**3, 2),
                "memory_available_gb": round(memory.available / 1024**3, 2),
                "disk_percent": disk.percent,
                "disk_total_gb": round(disk.total / 1024**3, 2),
                "disk_free_gb": round(disk.free / 1024**3, 2),
            },
            "network": {
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv,
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv,
            },
            "services": {
                "total_ports": list(SERVICES.values()),
                "expected_services": len(SERVICES),
                "port_range": "8002-8007",
            },
        }
        return metrics
    except _OPS_ERRORS as e:
        logger.error("Failed to collect system metrics: %s", e)
        return {"error": "Failed to collect metrics", "timestamp": datetime.now(UTC).isoformat()}


async def collect_all_health_data() -> dict[str, Any]:
    """Collect health data from all enhanced services"""
    health_data = {}
    tasks = []
    for service_id, service_info in SERVICES.items():
        task = check_service_health(service_id, service_info)
        tasks.append(task)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, (service_id, _service_info) in enumerate(SERVICES.items()):
        result = results[i]
        if isinstance(result, Exception):
            health_data[service_id] = {"status": "unhealthy", "error": str(result), "timestamp": datetime.now(UTC).isoformat()}
        else:
            health_data[service_id] = result  # type: ignore[assignment]
    return health_data


async def check_service_health(service_name: str, service_config: dict[str, Any]) -> dict[str, Any]:  # noqa: fake-async — scheduled via asyncio.gather in collect_all_health_data
    """
    Check health status of a specific service
    """
    try:
        client = AITBCHTTPClient(timeout=2.0, max_retries=0)
        health_url = f"{service_config['url']}/health"
        started = time.monotonic()
        response = client.get(health_url)
        elapsed = time.monotonic() - started
        return {
            "status": "healthy",
            "response_time": round(elapsed, 3),
            "last_check": datetime.now(UTC).isoformat(),
            "details": response,
        }
    except NetworkError as e:
        logger.warning("Service %s health check failed: %s", service_name, e)
        return {"status": "unhealthy", "error": str(e), "last_check": datetime.now(UTC).isoformat()}
    except _OPS_ERRORS as e:
        return {"status": "unhealthy", "error": str(e), "timestamp": datetime.now(UTC).isoformat()}


def calculate_overall_metrics(health_data: dict[str, Any]) -> dict[str, Any]:
    """Calculate overall system metrics from health data"""
    status_counts = {"healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0}
    total_response_time = 0.0
    response_time_count = 0
    for service_health in health_data.values():
        status = service_health.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        if "response_time" in service_health:
            try:
                # Stored as float seconds by check_service_health; tolerate a
                # legacy "0.123s" string just in case an older payload arrives.
                raw = service_health["response_time"]
                total_response_time += float(str(raw).removesuffix("s"))
                response_time_count += 1
            except (ValueError, AttributeError, TypeError):
                pass
    if status_counts["unhealthy"] > 0:
        overall_status = "unhealthy"
    elif status_counts["degraded"] > 0:
        overall_status = "degraded"
    else:
        overall_status = "healthy"
    avg_response_time = total_response_time / response_time_count if response_time_count > 0 else 0
    return {
        "overall_status": overall_status,
        "status_counts": status_counts,
        "average_response_time": f"{avg_response_time:.3f}s",
        "health_percentage": status_counts["healthy"] / len(health_data) * 100 if health_data else 0,
    }


_JOB_BUCKETS = {
    "COMPLETED": "completed",
    "FAILED": "failed",
    "QUEUED": "pending",
    "ASSIGNED": "pending",
    "RUNNING": "pending",
    "CANCELED": "canceled",
    "EXPIRED": "expired",
}


def _job_bucket(state: str | None) -> str:
    """Map a job state onto a metrics bucket; unknown states get "other".

    Every state lands in exactly one bucket so the buckets always sum to
    total — canceled/expired were silently dropped before #2409, and the
    CLI's success_rate read those unbucketed jobs as failures.
    """
    return _JOB_BUCKETS.get((state or "").upper(), "other")


@router.get("/metrics", tags=["monitoring"], summary="Full monitoring metrics")
@rate_limit(rate=100, per=60)
def monitoring_metrics_route(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Return coordinator, job, miner, and system metrics for the CLI monitor group."""
    from sqlmodel import select

    from ...infrastructure.domain.job import Job
    from ...infrastructure.domain.miner import Miner

    metrics: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "coordinator": {"status": "online"},
        "jobs": {
            "total": 0,
            "completed": 0,
            "pending": 0,
            "failed": 0,
            "canceled": 0,
            "expired": 0,
            "other": 0,
        },
        "miners": {
            "total": 0,
            "online": 0,
            "offline": 0,
        },
    }

    try:
        from sqlalchemy import func

        # Count in SQL — loading every Job/Miner row per call does not scale
        # (#2715). Grouped counts bucket the same way the row loop did.
        for state, count in session.exec(select(Job.state, func.count()).group_by(Job.state)).all():
            metrics["jobs"]["total"] += count
            metrics["jobs"][_job_bucket(state)] += count

        miner_rows = session.exec(select(Miner.status, func.count()).group_by(Miner.status)).all()
        metrics["miners"]["total"] = sum(count for _, count in miner_rows)
        metrics["miners"]["online"] = sum(count for status, count in miner_rows if status == "ONLINE")
        metrics["miners"]["offline"] = metrics["miners"]["total"] - metrics["miners"]["online"]
    except _OPS_ERRORS as e:
        logger.error("Failed to collect job/miner metrics: %s", e)

    # Add system metrics
    try:
        import psutil

        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        metrics["system"] = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": memory.percent,
            "memory_available_gb": memory.available / (1024**3),
            "disk_percent": disk.percent,
        }
    except _OPS_ERRORS:
        metrics["system"] = {}

    return metrics
