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
        patch("aitbc_cli.commands.workflow.auth_headers", return_value={"Authorization": "Bearer t"}),
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
        patch("aitbc_cli.commands.workflow.auth_headers", return_value={}),
        patch("httpx.get", return_value=resp),
    ):
        result = runner.invoke(list_cmd, [], obj={"output_format": "table"})

    assert result.exit_code != 0
    assert "403" in result.output


# --- #2231 workflow commands route the admin credential + name the gate ------


def test_workflow_list_requests_admin_credential(runner):
    from aitbc_cli.commands.workflow import list as list_cmd

    config = MagicMock()
    config.coordinator_api_url = "http://coord.example:8203"
    config.coordinator_api_key = "k"

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = []

    with (
        patch("aitbc_cli.commands.workflow.get_config", return_value=config),
        patch("aitbc_cli.commands.workflow.auth_headers", return_value={}) as headers,
        patch("httpx.get", return_value=resp),
    ):
        result = runner.invoke(list_cmd, [], obj={"output_format": "table", "api_key": "explicit-jwt"})

    assert result.exit_code == 0, result.output
    assert headers.call_args.kwargs["credential"] == "admin"
    assert headers.call_args.kwargs["explicit_key"] == "explicit-jwt"


def test_workflow_list_403_names_admin_gate(runner):
    from aitbc_cli.commands.workflow import list as list_cmd

    config = MagicMock()
    config.coordinator_api_url = "http://coord.example:8203"
    config.coordinator_api_key = "k"

    resp = MagicMock()
    resp.status_code = 403
    resp.text = '{"detail":"Role required"}'

    with (
        patch("aitbc_cli.commands.workflow.get_config", return_value=config),
        patch("aitbc_cli.commands.workflow.auth_headers", return_value={}),
        patch("httpx.get", return_value=resp),
    ):
        result = runner.invoke(list_cmd, [], obj={"output_format": "table"})

    assert result.exit_code != 0
    assert "admin-role credential" in result.output
    assert "auth login --credential-name admin" in result.output


def test_workflow_status_403_names_admin_gate(runner):
    from aitbc_cli.commands.workflow import status as status_cmd

    config = MagicMock()
    config.coordinator_api_url = "http://coord.example:8203"
    config.coordinator_api_key = "k"

    resp = MagicMock()
    resp.status_code = 403
    resp.text = '{"detail":"Role required"}'

    with (
        patch("aitbc_cli.commands.workflow.get_config", return_value=config),
        patch("aitbc_cli.commands.workflow.auth_headers", return_value={}),
        patch("httpx.get", return_value=resp),
    ):
        result = runner.invoke(status_cmd, ["--workflow-name", "gpu-market"], obj={"output_format": "table"})

    assert result.exit_code != 0
    assert "admin-role credential" in result.output


def test_workflow_run_expired_admin_token_surfaces_relogin(runner):
    from aitbc_cli.commands.workflow import run as run_cmd
    from aitbc_cli.auth import ExpiredAdminToken

    config = MagicMock()
    config.coordinator_api_url = "http://coord.example:8203"
    config.coordinator_api_key = "k"

    with (
        patch("aitbc_cli.commands.workflow.get_config", return_value=config),
        patch(
            "aitbc_cli.commands.workflow.auth_headers",
            side_effect=ExpiredAdminToken("The stored admin credential has expired. Run `aitbc auth login` to refresh it."),
        ),
    ):
        result = runner.invoke(run_cmd, ["--workflow-name", "gpu-market"], obj={"output_format": "table"})

    assert result.exit_code != 0
    assert "auth login" in result.output


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


# --- #2097 wallet info shows live chain balance ------------------------------


def _write_wallet(tmp_path, name="w1"):
    import aitbc_cli.commands.wallet.basic as basic_mod

    wdir = tmp_path / "wallets"
    wdir.mkdir(exist_ok=True)
    (wdir / f"{name}.json").write_text(
        json.dumps(
            {
                "wallet_id": name,
                "type": "simple",
                "address": "0xce6c422fe31fc3bc0299cfad0070125ebc306dff",
                "public_key": "0x02" + "11" * 32,
                "balance": 5.0,
                "created_at": "2026-01-01T00:00:00",
            }
        )
    )
    return basic_mod, wdir


def test_wallet_info_prefers_chain_balance(runner, tmp_path):
    basic_mod, wdir = _write_wallet(tmp_path)
    client = MagicMock()
    client.get.return_value = {"balance": 108000000, "nonce": 3, "chain_id": "bc-2"}
    cfg = MagicMock()
    cfg.blockchain_rpc_url = "http://rpc:8202"
    import aitbc_cli.commands.wallet as wallet_pkg

    with (
        patch.object(basic_mod, "AITBCHTTPClient", return_value=client),
        patch.object(basic_mod, "get_config", return_value=cfg),
        patch.object(wallet_pkg, "resolve_wallet_dir", return_value=wdir),
    ):
        result = runner.invoke(
            basic_mod.wallet,
            obj={"output_format": "json", "wallet_name": "w1", "chain_id": "bc-2"},
            args=["info", "--name", "w1"],
        )
    assert result.exit_code == 0, result.output
    body = json.loads(result.output[result.output.index("{") :])
    assert body["balance_source"] == "chain"
    assert body["balance"] == basic_mod.format_ait(108000000)


def test_wallet_info_falls_back_to_stored_with_label(runner, tmp_path):
    from aitbc.exceptions import NetworkError

    basic_mod, wdir = _write_wallet(tmp_path)
    client = MagicMock()
    client.get.side_effect = NetworkError("connection refused")
    cfg = MagicMock()
    cfg.blockchain_rpc_url = "http://rpc:8202"
    import aitbc_cli.commands.wallet as wallet_pkg

    with (
        patch.object(basic_mod, "AITBCHTTPClient", return_value=client),
        patch.object(basic_mod, "get_config", return_value=cfg),
        patch.object(wallet_pkg, "resolve_wallet_dir", return_value=wdir),
    ):
        result = runner.invoke(
            basic_mod.wallet,
            obj={"output_format": "json", "wallet_name": "w1", "chain_id": "bc-2"},
            args=["info", "--name", "w1"],
        )
    assert result.exit_code == 0, result.output
    body = json.loads(result.output[result.output.index("{") :])
    assert body["balance_source"] == "stored-file (may be stale)"
    assert "balance" in body


# --- #2101-partial: ai stats hits the registered admin route -----------------


def test_ai_stats_uses_admin_route(runner):
    import aitbc_cli.commands.ai as ai_mod

    client = MagicMock()
    client.get.return_value = {"total_jobs": 3}
    cfg = MagicMock()
    cfg.coordinator_api_url = "http://coord:8203"
    with (
        patch.object(ai_mod, "get_config", return_value=cfg),
        patch.object(ai_mod, "_coordinator_base_url", return_value="http://coord:8203"),
        patch.object(ai_mod, "_auth_headers", return_value={}),
        patch.object(ai_mod, "AITBCHTTPClient", return_value=client),
    ):
        result = runner.invoke(ai_mod.stats, ["--coordinator-url", "http://coord:8203"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    assert client.get.call_args[0][0] == "/v1/admin/stats"


# --- #2092 bridge deposits repo-root auto-detection --------------------------


def test_bridge_repo_root_finds_checkout_from_cwd(tmp_path, monkeypatch):
    import aitbc_cli.commands.bridge as bridge_mod

    checkout = tmp_path / "opt" / "aitbc"
    admin = checkout / "apps" / "bridge-monitor" / "src" / "bridge_monitor" / "admin.py"
    admin.parent.mkdir(parents=True)
    admin.write_text("# stub\n")
    workdir = checkout / "sub" / "dir"
    workdir.mkdir(parents=True)
    monkeypatch.chdir(workdir)
    monkeypatch.delenv("AITBC_REPO_ROOT", raising=False)
    assert bridge_mod._resolve_bridge_repo_root(None) == checkout


def test_bridge_repo_root_explicit_wins(tmp_path, monkeypatch):
    import aitbc_cli.commands.bridge as bridge_mod

    explicit = tmp_path / "explicit"
    (explicit / "apps" / "bridge-monitor" / "src" / "bridge_monitor").mkdir(parents=True)
    (explicit / "apps" / "bridge-monitor" / "src" / "bridge_monitor" / "admin.py").write_text("# stub\n")
    other = tmp_path / "other"
    (other / "apps" / "bridge-monitor" / "src" / "bridge_monitor").mkdir(parents=True)
    (other / "apps" / "bridge-monitor" / "src" / "bridge_monitor" / "admin.py").write_text("# stub\n")
    monkeypatch.chdir(other)
    monkeypatch.delenv("AITBC_REPO_ROOT", raising=False)
    assert bridge_mod._resolve_bridge_repo_root(str(explicit)) == explicit
