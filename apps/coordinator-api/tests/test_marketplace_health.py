"""Integration tests for marketplace health endpoints (skipped unless URLs provided).

Set env vars to run:
  MARKETPLACE_HEALTH_URL=http://127.0.0.1:18000/v1/health
  MARKETPLACE_HEALTH_URL_ALT=http://127.0.0.1:18001/v1/health
"""

import json
import os
import urllib.request

import pytest


def _check_health(url: str) -> None:
    with urllib.request.urlopen(url, timeout=5) as resp:  # nosec: B310 external URL controlled via env
        assert resp.status == 200
        data = resp.read().decode("utf-8")
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        pytest.fail(f"Health response not JSON: {data}")
    assert payload.get("status", "").lower() in {"ok", "healthy", "pass"}


@pytest.mark.skipif(
    not os.getenv("MARKETPLACE_HEALTH_URL"),
    reason="MARKETPLACE_HEALTH_URL not set; integration test skipped",
)
def test_marketplace_health_primary():
    _check_health(os.environ["MARKETPLACE_HEALTH_URL"])


@pytest.mark.skipif(
    not os.getenv("MARKETPLACE_HEALTH_URL_ALT"),
    reason="MARKETPLACE_HEALTH_URL_ALT not set; integration test skipped",
)
def test_marketplace_health_secondary():
    _check_health(os.environ["MARKETPLACE_HEALTH_URL_ALT"])
