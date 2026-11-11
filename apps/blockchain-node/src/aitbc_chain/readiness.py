"""Node-engine readiness heartbeat (#1711).

``aitbc_chain.main`` (the consensus engine) has no HTTP surface — the
FastAPI ``/ready`` probe lives in the separate ``aitbc-blockchain-rpc``
process. During the v12-11 chaos drill the engine stayed ``active`` while
its gossip transport was dead (peer RPCs restarting), so it could neither
attest nor import and consensus stalled ~5 min with every unit green.

This module closes that gap with a filesystem signal both processes can
see: the engine writes a JSON heartbeat on an interval describing probe
results (gossip transport health today, more components later); the RPC
``/ready`` endpoint fails while the file is missing, stale, or reports a
non-ready component. File-based IPC is deliberate — it works across the
unit boundary with no new port or auth surface, and a dead engine simply
stops writing, which reads as not-ready.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .logger import get_logger

logger = get_logger(__name__)

Probe = Callable[[], Awaitable[dict[str, Any]]]


class NodeReadinessHeartbeat:
    """Periodic JSON heartbeat with named component probes.

    ``register_probe(name, fn)`` adds an async probe returning
    ``{"ok": bool, ...}``; the file's top-level ``status`` is ``ready``
    only while every registered probe reports ok. Probes that raise are
    recorded as failed — a probe bug must fail closed, not silently pass.
    """

    def __init__(self, path: str | Path, interval_seconds: float = 15.0) -> None:
        self._path = Path(path)
        self._interval = max(1.0, float(interval_seconds))
        self._probes: dict[str, Probe] = {}
        self._task: asyncio.Task[None] | None = None
        self._extra: dict[str, Any] = {}

    def register_probe(self, name: str, probe: Probe) -> None:
        self._probes[name] = probe

    def set_component(self, name: str, ok: bool, **detail: Any) -> None:
        """Static component state (e.g. "gossip_backend": "mesh")."""
        self._extra[name] = {"ok": ok, **detail}

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="node_readiness_heartbeat")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        # A stopped engine must not keep reporting ready — remove the file
        # so /ready fails closed rather than on stale data.
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass

    async def _loop(self) -> None:
        while True:
            try:
                await self._write_once()
            except Exception as exc:  # noqa: BLE001 - heartbeat must never die
                logger.warning("readiness heartbeat write failed: %s", exc)
            await asyncio.sleep(self._interval)

    async def _write_once(self) -> None:
        components: dict[str, Any] = dict(self._extra)
        for name, probe in self._probes.items():
            try:
                components[name] = await asyncio.wait_for(probe(), timeout=5.0)
            except Exception as exc:  # noqa: BLE001 - probe failure = not ok
                components[name] = {"ok": False, "detail": f"probe raised: {exc}"}
        ready = all(bool(c.get("ok")) for c in components.values()) if components else True
        payload = {
            "ts": time.time(),
            "pid": os.getpid(),
            "status": "ready" if ready else "degraded",
            "components": components,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), prefix=self._path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(payload, fh)
                fh.write("\n")
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def read_heartbeat(path: str | Path) -> dict[str, Any] | None:
    """Parse a heartbeat file; None when missing/unreadable/malformed."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
