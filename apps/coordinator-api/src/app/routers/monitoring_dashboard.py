"""
Enhanced Services Monitoring Dashboard
Provides a unified dashboard for all 6 enhanced services
"""

import asyncio
from datetime import datetime, UTC
from typing import Any

from fastapi import APIRouter

from aitbc import get_logger, AITBCHTTPClient, NetworkError

logger = get_logger(__name__)

router = APIRouter()

# Service endpoints configuration
SERVICES = {
    "multimodal": {
        "name": "Multi-Modal Agent Service",
        "port": 8002,
        "url": "http://localhost:8002",
        "description": "Text, image, audio, video processing",
        "icon": "🤖",
    },
    "gpu_multimodal": {
        "name": "GPU Multi-Modal Service",
        "port": 8003,
        "url": "http://localhost:8003",
        "description": "CUDA-optimized processing",
        "icon": "🚀",
    },
    "modality_optimization": {
        "name": "Modality Optimization Service",
        "port": 8004,
        "url": "http://localhost:8004",
        "description": "Specialized optimization strategies",
        "icon": "⚡",
    },
    "adaptive_learning": {
        "name": "Adaptive Learning Service",
        "port": 8005,
        "url": "http://localhost:8005",
        "description": "Reinforcement learning frameworks",
        "icon": "🧠",
    },
    "marketplace_enhanced": {
        "name": "Enhanced Marketplace Service",
        "port": 8006,
        "url": "http://localhost:8006",
        "description": "NFT 2.0, royalties, analytics",
        "icon": "🏪",
    },
    "openclaw_enhanced": {
        "name": "OpenClaw Enhanced Service",
        "port": 8007,
        "url": "http://localhost:8007",
        "description": "Agent orchestration, edge computing",
        "icon": "🌐",
    },
}


@router.get("/dashboard", tags=["monitoring"], summary="Enhanced Services Dashboard")
async def monitoring_dashboard() -> dict[str, Any]:
    """
    Unified monitoring dashboard for all enhanced services
    """
    try:
        # Collect health data from all services
        health_data = await collect_all_health_data()

        # Calculate overall metrics
        overall_metrics = calculate_overall_metrics(health_data)

        dashboard_data = {
            "timestamp": datetime.now(datetime.UTC).isoformat(),
            "overall_status": overall_metrics["overall_status"],
            "services": health_data,
            "metrics": overall_metrics,
            "summary": {
                "total_services": len(SERVICES),
                "healthy_services": len([s for s in health_data.values() if s.get("status") == "healthy"]),
                "degraded_services": len([s for s in health_data.values() if s.get("status") == "degraded"]),
                "unhealthy_services": len([s for s in health_data.values() if s.get("status") == "unhealthy"]),
                "last_updated": datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            },
        }

        # In production, this would render a template
        # return templates.TemplateResponse("dashboard.html", {"request": request, "data": dashboard_data})

        logger.info("Monitoring dashboard data collected successfully")
        return dashboard_data

    except Exception as e:
        logger.error(f"Failed to generate monitoring dashboard: {e}")
        return {
            "error": "Failed to generate dashboard",
            "timestamp": datetime.now(datetime.UTC).isoformat(),
            "services": SERVICES,
            "overall_status": "error",
            "summary": {
                "total_services": len(SERVICES),
                "healthy_services": 0,
                "degraded_services": 0,
                "unhealthy_services": len(SERVICES),
                "last_updated": datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            },
        }


@router.get("/dashboard/summary", tags=["monitoring"], summary="Services Summary")
async def services_summary() -> dict[str, Any]:
    """
    Quick summary of all services status
    """
    try:
        health_data = await collect_all_health_data()

        summary = {"timestamp": datetime.now(datetime.UTC).isoformat(), "services": {}}

        for service_id, service_info in SERVICES.items():
            health = health_data.get(service_id, {})
            summary["services"][service_id] = {
                "name": service_info["name"],
                "port": service_info["port"],
                "status": health.get("status", "unknown"),
                "description": service_info["description"],
                "icon": service_info["icon"],
                "last_check": health.get("timestamp"),
            }

        return summary

    except Exception as e:
        logger.error(f"Failed to generate services summary: {e}")
        return {"error": "Failed to generate summary", "timestamp": datetime.now(datetime.UTC).isoformat()}


@router.get("/dashboard/metrics", tags=["monitoring"], summary="System Metrics")
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
            "timestamp": datetime.now(datetime.UTC).isoformat(),
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
                "total_ports": list(SERVICES.values()),
                "expected_services": len(SERVICES),
                "port_range": "8002-8007",
            },
        }

        return metrics

    except Exception as e:
        logger.error(f"Failed to collect system metrics: {e}")
        return {"error": "Failed to collect metrics", "timestamp": datetime.now(datetime.UTC).isoformat()}


async def collect_all_health_data() -> dict[str, Any]:
    """Collect health data from all enhanced services"""
    health_data = {}

    client = AITBCHTTPClient(timeout=5.0)
    tasks = []

    for service_id, service_info in SERVICES.items():
        task = check_service_health(client, service_id, service_info)
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, (service_id, service_info) in enumerate(SERVICES.items()):
        result = results[i]
        if isinstance(result, Exception):
            health_data[service_id] = {
                "status": "unhealthy",
                "error": str(result),
                "timestamp": datetime.now(datetime.UTC).isoformat(),
            }
        else:
            health_data[service_id] = result

    return health_data


async def check_service_health(service_name: str, service_config: dict[str, Any]) -> dict[str, Any]:
    """
    Check health status of a specific service
    """
    try:
        client = AITBCHTTPClient(timeout=5.0)
        health_url = f"{service_config['url']}/health"
        response = client.get(health_url)
        return {
            "status": "healthy",
            "response_time": 0.1,  # Placeholder - would be measured
            "last_check": datetime.now(datetime.UTC).isoformat(),
            "details": response,
        }
    except NetworkError as e:
        logger.warning(f"Service {service_name} health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "last_check": datetime.now(datetime.UTC).isoformat(),
        }
        return {"status": "unhealthy", "error": "connection refused", "timestamp": datetime.now(datetime.UTC).isoformat()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e), "timestamp": datetime.now(datetime.UTC).isoformat()}


def calculate_overall_metrics(health_data: dict[str, Any]) -> dict[str, Any]:
    """Calculate overall system metrics from health data"""

    status_counts = {"healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0}

    total_response_time = 0
    response_time_count = 0

    for service_health in health_data.values():
        status = service_health.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        if "response_time" in service_health:
            try:
                # Extract numeric value from response time string
                time_str = service_health["response_time"].replace("s", "")
                total_response_time += float(time_str)
                response_time_count += 1
            except:
                pass

    # Determine overall status
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
        "health_percentage": (status_counts["healthy"] / len(health_data)) * 100 if health_data else 0,
        "uptime_estimate": "99.9%",  # Mock data - would calculate from historical data
    }
