"""Monitoring Service for system health and metrics."""

from __future__ import annotations

import logging
import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
import httpx

logger = logging.getLogger(__name__)
app = FastAPI(
    title="AITBC Monitoring Service",
    description="System health and metrics monitoring service",
    version="1.0.0"
)

# Service endpoints configuration
SERVICES = {
    "gpu": {
        "name": "GPU Service",
        "port": 8101,
        "url": "http://localhost:8101",
        "description": "GPU marketplace and miner operations",
    },
    "marketplace": {
        "name": "Marketplace Service",
        "port": 8102,
        "url": "http://localhost:8102",
        "description": "Marketplace transactions",
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
    "ai": {
        "name": "AI Service",
        "port": 8106,
        "url": "http://localhost:8106",
        "description": "AI job operations",
    },
}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "monitoring-service"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AITBC Monitoring Service",
        "version": "1.0.0",
        "status": "operational"
    }


@app.get("/dashboard")
async def monitoring_dashboard() -> dict[str, Any]:
    """
    Unified monitoring dashboard for all services
    """
    try:
        # Collect health data from all services
        health_data = await collect_all_health_data()

        # Calculate overall metrics
        overall_metrics = calculate_overall_metrics(health_data)

        dashboard_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_metrics["overall_status"],
            "services": health_data,
            "metrics": overall_metrics,
            "summary": {
                "total_services": len(SERVICES),
                "healthy_services": len([s for s in health_data.values() if s.get("status") == "healthy"]),
                "degraded_services": len([s for s in health_data.values() if s.get("status") == "degraded"]),
                "unhealthy_services": len([s for s in health_data.values() if s.get("status") == "unhealthy"]),
                "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            },
        }

        logger.info("Monitoring dashboard data collected successfully")
        return dashboard_data

    except Exception as e:
        logger.error(f"Failed to generate monitoring dashboard: {e}")
        return {
            "error": "Failed to generate dashboard",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": SERVICES,
            "overall_status": "error",
            "summary": {
                "total_services": len(SERVICES),
                "healthy_services": 0,
                "degraded_services": 0,
                "unhealthy_services": len(SERVICES),
                "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            },
        }


@app.get("/dashboard/summary")
async def services_summary() -> dict[str, Any]:
    """
    Quick summary of all services status
    """
    try:
        health_data = await collect_all_health_data()

        summary = {"timestamp": datetime.utcnow().isoformat(), "services": {}}

        for service_id, service_info in SERVICES.items():
            health = health_data.get(service_id, {})
            summary["services"][service_id] = {
                "name": service_info["name"],
                "port": service_info["port"],
                "status": health.get("status", "unknown"),
                "description": service_info["description"],
                "last_check": health.get("timestamp"),
            }

        return summary

    except Exception as e:
        logger.error(f"Failed to generate services summary: {e}")
        return {"error": "Failed to generate summary", "timestamp": datetime.utcnow().isoformat()}


@app.get("/dashboard/metrics")
async def system_metrics() -> dict[str, Any]:
    """
    System-wide performance metrics
    """
    try:
        import psutil

        # System metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        # Network metrics
        network = psutil.net_io_counters()

        metrics = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system": {
                "cpu_percent": cpu_percent,
                "cpu_count": psutil.cpu_count(),
                "memory_percent": memory.percent,
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_percent": disk.percent,
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "disk_free_gb": round(disk.free / (1024**3), 2),
            },
            "network": {
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv,
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv,
            },
            "services": {
                "total_services": len(SERVICES),
                "service_names": list(SERVICES.keys()),
            },
        }

        return metrics

    except Exception as e:
        logger.error(f"Failed to collect system metrics: {e}")
        return {"error": "Failed to collect metrics", "timestamp": datetime.utcnow().isoformat()}


async def collect_all_health_data() -> dict[str, Any]:
    """Collect health data from all services"""
    health_data = {}

    tasks = []
    for service_id, service_info in SERVICES.items():
        task = check_service_health(service_id, service_info)
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, (service_id, service_info) in enumerate(SERVICES.items()):
        result = results[i]
        if isinstance(result, Exception):
            health_data[service_id] = {
                "status": "unhealthy",
                "error": str(result),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        else:
            health_data[service_id] = result

    return health_data


async def check_service_health(service_name: str, service_config: dict[str, Any]) -> dict[str, Any]:
    """
    Check health status of a specific service
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            health_url = f"{service_config['url']}/health"
            response = await client.get(health_url)
            return {
                "status": "healthy",
                "response_time": 0.1,
                "last_check": datetime.utcnow().isoformat(),
                "details": response.json(),
            }
    except Exception as e:
        logger.warning(f"Service {service_name} health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "last_check": datetime.utcnow().isoformat(),
        }


def calculate_overall_metrics(health_data: dict[str, Any]) -> dict[str, Any]:
    """Calculate overall system metrics from health data"""

    status_counts = {"healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0}

    for service_health in health_data.values():
        status = service_health.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    # Determine overall status
    if status_counts["unhealthy"] > 0:
        overall_status = "unhealthy"
    elif status_counts["degraded"] > 0:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return {
        "overall_status": overall_status,
        "status_counts": status_counts,
        "health_percentage": (status_counts["healthy"] / len(health_data)) * 100 if health_data else 0,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8107)
