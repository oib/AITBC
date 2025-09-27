from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Optional

from ..config import settings
from ..logging import get_logger
from ..coordinator import CoordinatorClient
from ..util.probe import collect_capabilities, collect_runtime_metrics
from ..util.backoff import compute_backoff
from ..util.fs import ensure_workspace, write_json
from ..runners import get_runner

logger = get_logger(__name__)


class MinerControlLoop:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()
        self._coordinator = CoordinatorClient()
        self._capabilities_snapshot = collect_capabilities(settings.max_concurrent_cpu, settings.max_concurrent_gpu)
        self._current_backoff = settings.poll_interval_seconds

    async def start(self) -> None:
        logger.info("Starting miner control loop", extra={"node_id": settings.node_id})
        await self._register()
        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
        self._tasks.append(asyncio.create_task(self._poll_loop()))

    async def stop(self) -> None:
        logger.info("Stopping miner control loop")
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._coordinator.aclose()

    async def _register(self) -> None:
        payload = {
            "capabilities": self._capabilities_snapshot.capabilities,
            "concurrency": self._capabilities_snapshot.concurrency,
            "region": settings.region,
        }
        try:
            resp = await self._coordinator.register(payload)
            logger.info("Registered miner", extra={"resp": resp})
        except Exception as exc:
            logger.exception("Failed to register miner", exc_info=exc)
            raise

    async def _heartbeat_loop(self) -> None:
        interval = settings.heartbeat_interval_seconds
        while not self._stop_event.is_set():
            payload = {
                "inflight": 0,
                "status": "ONLINE",
                "metadata": collect_runtime_metrics(),
            }
            try:
                await self._coordinator.heartbeat(payload)
                logger.debug("heartbeat sent")
            except Exception as exc:
                logger.warning("heartbeat failed", exc_info=exc)
            await asyncio.sleep(interval)

    async def _poll_loop(self) -> None:
        interval = settings.poll_interval_seconds
        while not self._stop_event.is_set():
            payload = {"max_wait_seconds": interval}
            try:
                job = await self._coordinator.poll(payload)
                if job:
                    logger.info("received job", extra={"job_id": job.get("job_id")})
                    self._current_backoff = settings.poll_interval_seconds
                    await self._handle_job(job)
                else:
                    interval = min(compute_backoff(interval, 2.0, settings.heartbeat_jitter_pct, settings.max_backoff_seconds), settings.max_backoff_seconds)
                    logger.debug("no job; next poll interval=%s", interval)
            except Exception as exc:
                logger.warning("poll failed", exc_info=exc)
                interval = min(compute_backoff(interval, 2.0, settings.heartbeat_jitter_pct, settings.max_backoff_seconds), settings.max_backoff_seconds)
            await asyncio.sleep(interval)

    async def _handle_job(self, job: dict) -> None:
        job_id = job.get("job_id", "unknown")
        workspace = ensure_workspace(settings.workspace_root, job_id)
        runner_kind = job.get("runner", {}).get("kind", "noop")
        runner = get_runner(runner_kind)

        try:
            result = await runner.run(job, workspace)
        except Exception as exc:
            logger.exception("runner crashed", extra={"job_id": job_id, "runner": runner_kind})
            await self._coordinator.submit_failure(
                job_id,
                {
                    "error_code": "RUNTIME_ERROR",
                    "error_message": str(exc),
                    "metrics": {},
                },
            )
            return

        if result.ok:
            write_json(workspace / "result.json", result.output)
            try:
                await self._coordinator.submit_result(
                    job_id,
                    {
                        "result": result.output,
                        "metrics": {"workspace": str(workspace)},
                    },
                )
            except Exception as exc:
                logger.warning("failed to submit result", extra={"job_id": job_id}, exc_info=exc)
        else:
            await self._coordinator.submit_failure(
                job_id,
                {
                    "error_code": result.output.get("error_code", "FAILED"),
                    "error_message": result.output.get("error_message", "Job failed"),
                    "metrics": result.output.get("metrics", {}),
                },
            )
