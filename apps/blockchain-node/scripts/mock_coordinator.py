#!/usr/bin/env python3
"""Mock coordinator API for devnet testing."""

from __future__ import annotations

from typing import Dict

from fastapi import FastAPI

app = FastAPI(title="Mock Coordinator API", version="0.1.0")

MOCK_JOBS: Dict[str, Dict[str, str]] = {
    "job_1": {"status": "complete", "price": "50000", "compute_units": 2500},
    "job_2": {"status": "complete", "price": "25000", "compute_units": 1200},
}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/attest/receipt")
def attest_receipt(payload: Dict[str, str]) -> Dict[str, str | bool]:
    job_id = payload.get("job_id")
    if job_id in MOCK_JOBS:
        return {
            "exists": True,
            "paid": True,
            "not_double_spent": True,
            "quote": MOCK_JOBS[job_id],
        }
    return {
        "exists": False,
        "paid": False,
        "not_double_spent": False,
        "quote": {},
    }
