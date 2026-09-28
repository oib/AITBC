"""Per-IP rate limits on the coin-request routes (V23 faucet review).

A faucet drain does not need many requests to be worthwhile, so `/register` and
`/execute` carry tighter buckets (30/min and 20/min) on top of the service-wide
middleware. These tests pin the caller via `X-Real-IP` — the same header the
shared limiter keys on behind nginx — so each test owns a deterministic bucket
instead of racing the TestClient default.
"""

from __future__ import annotations

import pytest

from aitbc.rate_limiting import reset_rate_limit

from .conftest import API_KEY, PAYOUT

WALLET = "0x81B8A8D5143fE722304E49b2C09d51BbF4588265"
IP = "192.0.2.7"
OTHER_IP = "192.0.2.8"


@pytest.fixture
def client(bare_client, monkeypatch):
    """A fresh bucket for the pinned test IP, before and after.

    Rate limiting has to be on for these tests — several older test modules
    disable it globally at import time, so this suite's env is unreliable.
    """
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "true")
    for ip in (IP, OTHER_IP):
        reset_rate_limit(ip)
    yield bare_client
    for ip in (IP, OTHER_IP):
        reset_rate_limit(ip)


def _register(client, ip: str = IP) -> object:
    body = {
        "request_id": "req-rate",
        "sender": "agent-rate",
        "amount": PAYOUT,
        "wallet_address": WALLET,
    }
    return client.post(
        "/api/v1/agent/coin-requests/register",
        json=body,
        headers={"x-api-key": API_KEY, "x-real-ip": ip},
    )


def _execute(client, ip: str = IP) -> object:
    body = {"request_id": "req-never-registered"}
    return client.post(
        "/api/v1/agent/coin-requests/execute",
        json=body,
        headers={"x-api-key": API_KEY, "x-real-ip": ip},
    )


def test_register_rate_limit_is_per_ip(client) -> None:
    # Same idempotent request replayed — the limiter counts every call, so the
    # bucket still drains even though the handler short-circuits.
    for _ in range(30):
        assert _register(client).status_code == 200
    limited = _register(client)
    assert limited.status_code == 429

    # Another source IP is a different bucket — one noisy caller cannot lock
    # the faucet out for everyone else.
    assert _register(client, ip=OTHER_IP).status_code == 200


def test_execute_rate_limit(client) -> None:
    # Unknown request ids still consume the bucket — limiting has to run ahead
    # of the handler, not only on successful work.
    for _ in range(20):
        assert _execute(client).status_code == 404
    assert _execute(client).status_code == 429
