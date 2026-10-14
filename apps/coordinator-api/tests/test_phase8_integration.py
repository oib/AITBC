"""Phase 8 integration tests (skipped unless URLs are provided).

Env vars (set any that you want to exercise):

import sys
For optional endpoints:
  EXPLORER_API_URL   # e.g., http://127.0.0.1:8000/v1/explorer/blocks/head
  MARKET_STATS_URL   # e.g., http://127.0.0.1:8000/v1/market/stats
  ECON_STATS_URL     # e.g., http://127.0.0.1:8000/v1/economics/summary

For task-based health checks:
  MARKET_HEALTH_URL      # e.g., http://127.0.0.1:8203/v1/health  (multi-region primary)
  MARKET_HEALTH_URL_ALT  # e.g., http://127.0.0.1:8203/v1/health  (multi-region secondary)
  BLOCKCHAIN_RPC_URL          # e.g., http://127.0.0.1:9080/rpc/head     (blockchain integration)
  COORDINATOR_HEALTH_URL      # e.g., http://127.0.0.1:8000/v1/health    (agent economics / API health)
"""

import json
import os
import urllib.request

import pytest


def _env_url_or_skip(var: str) -> str:
    """Return the env-gated URL, or skip when it cannot serve the test.

    Skips when the variable is unset and when nothing answers a quick probe —
    the tests' conftest provides loopback defaults, so "set" alone does not
    mean a service is up. An HTTP error still counts as reachable: the test
    itself asserts on the response.
    """
    url = os.getenv(var)
    if not url:
        pytest.skip(f"{var} not set; check skipped")
    try:
        urllib.request.urlopen(url, timeout=2).close()  # nosec: B310 external URL controlled via env
    except urllib.error.HTTPError:
        pass
    except (urllib.error.URLError, OSError) as exc:
        pytest.skip(f"{var} endpoint {url} is not reachable ({exc}); check skipped")
    return url


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
def test_explorer_api_head():
    """Test explorer API head endpoint"""
    _check_json(_env_url_or_skip("EXPLORER_API_URL"))


def test_market_stats():
    """Test market statistics endpoint"""
    _check_json(_env_url_or_skip("MARKET_STATS_URL"))


def test_economics_stats():
    """Test economics statistics endpoint"""
    _check_json(_env_url_or_skip("ECON_STATS_URL"))


# Task-based health check tests
def test_market_health_primary():
    """Test primary market health endpoint"""
    _check_health(_env_url_or_skip("MARKET_HEALTH_URL"))


def test_market_health_secondary():
    """Test secondary market health endpoint"""
    _check_health(_env_url_or_skip("MARKET_HEALTH_URL_ALT"))


def test_blockchain_rpc_head():
    """Test blockchain RPC head endpoint"""
    url = _env_url_or_skip("BLOCKCHAIN_RPC_URL").rstrip("/")
    if not url.endswith("/rpc/head"):
        url = f"{url}/rpc/head"
    _check_json(url)


def test_coordinator_health():
    """Test coordinator API health endpoint"""
    _check_health(_env_url_or_skip("COORDINATOR_HEALTH_URL"))
