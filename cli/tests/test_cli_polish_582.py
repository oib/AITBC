"""CLI-POLISH-2 (#582): single error line on refund abort; no daemon traceback."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import click
import pytest

from aitbc_cli.commands.market import escrow as esc_mod
from aitbc_cli.utils.wallet_daemon_client import WalletDaemonClient


def _ctx():
    return click.Context(esc_mod.escrow_refund, obj={"output_format": "table"})


def test_refund_failure_prints_one_error_line(monkeypatch, capsys):
    """A refused refund prints the named failure once — no empty second line."""
    monkeypatch.setattr(esc_mod, "get_config", lambda: MagicMock())
    monkeypatch.setattr(esc_mod, "_coordinator_refund", lambda *a, **kw: None)
    monkeypatch.setattr(esc_mod, "_post_escrow_rpc", lambda *a, **kw: (None, ["hub: HTTP 503 settlement refused"]))
    with pytest.raises(click.Abort):
        esc_mod.refund_escrow(_ctx(), "job-x", "r")
    out = capsys.readouterr().out
    assert "Failed to refund escrow for job job-x" in out
    assert "Error refunding escrow" not in out, out


def test_daemon_unavailable_warns_without_traceback(caplog):
    """Daemon-down logs one short warning; the traceback stays at debug."""
    client = WalletDaemonClient(MagicMock(wallet_daemon_url="http://127.0.0.1:9", wallet_api_key=None))
    with patch.object(
        __import__("aitbc_cli.utils.wallet_daemon_client", fromlist=["AITBCHTTPClient"]).AITBCHTTPClient,
        "get",
        side_effect=__import__("aitbc_cli.utils.http_client", fromlist=["NetworkError"]).NetworkError("down"),
    ):
        with caplog.at_level(logging.WARNING):
            assert client.is_available() is False
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warns and "unavailable" in warns[0].getMessage()
    assert all(r.exc_info is None for r in warns), "traceback leaked at warning level"


def test_daemon_unavailable_traceback_kept_at_debug(caplog):
    client = WalletDaemonClient(MagicMock(wallet_daemon_url="http://127.0.0.1:9", wallet_api_key=None))
    with patch.object(
        __import__("aitbc_cli.utils.wallet_daemon_client", fromlist=["AITBCHTTPClient"]).AITBCHTTPClient,
        "get",
        side_effect=__import__("aitbc_cli.utils.http_client", fromlist=["NetworkError"]).NetworkError("down"),
    ):
        with caplog.at_level(logging.DEBUG):
            assert client.is_available() is False
    assert any(r.exc_info is not None for r in caplog.records if r.levelno <= logging.DEBUG)


def test_monitor_metrics_offline_fallback_warns(monkeypatch):
    """Unreachable monitoring service -> warning shown, rc 0, offline data."""
    from click.testing import CliRunner

    from aitbc_cli.commands import monitor as mon_mod
    from aitbc_cli.utils.http_client import NetworkError

    class _BadClient:
        def get(self, path):
            raise NetworkError("connection refused")

    monkeypatch.setattr(mon_mod, "_monitoring_client", lambda *a, **kw: _BadClient())
    result = CliRunner().invoke(mon_mod.metrics, [], obj={"output_format": "table"})
    assert result.exit_code == 0
    assert "Coordinator metrics unavailable" in result.output
    assert "offline" in result.output
