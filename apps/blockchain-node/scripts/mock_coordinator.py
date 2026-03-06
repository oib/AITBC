#!/usr/bin/env python3
"""Mock coordinator API for devnet testing."""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections import deque
from typing import Deque, Dict, List

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from aitbc_chain.metrics import metrics_registry

app = FastAPI(title="Mock Coordinator API", version="0.1.0")

SIMULATED_MINERS: List[str] = ["miner-alpha", "miner-beta", "miner-gamma"]
SIMULATED_CLIENTS: List[str] = ["client-labs", "client-trading", "client-research"]

MOCK_JOBS: Dict[str, Dict[str, str]] = {
    "job_1": {"status": "complete", "price": "50000", "compute_units": 2500},
    "job_2": {"status": "complete", "price": "25000", "compute_units": 1200},
}

_simulation_task: asyncio.Task | None = None
_job_rollup: Deque[str] = deque(maxlen=120)


def _simulate_miner_metrics() -> None:
    active_jobs = random.randint(1, 6)
    metrics_registry.set_gauge("miner_active_jobs", float(active_jobs))
    metrics_registry.set_gauge("miner_error_rate", float(random.randint(0, 1)))
    metrics_registry.observe("miner_job_duration_seconds", random.uniform(1.5, 8.0))
    metrics_registry.observe("miner_queue_depth", float(random.randint(0, 12)))


async def _simulation_loop() -> None:
    job_counter = 3
    while True:
        _simulate_miner_metrics()

        job_id = f"job_{job_counter}"
        client = random.choice(SIMULATED_CLIENTS)
        miner = random.choice(SIMULATED_MINERS)
        price = random.randint(15_000, 75_000)
        compute_units = random.randint(750, 5000)

        MOCK_JOBS[job_id] = {
            "status": random.choice(["complete", "pending", "failed"]),
            "price": str(price),
            "compute_units": compute_units,
            "client": client,
            "assigned_miner": miner,
        }
        _job_rollup.append(job_id)

        if len(MOCK_JOBS) > _job_rollup.maxlen:
            oldest = _job_rollup.popleft()
            MOCK_JOBS.pop(oldest, None)

        metrics_registry.increment("coordinator_jobs_submitted_total")
        metrics_registry.observe("coordinator_job_price", float(price))
        metrics_registry.observe("coordinator_job_compute_units", float(compute_units))

        if MOCK_JOBS[job_id]["status"] == "failed":
            metrics_registry.increment("coordinator_jobs_failed_total")
        else:
            metrics_registry.increment("coordinator_jobs_completed_total")

        job_counter += 1
        await asyncio.sleep(random.uniform(1.5, 3.5))


@app.on_event("startup")
async def _startup() -> None:
    global _simulation_task
    _simulate_miner_metrics()
    _simulation_task = asyncio.create_task(_simulation_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    global _simulation_task
    if _simulation_task:
        _simulation_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _simulation_task
        _simulation_task = None


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/attest/receipt")
def attest_receipt(payload: Dict[str, str]) -> Dict[str, str | bool]:
    job_id = payload.get("job_id")
    if job_id in MOCK_JOBS:
        metrics_registry.increment("miner_receipts_attested_total")
        return {
            "exists": True,
            "paid": True,
            "not_double_spent": True,
            "quote": MOCK_JOBS[job_id],
        }
    metrics_registry.increment("miner_receipts_unknown_total")
    return {
        "exists": False,
        "paid": False,
        "not_double_spent": False,
        "quote": {},
    }


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    metrics_registry.observe("miner_metrics_scrape_duration_seconds", random.uniform(0.001, 0.01))
    return metrics_registry.render_prometheus()
