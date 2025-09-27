from __future__ import annotations

import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import psutil


@dataclass
class CapabilitySnapshot:
    capabilities: Dict[str, Any]
    concurrency: int
    region: str | None = None


def collect_capabilities(max_cpu_concurrency: int, max_gpu_concurrency: int) -> CapabilitySnapshot:
    cpu_count = psutil.cpu_count(logical=True) or 1
    total_mem = psutil.virtual_memory().total
    gpu_info = _detect_gpus()

    capabilities: Dict[str, Any] = {
        "node": platform.node(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "cpu": {
            "logical_cores": cpu_count,
            "model": platform.processor(),
        },
        "memory": {
            "total_bytes": total_mem,
            "total_gb": round(total_mem / (1024**3), 2),
        },
        "runners": {
            "cli": True,
            "python": True,
        },
    }

    if gpu_info:
        capabilities["gpus"] = gpu_info

    concurrency = max(1, max_cpu_concurrency, max_gpu_concurrency if gpu_info else 0)
    return CapabilitySnapshot(capabilities=capabilities, concurrency=concurrency)


def collect_runtime_metrics() -> Dict[str, Any]:
    vm = psutil.virtual_memory()
    load_avg = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0, 0, 0)
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "load_avg": load_avg,
        "memory_percent": vm.percent,
        "timestamp": time.time(),
    }


def _detect_gpus() -> List[Dict[str, Any]]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return []
    try:
        output = subprocess.check_output(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader"
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    gpus: List[Dict[str, Any]] = []
    for line in output.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if not parts:
            continue
        name = parts[0]
        mem_mb = None
        if len(parts) > 1 and parts[1].lower().endswith(" mib"):
            try:
                mem_mb = int(float(parts[1].split()[0]))
            except ValueError:
                mem_mb = None
        gpus.append({"name": name, "memory_mb": mem_mb})
    return gpus
