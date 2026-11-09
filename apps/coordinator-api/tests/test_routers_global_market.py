"""Contract tests for /v1/global-market/* (#1289 round 9 batch 7).

global_market + global_market_integration routers are imported in
market/routers/__init__.py but NEVER include_router'd in main.py — the
entire surface is latent/unreachable (same class as #1336 zk_applications,
downgraded to latent pending an AD mount-or-delete decision). These tests
pin the unmounted contract: every path 404s. If either router is ever
mounted, this file must be replaced with real endpoint coverage.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

GM = "/v1/global-market"
GMI = "/v1/global-market-integration"

PATHS = [
    ("GET", f"{GM}/health"),
    ("GET", f"{GM}/config"),
    ("GET", f"{GM}/regions"),
    ("GET", f"{GM}/offers"),
    ("POST", f"{GM}/offers"),
    ("GET", f"{GM}/offers/abc"),
    ("GET", f"{GM}/transactions"),
    ("POST", f"{GM}/transactions"),
    ("GET", f"{GM}/analytics"),
    ("GET", f"{GM}/regions/at1/health"),
    ("POST", f"{GM}/regions/at1/health"),
    ("GET", f"{GMI}/status"),
    ("GET", f"{GMI}/config"),
    ("GET", f"{GMI}/health"),
    ("GET", f"{GMI}/offers/cross-chain"),
    ("POST", f"{GMI}/offers/create-cross-chain"),
    ("GET", f"{GMI}/transactions/cross-chain"),
    ("POST", f"{GMI}/transactions/execute-cross-chain"),
    ("GET", f"{GMI}/analytics/cross-chain"),
    ("GET", f"{GMI}/analytics/market-integration"),
    ("POST", f"{GMI}/config/update"),
    ("POST", f"{GMI}/diagnostics/run"),
]


@pytest.mark.parametrize("method,path", PATHS)
def test_global_market_routers_unmounted(client: TestClient, method: str, path: str) -> None:
    resp = client.request(method, path, json={} if method == "POST" else None)
    assert resp.status_code == 404, f"{method} {path} -> {resp.status_code} (router mounted? update coverage)"
