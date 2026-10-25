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
    "explorer.py": ["not found", "Explorer API unavailable", "Error getting"],
    "governance.py": ["Network error", "Error listing proposals", "Error getting proposal"],
    "cross_chain.py": ["Network error", "Swap failed", "Bridge failed", "Confirm failed"],
    "gpu_market.py": ["Network error", "Error discovering GPUs", "Error registering GPU"],
    "monitor.py": ["Alert name required", "Webhook test failed", "not found"],
    "transactions.py": ["Error getting transaction status"],
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
