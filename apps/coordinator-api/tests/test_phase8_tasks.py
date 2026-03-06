"""Integration checks mapped to Phase 8 tasks (skipped unless URLs provided).

Environment variables to enable:
  MARKETPLACE_HEALTH_URL      # e.g., http://127.0.0.1:18000/v1/health  (multi-region primary)
  MARKETPLACE_HEALTH_URL_ALT  # e.g., http://127.0.0.1:18001/v1/health  (multi-region secondary)
  BLOCKCHAIN_RPC_URL          # e.g., http://127.0.0.1:9080/rpc/head     (blockchain integration)
  COORDINATOR_HEALTH_URL      # e.g., http://127.0.0.1:8000/v1/health    (agent economics / API health)
"""

import json
import os
import urllib.request

import pytest


def _check_health(url: str, expect_status_field: bool = True) -> None:
    with urllib.request.urlopen(url, timeout=5) as resp:  # nosec: B310 external URL controlled via env
        assert resp.status == 200
        data = resp.read().decode("utf-8")
    if not expect_status_field:
        return
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        pytest.fail(f"Response not JSON: {data}")
    assert payload.get("status", "").lower() in {"ok", "healthy", "pass"}


@pytest.mark.skipif(
    not os.getenv("MARKETPLACE_HEALTH_URL"),
    reason="MARKETPLACE_HEALTH_URL not set; multi-region primary health skipped",
)
def test_multi_region_primary_health():
    _check_health(os.environ["MARKETPLACE_HEALTH_URL"])


@pytest.mark.skipif(
    not os.getenv("MARKETPLACE_HEALTH_URL_ALT"),
    reason="MARKETPLACE_HEALTH_URL_ALT not set; multi-region secondary health skipped",
)
def test_multi_region_secondary_health():
    _check_health(os.environ["MARKETPLACE_HEALTH_URL_ALT"])


@pytest.mark.skipif(
    not os.getenv("BLOCKCHAIN_RPC_URL"),
    reason="BLOCKCHAIN_RPC_URL not set; blockchain RPC check skipped",
)
def test_blockchain_rpc_head():
    _check_health(os.environ["BLOCKCHAIN_RPC_URL"], expect_status_field=False)


@pytest.mark.skipif(
    not os.getenv("COORDINATOR_HEALTH_URL"),
    reason="COORDINATOR_HEALTH_URL not set; coordinator health skipped",
)
def test_agent_api_health():
    _check_health(os.environ["COORDINATOR_HEALTH_URL"])
