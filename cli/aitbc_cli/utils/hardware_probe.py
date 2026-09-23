"""Local hardware probing for ``aitbc energy suggest``.

Read-only inspection of the shop node: ``nvidia-smi`` for GPUs (model,
memory, configured power limit = real TBP, UUID) and ``lscpu`` for the CPU
model. Every probe degrades to an empty result instead of raising so the
suggestion can fall back to manual flags.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from .http_client import get_logger

logger = get_logger(__name__)

_NVIDIA_SMI_FIELDS = "index,name,memory.total,power.limit,uuid"


@dataclass
class GpuInfo:
    index: int
    name: str
    memory_gb: int
    power_limit_w: int | None
    uuid: str


def _parse_int(value: str) -> int | None:
    try:
        return int(float(value.strip()))
    except (ValueError, TypeError):
        return None


def probe_gpus(timeout: int = 10) -> list[GpuInfo]:
    """Return one GpuInfo per local GPU via nvidia-smi; [] when unavailable."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={_NVIDIA_SMI_FIELDS}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("nvidia-smi probe unavailable: %s", exc)
        return []
    if result.returncode != 0:
        logger.warning("nvidia-smi failed: %s", result.stderr.strip())
        return []

    gpus: list[GpuInfo] = []
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        index = _parse_int(parts[0])
        memory_mb = _parse_int(parts[2])
        if index is None:
            continue
        gpus.append(
            GpuInfo(
                index=index,
                name=parts[1],
                memory_gb=(memory_mb // 1024) if memory_mb else 0,
                power_limit_w=_parse_int(parts[3]),
                uuid=parts[4],
            )
        )
    return gpus


def probe_cpu_model(timeout: int = 10) -> str | None:
    """CPU model string from lscpu ("Model name:"), or None when unavailable."""
    try:
        result = subprocess.run(
            ["lscpu"], capture_output=True, text=True, timeout=timeout
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("lscpu probe unavailable: %s", exc)
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.lower().startswith("model name:"):
            return line.split(":", 1)[1].strip()
    return None


def probe_ram_gb() -> int | None:
    """Installed RAM in GiB from /proc/meminfo; informational only."""
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    kb = int(re.sub(r"\D", "", line.split(":", 1)[1]))
                    return kb // (1024 * 1024)
    except (OSError, ValueError) as exc:
        logger.warning("meminfo probe unavailable: %s", exc)
    return None
