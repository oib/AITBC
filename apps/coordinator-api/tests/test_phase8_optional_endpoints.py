"""Optional integration checks for Phase 8 endpoints (skipped unless URLs are provided).

Env vars (set any that you want to exercise):
  EXPLORER_API_URL   # e.g., http://127.0.0.1:8000/v1/explorer/blocks/head
  MARKET_STATS_URL   # e.g., http://127.0.0.1:8000/v1/marketplace/stats
  ECON_STATS_URL     # e.g., http://127.0.0.1:8000/v1/economics/summary
"""

import json
import os
import urllib.request

import pytest


def _check_json(url: str) -> None:
    with urllib.request.urlopen(url, timeout=5) as resp:  # nosec: B310 external URL controlled via env
        assert resp.status == 200
        data = resp.read().decode("utf-8")
    try:
        json.loads(data)
    except json.JSONDecodeError:
        pytest.fail(f"Response not JSON from {url}: {data}")


@pytest.mark.skipif(not os.getenv("EXPLORER_API_URL"), reason="EXPLORER_API_URL not set; explorer check skipped")
def test_explorer_api_head():
    _check_json(os.environ["EXPLORER_API_URL"])


@pytest.mark.skipif(not os.getenv("MARKET_STATS_URL"), reason="MARKET_STATS_URL not set; market stats check skipped")
def test_market_stats():
    _check_json(os.environ["MARKET_STATS_URL"])


@pytest.mark.skipif(not os.getenv("ECON_STATS_URL"), reason="ECON_STATS_URL not set; economics stats check skipped")
def test_economics_stats():
    _check_json(os.environ["ECON_STATS_URL"])
