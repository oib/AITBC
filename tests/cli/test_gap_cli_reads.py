"""GAP-CLI-READS-1 — read-path fixes found by RESET-DRAIN-1 Phase 0.

Covers: the generic ``http call`` GET accepting JSON arrays, the MCP
``call_aitbc_http`` ``rpc``/``trading`` auth modes, ``market escrow status``
surfacing HTTP errors instead of a fake "No escrow found", the
``coin-requests --db`` ledger override, ``market payment``, ``exchange order
book``, and ``bridge deposits``.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

MCP_SERVER_DIR = Path(__file__).resolve().parents[2] / "mcp-server"


@pytest.fixture
def runner():
    return CliRunner()


class TestHttpCallArrayResponse:
    """aitbc http call <svc> <path> must not crash on a JSON array body.

    bridge/pending is the reported case: it returns ``[]``, and ``client.get``
    raises TypeError via expect_object. The fix routes GET through get_json,
    which accepts either shape (GAP-CLI-READS-1).
    """

    @patch("aitbc_cli.commands.http.AITBCHTTPClient")
    @patch("aitbc_cli.commands.http.get_config")
    def test_get_array_body_prints_without_error(self, mock_get_config, mock_http_class, runner):
        from aitbc_cli.commands.http import http

        mock_get_config.return_value = SimpleNamespace(api_key=None)
        client = mock_http_class.return_value
        client.get_json.return_value = [{"transfer_id": "t-1"}, {"transfer_id": "t-2"}]

        result = runner.invoke(http, ["call", "blockchain-rpc", "bridge/pending"])

        assert result.exit_code == 0, result.output
        client.get_json.assert_called_once_with("bridge/pending", params=None)
        assert "t-1" in result.output

    @patch("aitbc_cli.commands.http.AITBCHTTPClient")
    @patch("aitbc_cli.commands.http.get_config")
    def test_get_object_body_still_works(self, mock_get_config, mock_http_class, runner):
        from aitbc_cli.commands.http import http

        mock_get_config.return_value = SimpleNamespace(api_key=None)
        client = mock_http_class.return_value
        client.get_json.return_value = {"height": 5}

        result = runner.invoke(http, ["call", "blockchain-rpc", "height"])

        assert result.exit_code == 0, result.output
        assert "height" in result.output or "5" in result.output


class TestMcpHttpAuthModes:
    """call_aitbc_http accepts rpc/trading auth and forwards --auth to the CLI."""

    def _call(self, **overrides):
        if str(MCP_SERVER_DIR) not in sys.path:
            sys.path.insert(0, str(MCP_SERVER_DIR))
        import aitbc_mcp_server as srv

        kwargs = {
            "service": "blockchain-rpc",
            "path": "escrow/job-1",
            "method": "GET",
            "params": None,
            "body": None,
            "auth": "none",
            "auth_env": "/etc/aitbc/aitbc-coordinator-api.env",
            "role": None,
            "host": "node9.test",
            "dry_run": True,
            "confirm": False,
            "expect_status": None,
            "timeout": 30,
        }
        kwargs.update(overrides)
        return srv.call_aitbc_http(**kwargs)

    def test_auth_rpc_builds_auth_flag(self):
        out = self._call(auth="rpc")
        assert "--auth rpc" in out or "--auth=rpc" in out

    def test_auth_trading_builds_auth_flag(self):
        out = self._call(auth="trading")
        assert "--auth trading" in out or "--auth=trading" in out

    def test_auth_miner_still_works(self):
        out = self._call(auth="miner")
        assert "--auth miner" in out or "--auth=miner" in out


class TestMarketEscrowStatusErrors:
    """market escrow status must name the real failure (403 auth, 5xx) — the
    old code folded every error into 'No escrow found', hiding the API-key
    requirement (GAP-CLI-READS-1). Only a true 404 keeps that message."""

    def _invoke(self, runner, exc):
        from aitbc_cli.commands.market.escrow import escrow

        with (
            patch("aitbc_cli.commands.market.escrow.get_config") as mock_cfg,
            patch("aitbc_cli.commands.market.escrow._get_rpc_client") as mock_client_fn,
        ):
            mock_cfg.return_value = SimpleNamespace(hub_discovery_url="http://hub.test", blockchain_rpc_api_key=None)
            mock_client_fn.return_value.get.side_effect = exc
            return runner.invoke(escrow, ["status", "--job-id", "job-1"], obj={})

    def test_403_names_the_auth_failure(self, runner):
        exc = Exception("forbidden")
        exc.response = SimpleNamespace(status_code=403, json=lambda: {"detail": "Missing API key"})
        result = self._invoke(runner, exc)
        assert "HTTP 403" in result.output
        assert "No escrow found" not in result.output

    def test_404_reports_no_escrow(self, runner):
        exc = Exception("not found")
        exc.response = SimpleNamespace(status_code=404, json=lambda: {"detail": "no escrow"})
        result = self._invoke(runner, exc)
        assert "No escrow found for job job-1" in result.output


class TestMarketPayment:
    """aitbc market payment reads /v1/jobs/{id}/payment (or /v1/payments/{id})."""

    def test_job_payment_path_and_bearer(self, runner):
        from aitbc_cli.commands.market import market

        with (
            patch("aitbc_cli.commands.market.payments._client_token", return_value="tok-1"),
            patch("aitbc_cli.commands.market.payments._coordinator_base_url", return_value="http://coord.test"),
            patch("aitbc_cli.commands.market.payments.AITBCHTTPClient") as mock_client_cls,
        ):
            client = mock_client_cls.return_value
            client.get.return_value = {"job_id": "job-1", "status": "released"}
            result = runner.invoke(market, ["payment", "--job-id", "job-1"], obj={})

        assert result.exit_code == 0, result.output
        kwargs = mock_client_cls.call_args.kwargs
        assert kwargs["headers"] == {"Authorization": "Bearer tok-1"}
        client.get.assert_called_once_with("/v1/jobs/job-1/payment")

    def test_payment_id_path(self, runner):
        from aitbc_cli.commands.market import market

        with (
            patch("aitbc_cli.commands.market.payments._client_token", return_value="tok-1"),
            patch("aitbc_cli.commands.market.payments._coordinator_base_url", return_value="http://coord.test"),
            patch("aitbc_cli.commands.market.payments.AITBCHTTPClient") as mock_client_cls,
        ):
            client = mock_client_cls.return_value
            client.get.return_value = {"payment_id": "pay-9"}
            result = runner.invoke(market, ["payment", "--payment-id", "pay-9"], obj={})

        assert result.exit_code == 0, result.output
        client.get.assert_called_once_with("/v1/payments/pay-9")

    def test_exactly_one_selector_required(self, runner):
        from aitbc_cli.commands.market import market

        result = runner.invoke(market, ["payment", "--job-id", "j", "--payment-id", "p"], obj={})
        assert result.exit_code != 0
        assert "exactly one" in result.output


class TestExchangeOrderBook:
    """aitbc exchange order book reads /api/orders/orderbook — public, no wallet."""

    def test_book_calls_orderbook_endpoint(self, runner):
        from aitbc_cli.commands.exchange.hub_orders import order

        with patch("aitbc_cli.commands.exchange.hub_orders._exchange_client") as mock_client_fn:
            mock_client_fn.return_value.get.return_value = {"bids": [], "asks": []}
            result = runner.invoke(order, ["book"], obj={})

        assert result.exit_code == 0, result.output
        mock_client_fn.return_value.get.assert_called_once_with("/api/orders/orderbook")


class TestCoinRequestsDbOption:
    """coin-requests --db PATH selects the ledger file before init_db()."""

    @patch("aitbc_cli.commands.coin_requests.init_db")
    @patch("aitbc_cli.commands.coin_requests.get_db_session")
    def test_db_option_sets_agent_db_path(self, mock_session_fn, mock_init, runner, tmp_path):
        saved = os.environ.pop("AGENT_DB_PATH", None)
        try:
            db_file = tmp_path / "alt-ledger.db"
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.order_by.return_value.all.return_value = []
            mock_session.query.return_value = mock_query
            mock_session_fn.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_fn.return_value.__exit__ = MagicMock(return_value=None)

            from aitbc_cli.commands.coin_requests import coin_requests

            result = runner.invoke(coin_requests, ["--db", str(db_file), "list"])

            assert result.exit_code == 0, result.output
            assert os.environ["AGENT_DB_PATH"] == str(db_file)
            # The cached engine must have been dropped so the new path wins.
            from aitbc.db import agent_db

            assert agent_db._engine is None
        finally:
            os.environ.pop("AGENT_DB_PATH", None)
            if saved is not None:
                os.environ["AGENT_DB_PATH"] = saved


class TestBridgeDeposits:
    """aitbc bridge deposits shells `python -m bridge_monitor.admin list`."""

    def _repo(self, tmp_path):
        admin = tmp_path / "apps" / "bridge-monitor" / "src" / "bridge_monitor"
        admin.mkdir(parents=True)
        (admin / "admin.py").write_text("# stub\n")
        return tmp_path

    def test_list_invocation(self, runner, tmp_path):
        from aitbc_cli.commands.bridge import bridge

        repo = self._repo(tmp_path)
        with patch("aitbc_cli.commands.bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="row1\n", stderr="")
            result = runner.invoke(
                bridge, ["deposits", "--repo-root", str(repo), "--status", "funding", "--limit", "5"], obj={}
            )

        assert result.exit_code == 0, result.output
        assert "row1" in result.output
        argv = mock_run.call_args.args[0]
        assert argv[1:] == ["-m", "bridge_monitor.admin", "list", "--limit", "5", "--status", "funding"]
        env = mock_run.call_args.kwargs["env"]
        assert "bridge-monitor/src" in env["PYTHONPATH"]

    def test_status_by_tx_hash(self, runner, tmp_path):
        from aitbc_cli.commands.bridge import bridge

        repo = self._repo(tmp_path)
        with patch("aitbc_cli.commands.bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="eth_tx_hash: 0xabc\n", stderr="")
            result = runner.invoke(bridge, ["deposits", "--repo-root", str(repo), "--tx-hash", "0xabc"], obj={})

        assert result.exit_code == 0, result.output
        argv = mock_run.call_args.args[0]
        assert argv[1:] == ["-m", "bridge_monitor.admin", "status", "0xabc"]

    def test_missing_monitor_sources_aborts(self, runner, tmp_path):
        from aitbc_cli.commands.bridge import bridge

        result = runner.invoke(bridge, ["deposits", "--repo-root", str(tmp_path)], obj={})
        assert result.exit_code != 0
        assert "bridge-monitor" in result.output
