"""Tests for the additional typed AITBC RPC/HTTP tools in the MCP server."""

from __future__ import annotations

import json
import sys
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server
import aitbc_mcp_rpc_tools as rpc_tools

# Deterministic role map: unmapped roles are refused now (MCP-ROUTING-1), so
# tests must not depend on the machine's real mcp-hosts.yaml. Identical map
# in test_aitbc_mcp_cli_tools.py — last-writer-wins stays order-safe.
mcp_server._HOSTS_CONFIG = {
    "roles": {"hub": "hub", "customer": "node0", "shop": "node2"},
    "default_host": "hub",
    "ssh_user": "",
}


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


def test_messaging_tools_sanitise_invisible_chars():
    """MSG-4b: forum bodies must reach the agent with format chars made
    visible — including characters serialized as JSON \\uXXXX escapes."""
    body = f"hi{chr(0x200B)}there{chr(0xE0001)}end"  # ZWSP + a tag char
    payload = {"messages": [{"body": body, "topic": "msg-fix"}], "count": 1}
    rpc_tools._http_read_tool = lambda *a, **kw: json.dumps(payload, ensure_ascii=True)
    result = json.loads(rpc_tools.get_topic_messages(topic_id="msg-fix", role="hub"))
    out = result["messages"][0]["body"]
    assert "[U+200B]" in out
    assert "[U+E0001]" in out
    assert chr(0x200B) not in out
    assert chr(0xE0001) not in out


if __name__ == "__main__":
    test_get_eth_bridge_status_redacted_omits_rpc_url()
    test_get_eth_bridge_status_redacted_falls_back_to_stdout()
    test_get_eth_bridge_status_redacted_reports_failure_without_leak()


def _capture_write_body():
    """Capture the body a write tool hands to _run_http."""
    captured: dict[str, object] = {}

    def fake(target, service, path, method, params, body, timeout, auth="none"):
        captured.update({"target": target, "service": service, "path": path, "body": body})
        return _run_http_with_status({"ok": True})

    rpc_tools._run_http = fake
    return captured


def test_bridge_lock_forwards_replay_fields():
    captured = _capture_write_body()
    result = json.loads(
        rpc_tools.bridge_lock(
            target_chain="ait-side",
            sender="0x" + "aa" * 20,
            recipient="0x" + "bb" * 20,
            amount=3600000,
            signature="0x" + "ee" * 65,
            issued_at=1760000000,
            nonce="deadbeef",
            dry_run=False,
            confirm=True,
            host="node.test",
        )
    )
    body = captured["body"]
    assert captured["path"] == "bridge/lock"
    assert body["issued_at"] == 1760000000
    assert body["nonce"] == "deadbeef"
    assert body["signature"] == "0x" + "ee" * 65
    assert "ok" in str(result)


def test_bridge_lock_omits_replay_fields_when_unset():
    captured = _capture_write_body()
    rpc_tools.bridge_lock(
        target_chain="ait-side",
        sender="0x" + "aa" * 20,
        recipient="0x" + "bb" * 20,
        amount=3600000,
        signature="0x" + "ee" * 65,
        dry_run=False,
        confirm=True,
        host="node.test",
    )
    body = captured["body"]
    assert "issued_at" not in body
    assert "nonce" not in body


def test_cross_chain_swap_sends_signature_and_replay_fields():
    captured = _capture_write_body()
    rpc_tools.create_cross_chain_swap(
        from_chain="ait-hub",
        to_chain="ait-side",
        from_token="AIT",
        to_token="AIT",
        amount=100,
        user_address="0x" + "aa" * 20,
        signature="0x" + "ee" * 65,
        issued_at=1760000000,
        nonce="deadbeef",
        dry_run=False,
        confirm=True,
        host="node.test",
    )
    body = captured["body"]
    assert captured["path"] == "cross-chain/swap"
    assert body["signature"] == "0x" + "ee" * 65
    assert body["issued_at"] == 1760000000
    assert body["nonce"] == "deadbeef"
    assert body["user_address"] == "0x" + "aa" * 20


def test_cross_chain_swap_omits_new_fields_when_unset():
    captured = _capture_write_body()
    rpc_tools.create_cross_chain_swap(
        from_chain="ait-hub",
        to_chain="ait-side",
        from_token="AIT",
        to_token="AIT",
        amount=100,
        user_address="0x" + "aa" * 20,
        dry_run=False,
        confirm=True,
        host="node.test",
    )
    body = captured["body"]
    assert "signature" not in body
    assert "issued_at" not in body
    assert "nonce" not in body


def test_cross_chain_bridge_sends_sender_signature_and_replay_fields():
    captured = _capture_write_body()
    rpc_tools.create_cross_chain_bridge(
        source_chain="ait-hub",
        target_chain="ait-side",
        token="AIT",
        amount=100,
        sender="0x" + "aa" * 20,
        recipient_address="0x" + "bb" * 20,
        signature="0x" + "ee" * 65,
        issued_at=1760000000,
        nonce="deadbeef",
        dry_run=False,
        confirm=True,
        host="node.test",
    )
    body = captured["body"]
    assert captured["path"] == "cross-chain/bridge"
    assert body["sender"] == "0x" + "aa" * 20
    assert body["signature"] == "0x" + "ee" * 65
    assert body["issued_at"] == 1760000000
    assert body["nonce"] == "deadbeef"


def test_cross_chain_bridge_dry_run_stays_a_preview():
    calls = []
    rpc_tools._run_http = lambda *a, **kw: calls.append((a, kw))
    result = json.loads(
        rpc_tools.create_cross_chain_bridge(
            source_chain="ait-hub",
            target_chain="ait-side",
            token="AIT",
            amount=100,
            sender="0x" + "aa" * 20,
            recipient_address="0x" + "bb" * 20,
            signature="0x" + "ee" * 65,
            issued_at=1760000000,
            nonce="deadbeef",
            dry_run=True,
            confirm=True,
            host="node.test",
        )
    )
    assert calls == []
    assert result["dry_run"] is True
    command = result["command"]
    assert "cross-chain/bridge" in str(command)
    assert "deadbeef" in json.dumps(command)


def test_cross_chain_tools_require_confirmation():
    rpc_tools._run_http = _fake_run_http
    result = json.loads(
        rpc_tools.create_cross_chain_swap(
            from_chain="ait-hub",
            to_chain="ait-side",
            from_token="AIT",
            to_token="AIT",
            amount=100,
            signature="0x" + "ee" * 65,
            dry_run=False,
            confirm=False,
            host="node.test",
        )
    )
    assert result["error"] == "Confirmation required"


def test_register_gpu_forwards_signed_envelope():
    """FORK-OOB-1/#382: the route takes only a signed ``tx`` envelope; the
    tool is a pure relay (the MCP server holds no wallet)."""
    captured = _capture_write_body()
    envelope = {
        "type": "GPU_REGISTER",
        "from": "0x" + "aa" * 20,
        "signature": "0x" + "ee" * 65,
        "payload": {"gpu_id": "gpu-1"},
    }
    result = json.loads(rpc_tools.register_gpu(tx=envelope, dry_run=False, confirm=True, host="node.test"))
    assert captured["path"] == "gpu/register"
    assert captured["body"] == {"tx": envelope}
    assert "ok" in str(result)


def test_allocate_gpu_forwards_signed_envelope():
    captured = _capture_write_body()
    envelope = {
        "type": "GPU_ALLOCATE",
        "from": "0x" + "aa" * 20,
        "signature": "0x" + "ee" * 65,
        "payload": {"gpu_id": "gpu-1", "allocation_id": "alloc_1"},
    }
    rpc_tools.allocate_gpu(tx=envelope, dry_run=False, confirm=True, host="node.test")
    assert captured["path"] == "gpu/allocate"
    assert captured["body"] == {"tx": envelope}
