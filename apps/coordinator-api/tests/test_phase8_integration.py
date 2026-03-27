"""Phase 8 integration tests (skipped unless URLs are provided).

Env vars (set any that you want to exercise):

For optional endpoints:
  EXPLORER_API_URL   # e.g., http://127.0.0.1:8000/v1/explorer/blocks/head
  MARKET_STATS_URL   # e.g., http://127.0.0.1:8000/v1/marketplace/stats
  ECON_STATS_URL     # e.g., http://127.0.0.1:8000/v1/economics/summary

For task-based health checks:
  MARKETPLACE_HEALTH_URL      # e.g., http://127.0.0.1:18000/v1/health  (multi-region primary)
  MARKETPLACE_HEALTH_URL_ALT  # e.g., http://127.0.0.1:18001/v1/health  (multi-region secondary)
  BLOCKCHAIN_RPC_URL          # e.g., http://127.0.0.1:9080/rpc/head     (blockchain integration)
  COORDINATOR_HEALTH_URL      # e.g., http://127.0.0.1:8000/v1/health    (agent economics / API health)
"""

import json
import os
import urllib.request

import pytest


def _check_json(url: str) -> None:
    """Check that URL returns valid JSON"""
    with urllib.request.urlopen(url, timeout=5) as resp:  # nosec: B310 external URL controlled via env
        assert resp.status == 200
        data = resp.read().decode("utf-8")
    try:
        json.loads(data)
    except json.JSONDecodeError:
        pytest.fail(f"Response not JSON from {url}: {data}")


def _check_health(url: str, expect_status_field: bool = True) -> None:
    """Check that health endpoint returns healthy status"""
    with urllib.request.urlopen(url, timeout=5) as resp:  # nosec: B310 external URL controlled via env
        assert resp.status == 200
        data = resp.read().decode("utf-8")
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        pytest.fail(f"Health response not JSON: {data}")
    
    if expect_status_field:
        assert payload.get("status", "").lower() in {"ok", "healthy", "pass"}


# Optional endpoint tests
@pytest.mark.skipif(not os.getenv("EXPLORER_API_URL"), reason="EXPLORER_API_URL not set; explorer check skipped")
def test_explorer_api_head():
    """Test explorer API head endpoint"""
    _check_json(os.environ["EXPLORER_API_URL"])


@pytest.mark.skipif(not os.getenv("MARKET_STATS_URL"), reason="MARKET_STATS_URL not set; market stats check skipped")
def test_market_stats():
    """Test market statistics endpoint"""
    _check_json(os.environ["MARKET_STATS_URL"])


@pytest.mark.skipif(not os.getenv("ECON_STATS_URL"), reason="ECON_STATS_URL not set; economics stats check skipped")
def test_economics_stats():
    """Test economics statistics endpoint"""
    _check_json(os.environ["ECON_STATS_URL"])


# Task-based health check tests
@pytest.mark.skipif(not os.getenv("MARKETPLACE_HEALTH_URL"), reason="MARKETPLACE_HEALTH_URL not set; marketplace health check skipped")
def test_marketplace_health_primary():
    """Test primary marketplace health endpoint"""
    _check_health(os.environ["MARKETPLACE_HEALTH_URL"])


@pytest.mark.skipif(not os.getenv("MARKETPLACE_HEALTH_URL_ALT"), reason="MARKETPLACE_HEALTH_URL_ALT not set; alt marketplace health check skipped")
def test_marketplace_health_secondary():
    """Test secondary marketplace health endpoint"""
    _check_health(os.environ["MARKETPLACE_HEALTH_URL_ALT"])


@pytest.mark.skipif(not os.getenv("BLOCKCHAIN_RPC_URL"), reason="BLOCKCHAIN_RPC_URL not set; blockchain RPC check skipped")
def test_blockchain_rpc_head():
    """Test blockchain RPC head endpoint"""
    _check_json(os.environ["BLOCKCHAIN_RPC_URL"])


@pytest.mark.skipif(not os.getenv("COORDINATOR_HEALTH_URL"), reason="COORDINATOR_HEALTH_URL not set; coordinator health check skipped")
def test_coordinator_health():
    """Test coordinator API health endpoint"""
    _check_health(os.environ["COORDINATOR_HEALTH_URL"])
