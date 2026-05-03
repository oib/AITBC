"""
Edge GPU Router
Handles edge GPU management endpoints
"""

import subprocess
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/edge-gpu", tags=["edge-gpu"])


class GPUProfile(BaseModel):
    """GPU profile model"""
    gpu_model: str
    architecture: str
    memory_gb: int
    edge_optimized: bool


class GPUMetrics(BaseModel):
    """GPU metrics model"""
    gpu_id: str
    timestamp: str
    utilization: float
    memory_used: float
    temperature: float


def run_nvidia_smi(args: list[str]) -> str:
    """Run nvidia-smi command and return output"""
    try:
        result = subprocess.run(
            ["nvidia-smi"] + args,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout
        else:
            return ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def parse_gpu_info() -> list[dict[str, Any]]:
    """Parse GPU information from nvidia-smi"""
    output = run_nvidia_smi(["--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"])
    if not output:
        return []
    
    gpus = []
    for line in output.strip().split("\n"):
        if line:
            parts = line.split(", ")
            if len(parts) >= 3:
                gpus.append({
                    "gpu_id": parts[0].strip(),
                    "name": parts[1].strip(),
                    "memory_mb": int(parts[2].strip())
                })
    return gpus


@router.get("/profiles")
async def list_profiles() -> dict[str, Any]:
    """List available edge GPU profiles"""
    gpus = parse_gpu_info()
    profiles = []
    for gpu in gpus:
        profiles.append({
            "gpu_id": gpu["gpu_id"],
            "gpu_model": gpu["name"],
            "architecture": "NVIDIA",
            "memory_gb": gpu["memory_mb"] // 1024,
            "edge_optimized": True
        })
    return {"profiles": profiles, "total": len(profiles)}


@router.get("/metrics/{gpu_id}")
async def get_gpu_metrics(gpu_id: str) -> dict[str, Any]:
    """Get metrics for a specific GPU"""
    output = run_nvidia_smi([
        "--query-gpu=utilization.gpu,memory.used,temperature.gpu",
        "--format=csv,noheader,nounits",
        f"--id={gpu_id}"
    ])
    if not output:
        return {"gpu_id": gpu_id, "error": "GPU not found or nvidia-smi unavailable"}
    
    parts = output.strip().split(", ")
    if len(parts) >= 3:
        return {
            "gpu_id": gpu_id,
            "utilization": float(parts[0].strip()),
            "memory_used_mb": float(parts[1].strip()),
            "temperature_c": float(parts[2].strip())
        }
    return {"gpu_id": gpu_id, "error": "Failed to parse metrics"}


@router.post("/metrics")
async def submit_metrics(metrics: GPUMetrics) -> dict[str, Any]:
    """Submit GPU metrics"""
    # In a real implementation, this would store metrics in a database
    return {"status": "success", "gpu_id": metrics.gpu_id}


@router.post("/discover")
async def discover_edge_gpus(miner_id: str) -> dict[str, Any]:
    """Discover and register edge GPUs for a miner"""
    gpus = parse_gpu_info()
    registered = len(gpus)
    edge_optimized = sum(1 for gpu in gpus if "RTX" in gpu["name"] or "GTX" in gpu["name"])
    
    return {
        "miner_id": miner_id,
        "gpus": [{"gpu_id": gpu["gpu_id"], "name": gpu["name"]} for gpu in gpus],
        "registered": registered,
        "edge_optimized": edge_optimized
    }


@router.post("/optimize")
async def optimize_inference(gpu_id: str, model_name: str, request_data: dict) -> dict[str, Any]:
    """Optimize ML inference request for edge GPU"""
    # In a real implementation, this would apply optimization techniques
    return {
        "gpu_id": gpu_id,
        "model_name": model_name,
        "optimized": True,
        "latency_reduction": 15.0,  # Mock value
        "note": "Optimization applied successfully"
    }
