"""Node-process metrics registry snapshot, readable through the RPC ``/metrics``.

The node (consensus/sync) and the RPC server are separate processes, each with
its own in-memory ``metrics_registry``. Consensus counters such as
``pbft_intake_drop_*`` or ``pbft_view_change_*`` are incremented in the node
process, so the RPC ``/metrics`` route never showed them (drill2 #2205: counters
"unreadable" for exactly this reason). The node writes its rendered registry to
a small file every few seconds; the RPC route appends it to its own output. No
new port or listener; the reading is at most one interval stale.

A snapshot written by the same process is skipped on read (single-process
deployments already render the registry directly — appending it again would
duplicate every series).

Both processes import ``aitbc_chain.metrics`` and register the same names,
so a naive append exposes shared families twice — duplicate samples AND
duplicate ``# TYPE`` lines, which strict parsers reject and Prometheus
counts as dropped duplicates (#2488). ``with_node_snapshot`` therefore
merges by *series*, not by name (#2504): every snapshot sample is tagged
``process="node"`` so the node process's value survives next to the RPC
process's own same-named series, and the snapshot's ``# TYPE``/``# HELP``
lines for families the RPC render already declares are dropped — one
declaration per family, no duplicate samples.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path

from aitbc.constants import DATA_DIR

from .config import settings
from .logger import get_logger
from .metrics import metrics_registry

logger = get_logger(__name__)

# A snapshot older than this many intervals is considered dead and not served.
_STALE_INTERVALS = 6.0
_PID_PREFIX = "# aitbc-node-metrics-snapshot pid="


def snapshot_path() -> Path:
    return Path(DATA_DIR) / "node_metrics.prom"


def write_snapshot(path: Path | None = None) -> None:
    """Atomically write this process's rendered registry."""
    target = path or snapshot_path()
    body = f"{_PID_PREFIX}{os.getpid()} ts={time.time():.0f}\n{metrics_registry.render_prometheus()}"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, target)


def read_snapshot(path: Path | None = None, max_age: float | None = None) -> str:
    """The node process's snapshot text, or ``""`` (missing, stale, own pid)."""
    target = path or snapshot_path()
    interval = float(getattr(settings, "node_metrics_snapshot_interval_seconds", 5.0))
    limit = max_age if max_age is not None else interval * _STALE_INTERVALS
    try:
        if time.time() - target.stat().st_mtime > limit:
            return ""
        text = target.read_text(encoding="utf-8")
    except OSError:
        return ""
    first, _, rest = text.partition("\n")
    if not first.startswith(_PID_PREFIX):
        return ""
    pid = first[len(_PID_PREFIX) :].split(" ", 1)[0]
    if pid == str(os.getpid()):
        return ""
    return rest


def _exposition_names(rendered: bytes) -> set[str]:
    """Metric names in an exposition: TYPE/HELP subjects plus sample names.

    Sample names matter for summaries — ``foo`` renders ``foo_count`` /
    ``foo_sum`` samples under one ``# TYPE foo summary`` line, and the
    snapshot's copies of those samples must dedup against the RPC render's
    sample names, not just its TYPE subjects.
    """
    names: set[str] = set()
    for raw in rendered.decode("utf-8", "replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            parts = line.split()
            if len(parts) >= 3 and parts[1] in ("TYPE", "HELP"):
                names.add(parts[2])
            continue
        names.add(line.split("{", 1)[0].split()[0])
    return names


def _tag_node_sample(line: str) -> str:
    """Add ``process="node"`` to a sample's label set.

    The snapshot is the *node* process's registry; tagging every sample
    keeps it a distinct series from the RPC process's same-named one
    instead of colliding with it (#2504). A sample already carrying a
    ``process`` label is left alone.
    """
    stripped = line.strip()
    if re.search(r'[{,]process="', stripped):
        return line
    head, sep, tail = stripped.partition("{")
    if sep:
        return f'{head}{{process="node",{tail}'
    name, _, rest = stripped.partition(" ")
    return f'{name}{{process="node"}} {rest}'


def _merge_node_snapshot(node_metrics: str, known: set[str]) -> str:
    """Snapshot text safe to append to the RPC render.

    ``# TYPE``/``# HELP`` lines for families ``known`` already declares are
    dropped (one declaration per family); every sample is tagged
    ``process="node"`` so shared names keep BOTH processes' values as
    distinct series — dedup by series, not by name (#2504). Node-only
    families pass through with their declarations intact.
    """
    kept: list[str] = []
    for line in node_metrics.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            parts = stripped.split()
            if len(parts) >= 3 and parts[1] in ("TYPE", "HELP") and parts[2] in known:
                continue
            kept.append(line)
            continue
        kept.append(_tag_node_sample(line))
    return "\n".join(kept) + ("\n" if kept else "")


def with_node_snapshot(rendered: bytes) -> bytes:
    """``rendered`` plus the node-process snapshot when enabled and fresh."""
    if not getattr(settings, "node_metrics_snapshot_enabled", True):
        return rendered
    node_metrics = read_snapshot()
    if not node_metrics.strip():
        return rendered
    filtered = _merge_node_snapshot(node_metrics, _exposition_names(rendered))
    if not filtered.strip():
        return rendered
    return rendered + b"\n# node-process registry (snapshot)\n" + filtered.encode()


async def snapshot_loop() -> None:
    """Node-process task: refresh the snapshot until cancelled. Never raises."""
    interval = max(1.0, float(getattr(settings, "node_metrics_snapshot_interval_seconds", 5.0)))
    while True:
        try:
            await asyncio.to_thread(write_snapshot)
        except OSError as exc:
            logger.warning("node metrics snapshot write failed: %s", exc)
        await asyncio.sleep(interval)
