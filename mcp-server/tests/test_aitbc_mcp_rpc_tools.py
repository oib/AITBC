"""Tests for the additional typed AITBC RPC/HTTP tools in the MCP server."""

from __future__ import annotations

import json
import sys
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_rpc_tools as rpc_tools


FULL_BRIDGE_STATUS: dict[str, object] = {
    "status": "ready",
    "message": "Bridge active",
    "enabled": True,
    "network": "sepolia",
    "deposit_address": "0x5e2D7C7A4F8E9B1C3d5A2e8F4c6b8a0D2e4f6A8C",
    "wallet_address": "0x5e2D7C7A4F8E9B1C3d5A2e8F4c6b8a0D2e4f6A8C",
    "rpc_url": "https://user:secret@sepolia.infura.io/v3/SECRET_KEY",
    "poll_interval": 30,
    "auto_poll": True,
    "fee_rate": 0.005,
    "min_deposit": "0.001",
    "unexpected_secret": "should-not-appear",
}


def _run_http_with_status(status: dict[str, object]) -> dict[str, object]:
    """Build a realistic _run_http return value for a successful wallet call."""
    return {
        "returncode": 0,
        "stdout": json.dumps(status),
        "stderr": "",
        "json": status,
    }


def _fake_run_http(*_args: object, **_kwargs: object) -> dict[str, object]:
    return _run_http_with_status(FULL_BRIDGE_STATUS)


def _fake_run_http_raw_stdout(*_args: object, **_kwargs: object) -> dict[str, object]:
    """Simulate a CLI that returns JSON only via stdout (no parsed json key)."""
    return {
        "returncode": 0,
        "stdout": json.dumps(FULL_BRIDGE_STATUS),
        "stderr": "",
    }


def _fake_run_http_failure(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {
        "returncode": 1,
        "stdout": "",
        "stderr": "connection refused",
    }


def test_get_eth_bridge_status_redacted_omits_rpc_url():
    rpc_tools._run_http = _fake_run_http
    result = json.loads(rpc_tools.get_eth_bridge_status_redacted(role="hub"))

    assert "rpc_url" not in result
    assert "unexpected_secret" not in result
    assert result["status"] == "ready"
    assert result["enabled"] is True
    assert result["network"] == "sepolia"
    assert result["deposit_address"] == FULL_BRIDGE_STATUS["deposit_address"]
    assert result["fee_rate"] == 0.005
    assert result["min_deposit"] == "0.001"
    assert result["poll_interval"] == 30
    assert result["auto_poll"] is True


def test_get_eth_bridge_status_redacted_falls_back_to_stdout():
    rpc_tools._run_http = _fake_run_http_raw_stdout
    result = json.loads(rpc_tools.get_eth_bridge_status_redacted(role="hub"))

    assert "rpc_url" not in result
    assert result["network"] == "sepolia"
    assert result["deposit_address"] == FULL_BRIDGE_STATUS["deposit_address"]


def test_get_eth_bridge_status_redacted_reports_failure_without_leak():
    rpc_tools._run_http = _fake_run_http_failure
    result = json.loads(rpc_tools.get_eth_bridge_status_redacted(role="hub"))

    assert "error" in result
    assert result["returncode"] == 1
    assert "stdout" not in result
    assert "stderr" not in result


if __name__ == "__main__":
    test_get_eth_bridge_status_redacted_omits_rpc_url()
    test_get_eth_bridge_status_redacted_falls_back_to_stdout()
    test_get_eth_bridge_status_redacted_reports_failure_without_leak()
