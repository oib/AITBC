"""Tests for the additional typed AITBC CLI tools in the MCP server."""

from __future__ import annotations

import json
import sys
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server

# Deterministic role map: unmapped roles are refused now (MCP-ROUTING-1), so
# tests must not depend on the machine's real mcp-hosts.yaml. Identical map
# in test_aitbc_mcp_rpc_tools.py — last-writer-wins stays order-safe.
mcp_server._HOSTS_CONFIG = {
    "roles": {"hub": "hub", "customer": "node0", "shop": "node2"},
    "default_host": "hub",
    "ssh_user": "",
}

# Replace remote SSH execution with a recorder so tests run offline.
CAPTURED: list[dict[str, object]] = []


def _fake_run_remote(host: str, command: str, timeout: int = 60) -> dict[str, object]:
    CAPTURED.append({"host": host, "command": command, "timeout": timeout})
    return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}


mcp_server._run_remote = _fake_run_remote

import aitbc_mcp_cli_tools  # noqa: E402


def _last_command() -> str:
    assert CAPTURED
    return str(CAPTURED[-1]["command"])


def _clear() -> None:
    CAPTURED.clear()


def test_buy_ait_exchange():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.buy_ait_exchange(
            amount="1.0",
            max_price="0.00076",
            wallet="genesis",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "aitbc" in cmd
    assert "exchange-island" in cmd
    assert "buy" in cmd
    assert "--ait-amount=1.0" in cmd
    assert "--quote-currency=ETH" in cmd
    assert "--max-price=0.00076" in cmd
    assert "--wallet=genesis" in cmd


def test_sell_ait_exchange():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.sell_ait_exchange(
            amount="2.0",
            min_price="0.00075",
            wallet="shop-wallet",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "exchange-island sell" in cmd
    assert "--ait-amount=2.0" in cmd
    assert "--quote-currency=ETH" in cmd
    assert "--min-price=0.00075" in cmd
    assert "--wallet=shop-wallet" in cmd


def test_get_exchange_orderbook():
    _clear()
    result = json.loads(aitbc_mcp_cli_tools.get_exchange_orderbook(pair="AIT/ETH", limit=5, role="hub"))
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "exchange-island orderbook" in cmd
    assert "AIT/ETH" in cmd
    assert "--limit=5" in cmd


def test_create_island():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.create_island(
            island_id="ait-test-island",
            island_name="test",
            chain_id="ait-test",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "node island create" in cmd
    assert "--island-id=ait-test-island" in cmd
    assert "--island-name=test" in cmd
    assert "--chain-id=ait-test" in cmd


def test_join_island():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.join_island(
            island_id="ait-test-island",
            island_name="test",
            chain_id="ait-test",
            hub="hub.example.net",
            is_hub=False,
            rpc_url="https://hub.example.net/rpc",
            dry_run=False,
            confirm=True,
            role="shop",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "node island join" in cmd
    assert "--island-id=ait-test-island" in cmd
    assert "--island-name=test" in cmd
    assert "--chain-id=ait-test" in cmd
    assert "--hub=hub.example.net" in cmd
    assert "--rpc-url=https://hub.example.net/rpc" in cmd
    assert "--is-hub" not in cmd


def test_join_island_as_hub():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.join_island(
            island_id="ait-test-island",
            island_name="test",
            chain_id="ait-test",
            is_hub=True,
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "node island join" in cmd
    assert "--is-hub" in cmd


def test_create_market_offer():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.create_market_offer(
            service_type="ipfs",
            model="ipfs-host",
            price="1",
            unit="per_day",
            description="Host files for 1 AIT per day",
            wallet="shop-wallet",
            dry_run=False,
            confirm=True,
            role="shop",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert cmd.startswith("AITBC_WALLET_DIR=/var/lib/aitbc/wallets")
    assert "market" in cmd
    assert "--wallet=shop-wallet" in cmd
    assert "offer" in cmd
    assert "ipfs" in cmd
    assert "ipfs-host" in cmd
    assert "--unit=per_day" in cmd
    assert "--description='Host files for 1 AIT per day'" in cmd


def test_upload_ipfs():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.upload_ipfs(
            file="/tmp/test.txt",
            name="test upload",
            pin=True,
            dry_run=False,
            confirm=True,
            role="shop",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "ipfs upload" in cmd
    assert "--file=/tmp/test.txt" in cmd
    assert "--name='test upload'" in cmd
    assert "--pin" in cmd


def test_download_ipfs():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.download_ipfs(
            cid="QmTest",
            output="/tmp/out",
            wait=True,
            role="hub",
        )
    )
    # The downloader writes a file on the remote host — it is gated like the
    # generated aitbc_ipfs_download twin, so a default call only dry-runs.
    assert result.get("dry_run") is True
    assert "command" in result
    assert not CAPTURED

    result = json.loads(
        aitbc_mcp_cli_tools.download_ipfs(
            cid="QmTest",
            output="/tmp/out",
            wait=True,
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "ipfs download" in cmd
    assert "QmTest" in cmd
    assert "--output=/tmp/out" in cmd
    assert "--wait" in cmd


def test_create_wallet():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.create_wallet(
            name="test-wallet",
            wallet_type="simple",
            encrypt=False,
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "wallet create" in cmd
    assert "test-wallet" in cmd
    assert "--type=simple" in cmd
    assert "--no-encrypt" in cmd


def test_dry_run_gating():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.buy_ait_exchange(
            amount="1.0",
            max_price="0.00076",
            dry_run=True,
            confirm=False,
            role="hub",
        )
    )
    assert result.get("dry_run") is True
    assert "command" in result
    assert not CAPTURED


def test_run_market_offer():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.run_market_offer(
            offer_id_or_plugin_id="sw_offer_1234",
            prompt="transcribe this",
            wallet="test-wallet-3",
            language="en",
            stream=True,
            dry_run=False,
            confirm=True,
            role="customer",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert cmd.startswith("AITBC_WALLET_DIR=/var/lib/aitbc/wallets")
    assert "market --wallet=test-wallet-3 run" in cmd
    assert "sw_offer_1234" in cmd
    assert "'transcribe this'" in cmd
    assert "--language=en" in cmd
    assert "--stream" in cmd


def test_send_aitbc_from_wallet():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.send_aitbc_from_wallet(
            to_address="0xC10F0E4fC10f0e4FC10f0e4fC10F0E4FC10F0e4f",
            amount="1.5",
            wallet_name="test-wallet-3",
            fee="0.001",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert cmd.startswith("AITBC_WALLET_DIR=/var/lib/aitbc/wallets")
    assert "wallet --wallet-name=test-wallet-3 send" in cmd
    assert "0xC10F0E4fC10f0e4FC10f0e4fC10F0E4FC10F0e4f" in cmd
    assert "1.5" in cmd
    assert "--fee=0.001" in cmd


def test_nested_market_escrow_create():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.create_market_escrow(
            job_id="job-1234",
            buyer="0xABCDabcdABcDabcDaBCDAbcdABcdAbCdABcDABCd",
            provider="0xDb5247d03cA2e40f3995A583b2C097Ab703efD4d",
            amount="1.0",
            wallet="test-wallet-3",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "market --wallet=test-wallet-3 escrow create" in cmd
    assert "job-1234" in cmd
    assert "0xABCDabcdABcDabcDaBCDAbcdABcdAbCdABcDABCd" in cmd
    assert "0xDb5247d03cA2e40f3995A583b2C097Ab703efD4d" in cmd
    assert "1.0" in cmd


def test_set_aitbc_config():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.set_aitbc_config(
            key="coordinator.url",
            value="https://hub.example.net",
            global_config=True,
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "config set" in cmd
    assert "coordinator.url" in cmd
    assert "https://hub.example.net" in cmd
    assert "--global" in cmd


def test_login_aitbc():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.login_aitbc(
            wallet="test-wallet-3",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert cmd.startswith("AITBC_WALLET_DIR=/var/lib/aitbc/wallets")
    assert "auth login --wallet=test-wallet-3" in cmd


def test_aitbc_system_logs_since_grep():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.aitbc_system_logs(
            service="aitbc-market",
            lines=100,
            since="10 min ago",
            grep="ERROR",
            host="node2",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "system" in cmd
    assert "logs" in cmd
    assert "--since=" in cmd and "10 min ago" in cmd
    assert "--grep=" in cmd and "ERROR" in cmd


def test_aitbc_system_logs_defaults_omit_new_options():
    _clear()
    result = json.loads(aitbc_mcp_cli_tools.aitbc_system_logs(service="aitbc-market", host="node2"))
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "--since" not in cmd
    assert "--grep" not in cmd


def test_aitbc_system_logs_rejects_injection():
    _clear()
    for kwargs in (
        {"since": "10m; rm -rf /"},
        {"since": "10m$(whoami)"},
        {"grep": "a|cat /etc/passwd"},
        {"grep": "A" * 201},
    ):
        result = json.loads(aitbc_mcp_cli_tools.aitbc_system_logs(service="aitbc-market", host="node2", **kwargs))
        assert "error" in result, kwargs
    assert not CAPTURED


def test_aitbc_update_dry_run_runs_check():
    _clear()
    result = json.loads(aitbc_mcp_cli_tools.aitbc_update(host="node2"))
    cmd = _last_command()
    assert "update" in cmd
    assert "--check" in cmd
    assert "--format=json" in cmd
    assert "note" in result


def test_aitbc_update_requires_confirm():
    _clear()
    result = json.loads(aitbc_mcp_cli_tools.aitbc_update(host="node2", dry_run=False))
    assert result["error"] == "Confirmation required"
    assert not CAPTURED


def test_aitbc_update_no_deploy_flag():
    _clear()
    result = json.loads(aitbc_mcp_cli_tools.aitbc_update(host="node2", no_deploy=True, dry_run=False, confirm=True))
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "update" in cmd
    assert "--no-deploy" in cmd
    assert "--check" not in cmd


def test_omitted_optional_params_never_reach_command():
    """Generated tools default every optional parameter to None and skip unset
    options when building the command — an omitted optional must never reach
    the command line, and must never be serialised as the string "None"."""
    import inspect

    import aitbc_mcp_cli_tools_generated_prometheus as generated

    # Optional parameters carry a None default, so the call needs no nulls.
    sig = inspect.signature(generated.aitbc_prometheus_alerts)
    for name in ("prometheus_url",):
        assert sig.parameters[name].default is None, f"{name} has no None default"

    # The watch/notify surface of `prometheus alerts` is stripped on purpose
    # (SKIP_OPTIONS_BY_PATH): it would turn a one-shot read tool into a
    # polling/POST/file-write loop the agent cannot supervise. Assert the
    # skip stays in place instead of silently drifting back.
    for name in ("watch", "interval", "emit", "alert_log_path", "notify_urls"):
        assert name not in sig.parameters, f"{name} reappeared — SKIP_OPTIONS_BY_PATH must keep stripping it"

    _clear()
    result = json.loads(generated.aitbc_prometheus_alerts(role="hub"))
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "alerts" in cmd
    for flag in ("--prometheus-url", "--watch", "--interval", "--emit"):
        assert flag not in cmd, f"{flag} reached the command line despite being unset"
    assert "None" not in cmd


def test_no_generated_tool_exposes_password_or_password_stdin():
    """WAL-1 F1: a secret must never appear in MCP call arguments (it lands in
    transcripts), and a generated tool must never offer --password-stdin (the
    CLI child would read the MCP server's own stdio stream). password_file
    stays exposed — it is the agent-safe form."""
    import ast

    generated = sorted(MCP_SERVER_DIR.glob("aitbc_mcp_cli_tools_generated*.py"))
    assert generated, "no generated MCP cli tool modules found"
    saw_password_file = 0
    for path in generated:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            params = {a.arg for a in node.args.args + node.args.kwonlyargs}
            assert "password" not in params, f"{path.name}::{node.name} exposes 'password'"
            assert "password_stdin" not in params, f"{path.name}::{node.name} exposes 'password_stdin'"
            if "password_file" in params:
                saw_password_file += 1
    assert saw_password_file > 0, "expected some generated tools to keep the safe --password-file form"


# --- MCP-READONLY-1 (issue #417) ---------------------------------------------
#
# 28 scenario replay commands landed on dry_run-gated generated tools although
# the CLI leaf is a read; the generic read_aitbc_cli pivot executed them anyway.
# The generator misclassified them: the leaf token was missing from
# SAFE_LEAF_TOKENS or unreachable behind a hyphenated entry that never matched
# the normalized token.  The promoted leaves below must now execute on a bare
# call, while verified mutating leaves keep the dry_run/confirm gate.


def _generated(module_name: str, func_name: str):
    import importlib

    return getattr(importlib.import_module(module_name), func_name)


# (module, function, kwargs) — minimal kwargs to build the command.
PROMOTED_READ_LEAVES = [
    ("aitbc_mcp_cli_tools_generated_transactions", "aitbc_transactions_pending", {}),
    (
        "aitbc_mcp_cli_tools_generated_transactions",
        "aitbc_transactions_estimate_fee",
        {"from_wallet": "w1", "to_address": "0xd9d9d9d9d9d9d9d9d9d9d9d9d9d9d9d9d9d9d9d9", "amount": "10"},
    ),
    ("aitbc_mcp_cli_tools_generated_exchange_island", "aitbc_exchange_island_orderbook", {"pair": "AIT/ETH"}),
    ("aitbc_mcp_cli_tools_generated_exchange_island", "aitbc_exchange_island_orders", {}),
    ("aitbc_mcp_cli_tools_generated_ai", "aitbc_ai_results", {}),
    ("aitbc_mcp_cli_tools_generated_gpu", "aitbc_gpu_list_gpus", {}),
    ("aitbc_mcp_cli_tools_generated_gpu_onchain", "aitbc_gpu_onchain_query", {"gpu_id": "gpu-0"}),
    ("aitbc_mcp_cli_tools_generated_gpu_onchain", "aitbc_gpu_onchain_allocations", {"gpu_id": "gpu-0"}),
    ("aitbc_mcp_cli_tools_generated_agent", "aitbc_agent_discover_agents", {}),
    ("aitbc_mcp_cli_tools_generated_reputation", "aitbc_reputation_trust_score", {"agent_id": "agent-1"}),
    ("aitbc_mcp_cli_tools_generated_analytics", "aitbc_analytics_predict", {}),
    ("aitbc_mcp_cli_tools_generated_security", "aitbc_security_scan", {}),
    ("aitbc_mcp_cli_tools_generated_crosschain", "aitbc_crosschain_bridge_status", {"bridge_id": "0xabc"}),
    ("aitbc_mcp_cli_tools_generated_bridge", "aitbc_bridge_pending", {}),
    ("aitbc_mcp_cli_tools_generated_explorer", "aitbc_explorer_network_stats", {}),
    ("aitbc_mcp_cli_tools_generated_zk", "aitbc_zk_circuits", {}),
    ("aitbc_mcp_cli_tools_generated_dispute", "aitbc_dispute_active", {}),
    # Curated-twin leaves promoted alongside (issue gate-3…14).
    ("aitbc_mcp_cli_tools_generated_market", "aitbc_market_escrow_status", {"job_id": "job-1"}),
    ("aitbc_mcp_cli_tools_generated_market", "aitbc_market_exchange_price", {}),
    ("aitbc_mcp_cli_tools_generated_market", "aitbc_market_exchange_list_deposits", {}),
    ("aitbc_mcp_cli_tools_generated_dashboard", "aitbc_dashboard_customer", {}),
    ("aitbc_mcp_cli_tools_generated_dashboard", "aitbc_dashboard_shop", {}),
    ("aitbc_mcp_cli_tools_generated_node", "aitbc_node_island_island_info", {"island_id": "is-1"}),
    ("aitbc_mcp_cli_tools_generated_node", "aitbc_node_island_list_islands", {}),
    # Bonus promotions from the token fixes — all verified pure reads.
    ("aitbc_mcp_cli_tools_generated_bridge", "aitbc_bridge_security_status", {}),
    ("aitbc_mcp_cli_tools_generated_explorer", "aitbc_explorer_block_by_hash", {"block_hash": "0xabc"}),
    ("aitbc_mcp_cli_tools_generated_explorer", "aitbc_explorer_blocks_by_address", {"address": "0xabc"}),
    ("aitbc_mcp_cli_tools_generated_explorer", "aitbc_explorer_non_empty_blocks", {}),
    ("aitbc_mcp_cli_tools_generated_explorer", "aitbc_explorer_top_addresses", {}),
    ("aitbc_mcp_cli_tools_generated_explorer", "aitbc_explorer_transaction_by_hash", {"tx_hash": "0xabc"}),
    ("aitbc_mcp_cli_tools_generated_monitor", "aitbc_monitor_campaign_stats", {}),
    ("aitbc_mcp_cli_tools_generated_edge", "aitbc_edge_gpu_list_gpus", {}),
    ("aitbc_mcp_cli_tools_generated_simulate", "aitbc_simulate_price", {}),
]


def test_promoted_read_leaves_execute_without_gate():
    """Every leaf re-verified as a read runs on a bare call — no dry_run or
    confirm parameter exists, and the result is never a dry-run envelope."""
    import inspect

    for module_name, func_name, kwargs in PROMOTED_READ_LEAVES:
        func = _generated(module_name, func_name)
        params = inspect.signature(func).parameters
        assert "dry_run" not in params, f"{func_name} still exposes dry_run"
        assert "confirm" not in params, f"{func_name} still exposes confirm"
        _clear()
        result = json.loads(func(**kwargs))
        assert result.get("dry_run") is not True, f"{func_name} returned a dry-run envelope"
        assert "command" not in result or "returncode" in result, f"{func_name} returned a would-be command only"


def test_mutating_gate_check_still_enforced():
    """The 10 Phase-A gate-check tools keep the dry_run/confirm contract:
    dry-run envelope on defaults, refusal without confirm, execute with both."""
    gated = [
        ("aitbc_mcp_cli_tools_generated_wallet", "aitbc_wallet_create", {"name": "w1"}),
        (
            "aitbc_mcp_cli_tools_generated_transactions",
            "aitbc_transactions_send",
            {"from_wallet": "w1", "to_address": "0xd9d9d9d9d9d9d9d9d9d9d9d9d9d9d9d9d9d9d9d9", "amount": "1"},
        ),
        ("aitbc_mcp_cli_tools_generated_ai", "aitbc_ai_submit", {}),
        (
            "aitbc_mcp_cli_tools_generated_market",
            "aitbc_market_offer",
            {"service_type": "whisper", "model_or_variant": "tiny", "price": "1"},
        ),
        ("aitbc_mcp_cli_tools_generated_bond", "aitbc_bond_create", {"provider_id": "p1"}),
        (
            "aitbc_mcp_cli_tools_generated_governance",
            "aitbc_governance_propose",
            {"title": "t", "description": "d", "proposer_id": "p1"},
        ),
        (
            "aitbc_mcp_cli_tools_generated_bridge",
            "aitbc_bridge_lock",
            {"target_chain": "ait-test", "sender": "0x1", "recipient": "0x2", "amount": 1},
        ),
        ("aitbc_mcp_cli_tools_generated_system", "aitbc_system_restart", {"service": "wallet"}),
        ("aitbc_mcp_cli_tools_generated_system", "aitbc_system_env_set", {"service": "wallet"}),
        ("aitbc_mcp_cli_tools_generated_auth", "aitbc_auth_login", {}),
    ]
    for module_name, func_name, kwargs in gated:
        func = _generated(module_name, func_name)

        _clear()
        result = json.loads(func(**kwargs))
        assert result.get("dry_run") is True, f"{func_name} executed on a default call"
        assert "command" in result
        assert not CAPTURED, f"{func_name} reached the remote on a default call"

        _clear()
        result = json.loads(func(**kwargs, dry_run=False, confirm=False))
        assert "Confirmation required" in result.get("error", ""), f"{func_name} ran without confirm"
        assert not CAPTURED, f"{func_name} reached the remote without confirm"

        _clear()
        result = json.loads(func(**kwargs, dry_run=False, confirm=True))
        assert result.get("returncode") == 0, f"{func_name} failed to execute with confirm"
        assert CAPTURED, f"{func_name} never reached the remote with confirm"


def test_read_only_curated_tools_have_ungated_twins():
    """No curated tool may sit read-only-marked while its generated twin on the
    same CLI leaf is destructive-gated — the dual exposure this row removes.

    Exception: get_zk_refund_sweep_candidates is read-only on purpose — it pins
    --dry-run on `ai refund-sweep`, a leaf that genuinely mutates without it.
    """
    import inspect

    pairs = [
        (
            aitbc_mcp_cli_tools.get_exchange_orderbook,
            "aitbc_mcp_cli_tools_generated_exchange_island",
            "aitbc_exchange_island_orderbook",
        ),
        (
            aitbc_mcp_cli_tools.get_exchange_orders,
            "aitbc_mcp_cli_tools_generated_exchange_island",
            "aitbc_exchange_island_orders",
        ),
        (aitbc_mcp_cli_tools.list_node_islands, "aitbc_mcp_cli_tools_generated_node", "aitbc_node_island_list_islands"),
        (aitbc_mcp_cli_tools.get_node_island_info, "aitbc_mcp_cli_tools_generated_node", "aitbc_node_island_island_info"),
        (aitbc_mcp_cli_tools.get_market_escrow_status, "aitbc_mcp_cli_tools_generated_market", "aitbc_market_escrow_status"),
        (aitbc_mcp_cli_tools.get_market_exchange_price, "aitbc_mcp_cli_tools_generated_market", "aitbc_market_exchange_price"),
        (
            aitbc_mcp_cli_tools.list_market_exchange_deposits,
            "aitbc_mcp_cli_tools_generated_market",
            "aitbc_market_exchange_list_deposits",
        ),
        (mcp_server.get_ai_job_results, "aitbc_mcp_cli_tools_generated_ai", "aitbc_ai_results"),
        (mcp_server.list_pending_transactions, "aitbc_mcp_cli_tools_generated_transactions", "aitbc_transactions_pending"),
        (mcp_server.get_aitbc_dashboard_customer, "aitbc_mcp_cli_tools_generated_dashboard", "aitbc_dashboard_customer"),
        (mcp_server.get_aitbc_dashboard_shop, "aitbc_mcp_cli_tools_generated_dashboard", "aitbc_dashboard_shop"),
        (mcp_server.list_gpus, "aitbc_mcp_cli_tools_generated_gpu", "aitbc_gpu_list_gpus"),
    ]
    for curated, module_name, twin_name in pairs:
        curated_params = inspect.signature(curated).parameters
        assert "dry_run" not in curated_params, f"{curated.__name__} unexpectedly gated"
        twin_params = inspect.signature(_generated(module_name, twin_name)).parameters
        assert "dry_run" not in twin_params and "confirm" not in twin_params, (
            f"{curated.__name__} is read-only while generated twin {twin_name} is gated"
        )


def test_ipfs_downloaders_are_gated_both_lanes():
    """Both download leaves write a file on the remote host: the curated tools
    and their generated twins must all carry the dry_run/confirm gate."""
    import inspect

    for func in (
        aitbc_mcp_cli_tools.download_ipfs,
        aitbc_mcp_cli_tools.download_market_ipfs,
        _generated("aitbc_mcp_cli_tools_generated_ipfs", "aitbc_ipfs_download"),
        _generated("aitbc_mcp_cli_tools_generated_market", "aitbc_market_download"),
    ):
        params = inspect.signature(func).parameters
        assert "dry_run" in params and "confirm" in params, f"{func.__name__} lost its gate"
        assert params["dry_run"].default is True, f"{func.__name__} defaults dry_run off"
        assert params["confirm"].default is False, f"{func.__name__} defaults confirm on"

    _clear()
    result = json.loads(aitbc_mcp_cli_tools.download_market_ipfs(cid="QmTest", role="hub"))
    assert result.get("dry_run") is True
    assert not CAPTURED


def test_list_node_islands_targets_real_leaf():
    """gate-5: the curated tool called a nonexistent `island-list-islands`
    subcommand; it must build the real `node island list-islands` leaf."""
    _clear()
    result = json.loads(aitbc_mcp_cli_tools.list_node_islands(role="hub"))
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "node island list-islands" in cmd
    assert "island-list-islands" not in cmd.replace("node island list-islands", "")


def test_list_aitbc_ipfs_rentals_removed():
    """gate-12: `ipfs rentals` does not exist in the CLI tree — the tool could
    only ever return click's 'No such command' and is dropped."""
    assert not hasattr(mcp_server, "list_aitbc_ipfs_rentals")


# --- MCP-SECRETS-1 (issue #419) -----------------------------------------------
#
# SM-03: a secret *value* as an MCP call argument lands in the agent
# transcript, the MCP client log, the local ssh argv and the remote process
# list. No tool schema may accept one. The generator skips secret-named
# options by pattern (SECRET_VALUE_RE); curated tools keep only the file-path
# forms. This gate scans every registered tool module — generated AND
# curated — so a future secret parameter cannot slip back in either lane.


def _generator_secret_policy():
    """Load SECRET_VALUE_RE / path suffixes / allowlist from the generator.

    Extracted with ``ast`` so the test never has to import the generator
    (which pulls the whole CLI command tree) and cannot drift out of sync
    with the real skip rule.
    """
    import ast
    import re as _re

    gen_path = MCP_SERVER_DIR.parent / "scripts" / "dev" / "generate_mcp_cli_tools.py"
    tree = ast.parse(gen_path.read_text())
    pattern = None
    suffixes: tuple[str, ...] = ()
    allowlist: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SECRET_VALUE_RE":
                    pattern = ast.literal_eval(node.value.args[0])
                if isinstance(target, ast.Name) and target.id == "SECRET_PATH_SUFFIXES":
                    suffixes = ast.literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "SECRET_PATH_SUFFIXES":
                suffixes = ast.literal_eval(node.value)
            if node.target.id == "SECRET_OPTION_ALLOWLIST":
                allowlist = ast.literal_eval(node.value)
    assert pattern is not None, "SECRET_VALUE_RE not found in generator"
    assert suffixes, "SECRET_PATH_SUFFIXES not found in generator"
    return _re.compile(pattern), tuple(suffixes), allowlist


# Param names that match the generator's secret pattern but are NOT secret
# values. One-line reason per entry — adding an entry is the deliberate act
# the schema gate exists to force.
SECRET_PARAM_TEST_ALLOWLIST = {
    "show_secrets": "display toggle on `aitbc system config` — it controls whether stored secrets print in the output; the flag itself is not a secret value",
}


def _is_secret_param(name: str) -> bool:
    regex, suffixes, allowlist = _generator_secret_policy()
    if name.endswith(suffixes) or name in allowlist or name in SECRET_PARAM_TEST_ALLOWLIST:
        return False
    return regex.search(name) is not None


def test_no_mcp_tool_schema_accepts_secret_values():
    """Every mcp-server module's tool params are secret-value-free."""
    import ast

    modules = sorted(MCP_SERVER_DIR.glob("*.py"))
    assert modules, "no mcp-server modules found"
    offenders: list[str] = []
    used_allowlist: set[str] = set()
    for path in modules:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for arg in node.args.args + node.args.kwonlyargs:
                name = arg.arg
                if name in SECRET_PARAM_TEST_ALLOWLIST:
                    used_allowlist.add(name)
                    continue
                if _is_secret_param(name):
                    offenders.append(f"{path.name}::{node.name} exposes secret-value param '{name}'")
    assert not offenders, "MCP tools must not accept secret values:\n" + "\n".join(offenders)
    for name in SECRET_PARAM_TEST_ALLOWLIST:
        assert name in used_allowlist, f"stale allow-list entry '{name}' — remove it or the param was renamed"


def test_auth_login_drops_private_key_value():
    """aitbc_auth_login keeps --private-key-file but never the raw value."""
    import inspect

    import aitbc_mcp_cli_tools_generated_auth as generated

    params = inspect.signature(generated.aitbc_auth_login).parameters
    assert "private_key" not in params, "raw private_key param reappeared on aitbc_auth_login"
    assert "private_key_file" in params, "--private-key-file is the accepted form and must stay"

    _clear()
    result = json.loads(generated.aitbc_auth_login(wallet="w1", password_file="/tmp/pw", dry_run=True, role="hub"))
    cmd = result["command"]
    assert "--private-key" not in cmd
    assert "--private-key-file" not in cmd  # unset — no phantom option


def test_removed_secret_params_stay_removed():
    """Spot-check the signatures of the highest-risk generated tools."""
    import importlib
    import inspect

    gone = {
        ("aitbc_mcp_cli_tools_generated_bridge", "aitbc_bridge_attest"): {"private_key"},
        ("aitbc_mcp_cli_tools_generated_bridge", "aitbc_bridge_store_header"): {"admin_private_key"},
        ("aitbc_mcp_cli_tools_generated_bridge", "aitbc_bridge_lock"): {"wallet_password"},
        ("aitbc_mcp_cli_tools_generated_bridge", "aitbc_bridge_unlock"): {"wallet_password"},
        ("aitbc_mcp_cli_tools_generated_network", "aitbc_network_force_sync"): {"admin_private_key"},
        ("aitbc_mcp_cli_tools_generated_exchange", "aitbc_exchange_register"): {"api_key", "secret_key"},
        ("aitbc_mcp_cli_tools_generated_http", "aitbc_http_call"): {"api_key"},
        ("aitbc_mcp_cli_tools_generated_ipfs", "aitbc_ipfs_island_swarm_key"): {"api_key"},
        ("aitbc_mcp_cli_tools_generated_ipfs", "aitbc_ipfs_download"): {"access_secret"},
        ("aitbc_mcp_cli_tools_generated_market", "aitbc_market_download"): {"access_secret"},
        ("aitbc_mcp_cli_tools_generated_trade", "aitbc_trade_settle"): {"api_key", "secret"},
        ("aitbc_mcp_cli_tools_generated_trade", "aitbc_trade_lock_escrow"): {"api_key"},
    }
    for (module_name, func_name), removed in gone.items():
        params = inspect.signature(getattr(importlib.import_module(module_name), func_name)).parameters
        leaked = removed & set(params)
        assert not leaked, f"{func_name} re-exposes {leaked}"


def test_rental_token_tools_use_file_forms():
    """Curated HTTP tools keep working via MCP-host file paths."""
    import inspect

    import aitbc_mcp_rpc_tools as rpc_tools

    get_params = inspect.signature(rpc_tools.get_ipfs_rental_token).parameters
    assert "access_secret" not in get_params
    assert "access_secret_file" in get_params

    reg_params = inspect.signature(rpc_tools.register_ipfs_rental_token).parameters
    assert "token" not in reg_params
    assert "token_file" in reg_params

    dl_params = inspect.signature(aitbc_mcp_cli_tools.download_market_ipfs).parameters
    assert "access_secret" not in dl_params


def test_secret_file_forms_scrub_the_value_from_output(tmp_path):
    """The echoed command in _run_remote results must not leak the secret."""
    secret = "fake-secret-value-for-tests"  # noqa: S105 - obviously fake fixture
    secret_file = tmp_path / "access_secret"
    secret_file.write_text(secret + "\n")

    _clear()
    import aitbc_mcp_rpc_tools as rpc_tools

    out = rpc_tools.get_ipfs_rental_token(access_key="ak-test", access_secret_file=str(secret_file), role="hub")
    assert secret not in out, "rental secret leaked into serialized tool output"
    assert "***" in out
    # The forwarded call did carry the secret on the remote argv (recorded
    # follow-up: `aitbc http call` has no --params-file) — prove the relay
    # still happened.
    assert "access_secret" in _last_command()

    token_file = tmp_path / "token.json"
    token_file.write_text(
        json.dumps({"access_key": "ak-test", "access_secret": secret, "rental_id": "r-1", "cid": "bafy-test"})
    )
    _clear()
    out = rpc_tools.register_ipfs_rental_token(token_file=str(token_file), dry_run=True, role="hub")
    assert secret not in out, "token secret leaked into dry-run output"

    missing = rpc_tools.get_ipfs_rental_token(access_key="ak", access_secret_file=str(tmp_path / "nope"), role="hub")
    assert "error" in json.loads(missing)


def test_scrub_secrets_unit():
    import aitbc_mcp_rpc_tools as rpc_tools

    assert rpc_tools._scrub_secrets('{"command": "--x=fake-token"}', ["fake-token"]) == '{"command": "--x=***"}'
    assert rpc_tools._scrub_secrets("plain", [None, ""]) == "plain"

def test_format_option_forwarded_on_typed_tool():
    """MCP-MISC-1/SM-08: a leaf-declared --format reaches the CLI argv."""
    import aitbc_mcp_cli_tools_generated_reputation as generated

    _clear()
    result = json.loads(generated.aitbc_reputation_metrics(format="table", role="hub"))
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "--format=table" in cmd
    # The global --output=json default is still emitted; the leaf wins where
    # it declares its own format option.
    assert "--output=json" in cmd


def test_format_option_omitted_when_unset():
    import aitbc_mcp_cli_tools_generated_reputation as generated

    _clear()
    result = json.loads(generated.aitbc_reputation_metrics(role="hub"))
    assert result["returncode"] == 0
    assert "--format" not in _last_command()


def test_output_format_option_deduped_to_single_param():
    """OUTPUT_FORMAT_OPTION declares --output and --format on one param name;
    the generated tool must emit exactly one flag (--format preferred)."""
    import inspect

    import aitbc_mcp_cli_tools_generated_blockchain as generated

    params = inspect.signature(generated.aitbc_blockchain_height).parameters
    assert list(params).count("output_format") == 1

    _clear()
    result = json.loads(generated.aitbc_blockchain_height(output_format="yaml", role="hub"))
    assert result["returncode"] == 0
    cmd = _last_command()
    assert cmd.count("--format=") == 1
    assert "--format=yaml" in cmd


def test_crosschain_bridge_status_emits_bridge_id():
    """MCP-MISC-1/SM-10: the canonical --bridge-id spelling reaches the argv,
    not the --transfer-id alias."""
    import aitbc_mcp_cli_tools_generated_crosschain as generated

    _clear()
    result = json.loads(generated.aitbc_crosschain_bridge_status(bridge_id="0xbridge1", dry_run=True, role="hub"))
    cmd = result["command"]
    assert "--bridge-id=0xbridge1" in cmd
    assert "--transfer-id" not in cmd


if __name__ == "__main__":
    test_buy_ait_exchange()
    test_sell_ait_exchange()
    test_get_exchange_orderbook()
    test_create_island()
    test_join_island()
    test_join_island_as_hub()
    test_create_market_offer()
    test_upload_ipfs()
    test_download_ipfs()
    test_create_wallet()
    test_dry_run_gating()
    test_run_market_offer()
    test_send_aitbc_from_wallet()
    test_omitted_optional_params_never_reach_command()
    test_no_generated_tool_exposes_password_or_password_stdin()
    test_promoted_read_leaves_execute_without_gate()
    test_mutating_gate_check_still_enforced()
    test_read_only_curated_tools_have_ungated_twins()
    test_ipfs_downloaders_are_gated_both_lanes()
    test_list_node_islands_targets_real_leaf()
    test_list_aitbc_ipfs_rentals_removed()
    test_nested_market_escrow_create()
    test_set_aitbc_config()
    test_login_aitbc()
    test_format_option_forwarded_on_typed_tool()
    test_format_option_omitted_when_unset()
    test_output_format_option_deduped_to_single_param()
    test_crosschain_bridge_status_emits_bridge_id()
    print("All aitbc_mcp_cli_tools tests passed")
