"""CLI-EXIT-1: commands that print an error must exit non-zero (SP-13).

44+ replayed read-only commands exited 0 while printing an error — scripted
plays and the MCP result field cannot tell failure from success. The failure
paths now route through ``abort()`` instead of ``error()``-then-return.

Two layers: stubbed invocations asserting a non-zero exit for each command
group, and an AST guard pinning each converted message to an ``abort`` call
so the pattern cannot silently regress to ``error`` + ``return``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import agent as agent_mod
from aitbc_cli.commands import cross_chain as cross_mod
from aitbc_cli.commands import explorer as explorer_mod
from aitbc_cli.commands import governance as gov_mod
from aitbc_cli.commands import gpu_market as gpumkt_mod
from aitbc_cli.commands import monitor as monitor_mod
from aitbc_cli.commands import transactions as tx_mod
from aitbc_cli.commands.wallet import basic as wallet_basic
from aitbc_cli.utils.http_client import NetworkError


@pytest.fixture
def runner():
    return CliRunner()


class _NetBoom:
    """HTTP client stub that always raises NetworkError."""

    def __init__(self, *a, **kw):
        pass

    def get(self, *a, **kw):
        raise NetworkError("GET request failed: fake connection refused")

    def get_json(self, *a, **kw):
        return self.get(*a, **kw)

    def post(self, *a, **kw):
        raise NetworkError("POST request failed: fake connection refused")

    def close(self):
        pass


def test_explorer_block_not_found_exits_nonzero(runner, monkeypatch):
    monkeypatch.setattr(explorer_mod, "get_explorer_client", lambda: _NetBoom())
    result = runner.invoke(explorer_mod.explorer, obj={"output_format": "table"}, args=["block", "--height", "128452"])
    assert result.exit_code != 0
    assert "Explorer API unavailable" in result.output


def test_explorer_transaction_unavailable_exits_nonzero(runner, monkeypatch):
    monkeypatch.setattr(explorer_mod, "get_explorer_client", lambda: _NetBoom())
    result = runner.invoke(explorer_mod.explorer, obj={"output_format": "table"}, args=["transaction", "--tx-hash", "0xdead"])
    assert result.exit_code != 0
    assert "Explorer API unavailable" in result.output


def test_governance_list_error_exits_nonzero(runner, monkeypatch):
    monkeypatch.setattr(gov_mod, "_get_client", lambda *a, **kw: _NetBoom())
    result = runner.invoke(gov_mod.governance, obj={"output_format": "table"}, args=["list"])
    assert result.exit_code != 0
    assert "Network error" in result.output


def test_governance_get_error_exits_nonzero(runner, monkeypatch):
    monkeypatch.setattr(gov_mod, "_get_client", lambda *a, **kw: _NetBoom())
    result = runner.invoke(gov_mod.governance, obj={"output_format": "table"}, args=["get", "--proposal-id", "prop-1"])
    assert result.exit_code != 0


def test_crosschain_status_error_exits_nonzero(runner, monkeypatch):
    monkeypatch.setattr(cross_mod, "AITBCHTTPClient", _NetBoom)
    monkeypatch.setattr(cross_mod, "_resolve_transaction_rpc_url", lambda *a: "http://127.0.0.1:8202")
    result = runner.invoke(cross_mod.cross_chain, obj={"output_format": "table"}, args=["status", "--swap-id", "sw_1"])
    assert result.exit_code != 0
    assert "Network error" in result.output


def test_crosschain_bridge_status_error_exits_nonzero(runner, monkeypatch):
    monkeypatch.setattr(cross_mod, "AITBCHTTPClient", _NetBoom)
    monkeypatch.setattr(cross_mod, "_resolve_transaction_rpc_url", lambda *a: "http://127.0.0.1:8202")
    result = runner.invoke(
        cross_mod.cross_chain, obj={"output_format": "table"}, args=["bridge-status", "--bridge-id", "0x9f"]
    )
    assert result.exit_code != 0


def test_transactions_status_error_exits_nonzero(runner, monkeypatch):
    monkeypatch.setattr(tx_mod, "AITBCHTTPClient", _NetBoom)
    result = runner.invoke(tx_mod.transactions, obj={"output_format": "table"}, args=["status", "--tx-hash", "0x" + "ab" * 32])
    assert result.exit_code != 0
    assert "Error getting transaction status" in result.output


def test_transactions_status_explorer_not_found_exits_nonzero(runner, monkeypatch):
    class _404(_NetBoom):
        def get(self, *a, **kw):
            raise NetworkError("GET request failed: 404 Client Error: Not Found")

    monkeypatch.setattr(tx_mod, "AITBCHTTPClient", _404)
    monkeypatch.setattr(tx_mod, "http_response_status", lambda e: 404)
    result = runner.invoke(
        tx_mod.transactions,
        obj={"output_format": "table"},
        args=["status", "--tx-hash", "0x" + "ab" * 32, "--use-explorer"],
    )
    assert result.exit_code != 0
    assert "not found" in result.output


def test_agent_msg_peers_error_exits_nonzero(runner, monkeypatch):
    monkeypatch.setattr(agent_mod, "AITBCHTTPClient", _NetBoom)
    result = runner.invoke(agent_mod.messaging, obj={"output_format": "table"}, args=["peers"])
    assert result.exit_code != 0
    assert "Network error" in result.output


def test_gpu_discover_error_exits_nonzero(runner, monkeypatch):
    monkeypatch.setattr(gpumkt_mod, "AITBCHTTPClient", _NetBoom)
    result = runner.invoke(gpumkt_mod.gpu, obj={"output_format": "table"}, args=["discover"])
    assert result.exit_code != 0
    assert "Network error" in result.output


def test_agent_discover_coordinator_down_exits_nonzero(runner, monkeypatch):
    import aitbc_cli.commands.agent_sdk as sdk_mod

    monkeypatch.setattr(sdk_mod, "_check_agent_coordinator", lambda url, ctx=None: sdk_mod.abort(ctx, "down"))
    result = runner.invoke(
        sdk_mod.discover, obj={"output_format": "table"}, args=["agents", "--coordinator-url", "http://x:1"]
    )
    assert result.exit_code != 0


def test_wallet_info_missing_exits_nonzero(runner, tmp_path):
    result = runner.invoke(
        wallet_basic.wallet,
        obj={
            "output_format": "table",
            "wallet_name": "ghost",
            "wallet_dir": tmp_path,
            "wallet_sign_path": tmp_path / "ghost.json",
        },
        args=["info", "--name", "ghost"],
    )
    assert result.exit_code != 0
    assert "not found" in result.output


def test_wallet_transactions_missing_exits_nonzero(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(wallet_basic, "find_wallet_file", lambda name: None)
    result = runner.invoke(
        wallet_basic.wallet,
        obj={
            "output_format": "table",
            "wallet_name": "ghost",
            "wallet_dir": tmp_path,
            "wallet_sign_path": tmp_path / "ghost.json",
        },
        args=["transactions", "--name", "ghost"],
    )
    assert result.exit_code != 0


def test_coin_requests_show_missing_exits_nonzero(runner, monkeypatch):
    import aitbc_cli.commands.coin_requests as cr_mod

    class _Q:
        def filter(self, *a):
            return self

        def first(self):
            return None

    class _S:
        def query(self, *a):
            return _Q()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cr_mod, "init_db", lambda *a, **kw: None)
    monkeypatch.setattr(cr_mod, "get_db_session", lambda: _S())
    result = runner.invoke(cr_mod.coin_requests, obj={"output_format": "table"}, args=["show", "--request-id", "req-x"])
    assert result.exit_code != 0
    assert "not found" in result.output


class _CrQuery:
    def __init__(self, row=None):
        self._row = row

    def filter(self, *a):
        return self

    def first(self):
        return self._row


class _CrSession:
    """DB-session double returning a fixed first() row for coin_requests."""

    def __init__(self, row=None):
        self._q = _CrQuery(row)

    def query(self, *a):
        return self._q

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_coin_db(monkeypatch, cr_mod, row=None):
    monkeypatch.setattr(cr_mod, "init_db", lambda *a, **kw: None)
    monkeypatch.setattr(cr_mod, "get_db_session", lambda: _CrSession(row))


def test_coin_requests_request_no_wallet_exits_nonzero(runner, monkeypatch, tmp_path):
    """CLI-SWALLOW-SWEEP-1: `request` with no local wallet is a credential
    refusal on a write path — it must not exit 0."""
    import aitbc_cli.commands.coin_requests as cr_mod
    import aitbc_cli.utils.wallet_paths as wp

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(wp, "find_wallet_file", lambda name: None)
    _patch_coin_db(monkeypatch, cr_mod)
    result = runner.invoke(cr_mod.coin_requests, obj={"output_format": "table"}, args=["request", "--wallet", "ghost"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_coin_requests_request_no_api_key_exits_nonzero(runner, monkeypatch):
    """Registered path but no credential -> non-zero."""
    import aitbc_cli.commands.coin_requests as cr_mod

    monkeypatch.setattr(cr_mod, "_read_wallet_address", lambda ctx, w: "0x" + "ab" * 20)
    monkeypatch.setattr(cr_mod, "_agent_api_base", lambda: "http://hub:8107/api/v1/agent")
    for var in ("FOLLOWER_API_KEY", "COORDINATOR_API_KEY", "SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    _patch_coin_db(monkeypatch, cr_mod)
    result = runner.invoke(cr_mod.coin_requests, obj={"output_format": "table"}, args=["request", "--wallet", "w"])
    assert result.exit_code != 0
    assert "API key" in result.output


def test_coin_requests_request_pending_approval_exits_zero(runner, monkeypatch):
    """BY-DESIGN pin: a request registered with the hub but not auto-approved
    is a clean outcome — the command did its job, exit stays 0."""
    import aitbc_cli.commands.coin_requests as cr_mod

    monkeypatch.setattr(cr_mod, "_read_wallet_address", lambda ctx, w: "0x" + "ab" * 20)
    monkeypatch.setattr(cr_mod, "_agent_api_base", lambda: "http://hub:8107/api/v1/agent")
    monkeypatch.setenv("FOLLOWER_API_KEY", "k")
    monkeypatch.setattr(cr_mod, "_register_with_hub", lambda *a, **kw: False)
    _patch_coin_db(monkeypatch, cr_mod)
    result = runner.invoke(cr_mod.coin_requests, obj={"output_format": "table"}, args=["request", "--wallet", "w"])
    assert result.exit_code == 0, result.output


def test_coin_requests_request_no_wallet_json_one_document(runner, monkeypatch):
    """Under --output json the refusal emits exactly one JSON error document."""
    import json as _json

    import aitbc_cli.commands.coin_requests as cr_mod
    import aitbc_cli.utils.wallet_paths as wp

    monkeypatch.setattr(wp, "find_wallet_file", lambda name: None)
    _patch_coin_db(monkeypatch, cr_mod)
    result = runner.invoke(cr_mod.coin_requests, obj={"output_format": "json"}, args=["request", "--wallet", "ghost"])
    assert result.exit_code != 0
    doc = _json.loads(result.stdout)
    assert doc["error"]


def test_coin_requests_execute_no_credentials_exits_nonzero(runner, monkeypatch):
    """`execute` with no local genesis key and no API key must exit non-zero."""
    from types import SimpleNamespace

    import aitbc_cli.commands.coin_requests as cr_mod
    from aitbc.config import hub as hub_mod
    from aitbc.models import CoinRequestStatus

    req = SimpleNamespace(
        id="req-1",
        status=CoinRequestStatus.APPROVED,
        transaction_hash=None,
        sender="s",
        amount=1,
        wallet_address="0x" + "ab" * 20,
        recipient="r",
        approved_by="cli",
        audit_log="",
    )

    class _TxSvc:
        genesis_private_key = None

    monkeypatch.setattr(cr_mod, "TransactionService", lambda: _TxSvc())
    monkeypatch.setattr(hub_mod, "hub_agent_url", lambda: "http://hub:8107/api/v1/agent")
    for var in ("FOLLOWER_API_KEY", "COORDINATOR_API_KEY", "SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    _patch_coin_db(monkeypatch, cr_mod, row=req)
    result = runner.invoke(cr_mod.coin_requests, obj={"output_format": "table"}, args=["execute", "--request-id", "req-1"])
    assert result.exit_code != 0
    assert "API key" in result.output


def test_coin_requests_execute_uses_faucet_key(runner, monkeypatch):
    """FAUCET_* satisfies the local-key gate and takes precedence (#609)."""
    from types import SimpleNamespace

    import aitbc_cli.commands.coin_requests as cr_mod
    from aitbc.crypto.transaction_service import TransactionService
    from aitbc.models import CoinRequestStatus

    req = SimpleNamespace(
        id="req-1",
        status=CoinRequestStatus.APPROVED,
        transaction_hash=None,
        sender="s",
        amount=1,
        wallet_address="0x" + "ab" * 20,
        recipient="r",
        approved_by="cli",
        audit_log="",
    )

    class _EnvTxSvc(TransactionService):
        def get_balance(self, _addr):
            return 0

    monkeypatch.delenv("GENESIS_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GENESIS_ADDRESS", raising=False)
    monkeypatch.setenv("FAUCET_PRIVATE_KEY", "ab" * 32)
    monkeypatch.setenv("FAUCET_ADDRESS", "0x" + "cd" * 20)
    monkeypatch.setattr(cr_mod, "TransactionService", _EnvTxSvc)
    _patch_coin_db(monkeypatch, cr_mod, row=req)
    result = runner.invoke(cr_mod.coin_requests, obj={"output_format": "table"}, args=["execute", "--request-id", "req-1"])
    # cleared the key/address gates on FAUCET_* alone and reached the balance check
    assert "no API key" not in result.output
    assert "not configured" not in result.output
    assert "forwarding" not in result.output
    assert "Insufficient balance" in result.output


def test_coin_requests_reopen_unverifiable_exits_nonzero(runner, monkeypatch):
    """`reopen` refusing because the chain cannot confirm payment -> non-zero."""
    from types import SimpleNamespace

    import aitbc_cli.commands.coin_requests as cr_mod

    req = SimpleNamespace(id="req-1", transaction_hash="0x" + "cd" * 32, audit_log="")
    monkeypatch.setattr(cr_mod, "_chain_has_transaction", lambda *a, **kw: None)
    _patch_coin_db(monkeypatch, cr_mod, row=req)
    result = runner.invoke(
        cr_mod.coin_requests,
        obj={"output_format": "table"},
        args=["reopen", "--request-id", "req-1", "--rpc-url", "http://x:1"],
    )
    assert result.exit_code != 0
    assert "Refusing to reopen" in result.output


def test_coin_requests_list_invalid_status_exits_nonzero(runner, monkeypatch):
    import aitbc_cli.commands.coin_requests as cr_mod

    _patch_coin_db(monkeypatch, cr_mod)
    result = runner.invoke(cr_mod.coin_requests, obj={"output_format": "table"}, args=["list", "--status", "bogus"])
    assert result.exit_code != 0
    assert "Invalid status" in result.output


def test_monitor_alerts_test_webhook_fails_nonzero(runner, tmp_path, monkeypatch):
    alerts_dir = tmp_path / ".aitbc" / "alerts"
    alerts_dir.mkdir(parents=True)
    (alerts_dir / "alerts.json").write_text('[{"name": "miner-watch", "type": "t", "webhook": "http://x:9/"}]')
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(monitor_mod, "AITBCHTTPClient", _NetBoom)
    result = runner.invoke(
        monitor_mod.monitor, obj={"output_format": "table"}, args=["alerts", "test", "--name", "miner-watch"]
    )
    assert result.exit_code != 0
    assert "Webhook test failed" in result.output


# --- AST guard: converted messages must live inside abort() calls -----------


COMMANDS_DIR = Path(__file__).resolve().parent.parent / "aitbc_cli" / "commands"

GUARD = {
    "agent.py": ["No wallet directory found"],
    "chain.py": ["Error from /rpc/network-info"],
    "config.py": [],
    "agent_task.py": [],
    "auth.py": [],
    "control.py": [],
    "developer.py": [],
    "eth.py": [],
    "exchange/bridge.py": [],
    "exchange/payments.py": [],
    "exchange/trading.py": [],
    "exchange/wallet.py": [],
    "exchange_island.py": [],
    "grant.py": [],
    "market/__init__.py": [],
    "market/escrow.py": [],
    "market/payments.py": [],
    "market/ratings.py": [],
    "prometheus.py": [],
    "trade.py": [],
    "edge.py": ["not implemented", "Failed to sync", "Network error"],
    "energy.py": [],
    "genesis.py": [],
    "ipfs.py": ["Failed to send island IPFS"],
    "market/gpu.py": [],
    "market/offers.py": [],
    "mining.py": [],
    "operations.py": ["Job ID is required"],
    "system.py": ["Configuration file not found"],
    "update.py": ["not a git repository"],
    "wallet/bridge.py": [],
    "wallet/misc.py": ["Import file not found"],
    "wallet/multisig.py": ["Threshold"],
    "wallet/staking.py": ["Invalid sender address"],
    "workflow.py": ["Failed to start workflow"],
    "explorer.py": ["not found", "Explorer API unavailable", "Error getting"],
    "governance.py": ["Network error", "Error listing proposals", "Error getting proposal"],
    "cross_chain.py": ["Network error", "Swap failed", "Bridge failed", "Confirm failed"],
    "gpu_market.py": ["Network error", "Error discovering GPUs", "Error registering GPU"],
    "monitor.py": ["Alert name required", "Webhook test failed", "not found"],
    "transactions.py": ["Error getting transaction status"],
    "coin_requests.py": [
        "Invalid status",
        "no API key",
        "GENESIS_ADDRESS not configured",
        "Insufficient balance",
        "Refusing to reopen",
        "not found in the configured wallet directories",
    ],
}


def _error_calls_followed_by_return(tree):
    """Lines where ``error(...)`` is the last statement of a block or is
    immediately followed by a bare ``return`` — the swallowed-error shape."""
    bad = []

    def visit(stmts):
        for i, st in enumerate(stmts):
            if (
                isinstance(st, ast.Expr)
                and isinstance(st.value, ast.Call)
                and getattr(st.value.func, "id", "") == "error"
                and (i + 1 == len(stmts) or isinstance(stmts[i + 1], ast.Return))
            ):
                bad.append(st.lineno)
            for child in ast.iter_child_nodes(st):
                for attr in ("body", "orelse", "finalbody"):
                    if isinstance(getattr(child, attr, None), list):
                        visit(getattr(child, attr))
                for h in getattr(child, "handlers", []):
                    visit(h.body)

    visit(tree.body)
    return bad


@pytest.mark.parametrize("fname", sorted(GUARD))
def test_no_swallowed_error_returns(fname):
    tree = ast.parse((COMMANDS_DIR / fname).read_text())
    assert _error_calls_followed_by_return(tree) == []


def test_converted_messages_use_abort():
    """Each guarded file must route its failure messages through abort()."""
    for fname, needles in GUARD.items():
        tree = ast.parse((COMMANDS_DIR / fname).read_text())
        abort_args = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "abort" and len(n.args) > 1:
                abort_args.append(ast.dump(n.args[1]))
        joined = " ".join(abort_args)
        for needle in needles:
            assert needle in joined, f"{fname}: '{needle}' not inside an abort() call"


def test_edge_sync_db_501_exits_nonzero(runner, monkeypatch):
    """CLI-EXIT-2 follow-up: a 501 (unimplemented edge sync) must exit
    non-zero — the broad `except Exception` used to swallow the abort."""
    from aitbc_cli.commands import edge as edge_mod

    class _Resp:
        status_code = 501

        def json(self):
            return {"detail": "Edge database sync is not implemented"}

    class _Client:
        def post(self, path):
            return _Resp()

    monkeypatch.setattr(edge_mod, "get_edge_client", lambda: _Client())
    result = runner.invoke(edge_mod.database, obj={"output_format": "table"}, args=["sync-db", "--database-id", "db-1"])
    assert result.exit_code != 0
    assert "not implemented" in result.output
