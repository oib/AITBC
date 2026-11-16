"""Regression pins for the scenario-finding CLI batch (#2103/#2104/#2106/#2096/#2113)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


# --- #2113 reinvest policy persistence -------------------------------------


def test_reinvest_policy_persists_and_simulate_honors_it(runner, tmp_path, monkeypatch):
    from aitbc_cli.commands import reinvest

    store = tmp_path / "reinvest_policies.json"
    monkeypatch.setattr(reinvest, "_POLICY_STORE", store)

    from aitbc_cli.commands.reinvest import policy, simulate

    r1 = runner.invoke(
        policy, ["--agent-id", "agent-1", "--staking-pct", "70", "--reserve-pct", "30"], obj={"output_format": "table"}
    )
    assert r1.exit_code == 0, r1.output
    saved = json.loads(store.read_text())
    assert saved["agent-1"]["staking_pct"] == "70"

    captured = {}

    class FakeEngine:
        def __init__(self, budget, pol):
            captured["policy"] = pol

        def apply(self, amount, agent_id):
            return []

    class FakePolicy:
        def __init__(self, **kw):
            captured["policy_kwargs"] = kw

    class FakeBudget:
        def __init__(self, **kw):
            pass

    with patch.object(reinvest, "_load_miner_app", return_value=(FakeEngine, FakePolicy, FakeBudget)):
        r2 = runner.invoke(simulate, ["--agent-id", "agent-1", "--earnings", "10"], obj={"output_format": "table"})
    assert r2.exit_code == 0, r2.output
    assert captured["policy_kwargs"]["staking_pct"] == pytest.approx(70)
    assert captured["policy_kwargs"]["capacity_reserve_pct"] == pytest.approx(30)


def test_reinvest_policy_rejects_bad_split(runner, tmp_path, monkeypatch):
    from aitbc_cli.commands import reinvest
    from aitbc_cli.commands.reinvest import policy

    monkeypatch.setattr(reinvest, "_POLICY_STORE", tmp_path / "p.json")
    r = runner.invoke(
        policy, ["--agent-id", "a", "--staking-pct", "50", "--reserve-pct", "30"], obj={"output_format": "table"}
    )
    assert r.exit_code != 0


# --- #2103 coin-requests DB path resolution ---------------------------------


def test_agent_db_path_prefers_service_env(tmp_path, monkeypatch):
    import aitbc.db.agent_db as mod
    from pathlib import Path as RealPath

    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "agent-coordinator.env").write_text("AGENT_DB_PATH=/var/lib/aitbc/data/agent_coin_requests.db\n")
    (etc / "coordinator-api.env").write_text("AGENT_DB_PATH=/var/lib/aitbc/data/hermes_coin_requests.db\n")

    monkeypatch.setattr(mod, "Path", lambda p=".": RealPath(str(etc)) if p == "/etc/aitbc" else RealPath(p))
    monkeypatch.delenv("AGENT_DB_PATH", raising=False)
    monkeypatch.delenv("HERMES_DB_PATH", raising=False)
    assert mod.get_db_path() == "/var/lib/aitbc/data/hermes_coin_requests.db"


def test_agent_db_path_explicit_env_wins(tmp_path, monkeypatch):
    from aitbc.db import agent_db

    monkeypatch.setenv("AGENT_DB_PATH", "/tmp/explicit.db")
    assert agent_db.get_db_path() == "/tmp/explicit.db"


# --- #2106 workflow list hits the coordinator -------------------------------


def test_workflow_list_queries_coordinator(runner):
    from aitbc_cli.commands.workflow import list as list_cmd

    config = MagicMock()
    config.coordinator_api_url = "http://coord.example:8203/v1"
    config.coordinator_api_key = "k"

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = [
        {"id": "agent_1", "name": "gpu-market", "owner_id": "u1", "version": "1.0.0", "steps": {"a": {}, "b": {}}},
    ]

    with (
        patch("aitbc_cli.commands.workflow.get_config", return_value=config),
        patch("httpx.get", return_value=resp) as get,
    ):
        result = runner.invoke(list_cmd, ["--format", "json"], obj={"output_format": "json"})

    assert result.exit_code == 0, result.output
    assert get.call_args[0][0] == "http://coord.example:8203/v1/agents/workflows"
    rows = json.loads(result.output)
    assert rows[0]["name"] == "gpu-market"
    assert rows[0]["steps"] == 2


def test_workflow_list_surfaces_api_error(runner):
    from aitbc_cli.commands.workflow import list as list_cmd

    config = MagicMock()
    config.coordinator_api_url = "http://coord.example:8203"
    config.coordinator_api_key = "k"

    resp = MagicMock()
    resp.status_code = 403
    resp.text = "forbidden"

    with (
        patch("aitbc_cli.commands.workflow.get_config", return_value=config),
        patch("httpx.get", return_value=resp),
    ):
        result = runner.invoke(list_cmd, [], obj={"output_format": "table"})

    assert result.exit_code != 0
    assert "403" in result.output


# --- #2096 island join rejects malformed response ---------------------------


def test_island_join_refuses_null_credentials(runner, tmp_path, monkeypatch):
    import click

    import importlib

    island = importlib.import_module("aitbc_cli.commands.node.island")

    keystore = tmp_path / "validator_keys.json"
    keystore.write_text(json.dumps({"k1": {"public_key_pem": "PEM"}}))

    fake_client = MagicMock()
    fake_client.post.return_value = {"success": True, "island_id": None, "credentials": None}

    real_exists = island.os.path.exists
    real_open = island.open if hasattr(island, "open") else open

    def fake_exists(p):
        return str(p) == "/var/lib/aitbc/keystore/validator_keys.json" or real_exists(p)

    def fake_open(path, *a, **kw):
        if str(path) == "/var/lib/aitbc/keystore/validator_keys.json":
            return real_open(keystore)
        return real_open(path, *a, **kw)

    monkeypatch.setattr(island.os.path, "exists", fake_exists)
    monkeypatch.setattr("builtins.open", fake_open)

    with (
        patch.object(island, "AITBCHTTPClient", return_value=fake_client),
        patch("aitbc_cli.config.get_config", return_value=MagicMock(blockchain_rpc_api_key=None)),
        patch.object(island.os, "open", side_effect=AssertionError("must not write credentials")),
    ):
        ctx = MagicMock()
        ctx.obj = {"output_format": "table"}
        with pytest.raises(click.Abort):
            island.join_island_command(ctx, "isl-1", "hub", "ait-mainnet", "hub.example", False, rpc_url="http://hub:8202")


# --- #2104 list-chains uses live node inventory ------------------------------


def test_list_chains_uses_live_inventory(runner):
    import importlib

    chain_mod = importlib.import_module("aitbc_cli.commands.node.chain")

    fake_chain = MagicMock()
    fake_chain.id = "bc-2"
    fake_chain.name = "AITBC Bc 2 Chain"
    fake_chain.status.value = "active"
    fake_chain.block_height = 28700

    from unittest.mock import AsyncMock

    fake_client = AsyncMock()
    fake_client.get_hosted_chains = AsyncMock(return_value=[fake_chain])

    node_cfg = MagicMock()
    config = MagicMock()
    config.nodes = {"n1": node_cfg}

    ctx = MagicMock()
    ctx.obj = {"output": "json"}

    with (
        patch("aitbc_cli.core.config.load_multichain_config", return_value=config),
        patch("aitbc_cli.core.node_client.NodeClient", return_value=fake_client),
    ):
        chain_mod.list_chains_command(ctx)
