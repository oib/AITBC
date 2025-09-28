#!/usr/bin/env python3
"""Mock coordinator API for devnet testing."""

from __future__ import annotations

import random
import time
from typing import Dict

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from aitbc_chain.metrics import metrics_registry

app = FastAPI(title="Mock Coordinator API", version="0.1.0")

MOCK_JOBS: Dict[str, Dict[str, str]] = {
    "job_1": {"status": "complete", "price": "50000", "compute_units": 2500},
    "job_2": {"status": "complete", "price": "25000", "compute_units": 1200},
}


def _simulate_miner_metrics() -> None:
    metrics_registry.set_gauge("miner_active_jobs", float(random.randint(0, 5)))
    metrics_registry.set_gauge("miner_error_rate", float(random.randint(0, 1)))
    metrics_registry.observe("miner_job_duration_seconds", random.uniform(1.0, 5.0))


@app.on_event("startup")
async def _startup() -> None:
    _simulate_miner_metrics()


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
