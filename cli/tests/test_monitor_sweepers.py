"""Tests for ``aitbc monitor sweepers``.

The command's job is to make one distinction loud: a sweeper that is enabled
but not running. Everything else is presentation, so that distinction and the
non-zero exit that goes with it are what these cover.
"""

from __future__ import annotations

import json
from typing import Any

from click.testing import CliRunner

from aitbc_cli.commands import monitor as monitor_mod
from aitbc_cli.core.main import cli

REPORT: dict[str, Any] = {
    "process": "coordinator-api",
    "sweepers": [
        {
            "name": "zk_refund_sweeper",
            "purpose": "Refund escrow for unverifiable ZK receipts",
            "enabled": True,
            "status": "running",
            "healthy": True,
            "config": {"interval_seconds": 60, "batch_size": 25},
        },
        {
            "name": "stuck_escrow_sweeper",
            "purpose": "Refund escrow stuck in terminal states",
            "enabled": True,
            "status": "error: OperationalError",
            "healthy": False,
            "config": {"interval_seconds": 300, "batch_size": 25},
        },
        {
            "name": "escrow_settlement_reconciler",
            "purpose": "Re-drive unsettled releases",
            "enabled": False,
            "status": "disabled",
            "healthy": True,
            "config": {"interval_seconds": 300},
        },
    ],
    "degraded": ["stuck_escrow_sweeper"],
    "other_tasks": [{"name": "metrics_flusher", "status": "running"}],
    "external_sweepers": [
        {
            "name": "ipfs_rental_sweeper",
            "process": "marketplace-service",
            "purpose": "Expire IPFS rentals past their grace period",
            "status": "not visible from this process",
        }
    ],
    "checked_at": "2026-09-09T00:00:00+00:00",
}


def _run(monkeypatch, *args, report=REPORT):
    monkeypatch.setattr(monitor_mod.AITBCHTTPClient, "get", lambda self, endpoint, **kw: report, raising=True)
    return CliRunner().invoke(cli, [*args])


def test_json_output_passes_the_report_through_unchanged(monkeypatch):
    result = _run(monkeypatch, "--output", "json", "monitor", "sweepers")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == REPORT


def test_a_degraded_sweeper_is_named_in_the_output(monkeypatch):
    result = _run(monkeypatch, "monitor", "sweepers")
    assert result.exit_code == 0, result.output
    assert "stuck_escrow_sweeper" in result.output
    # The disabled reconciler must not be reported as a fault.
    assert "escrow_settlement_reconciler" in result.output


def test_a_healthy_fleet_says_so(monkeypatch):
    healthy = dict(REPORT)
    healthy["sweepers"] = [entry for entry in REPORT["sweepers"] if entry["healthy"]]
    healthy["degraded"] = []
    result = _run(monkeypatch, "monitor", "sweepers", report=healthy)
    assert result.exit_code == 0, result.output
    assert "running" in result.output


def test_config_is_hidden_until_asked_for(monkeypatch):
    without = _run(monkeypatch, "monitor", "sweepers")
    with_config = _run(monkeypatch, "monitor", "sweepers", "--config")
    assert "interval_seconds" not in without.output
    assert "interval_seconds" in with_config.output


def test_a_failed_request_exits_non_zero(monkeypatch):
    def _boom(self, endpoint, **kw):
        raise ConnectionError("coordinator unreachable")

    monkeypatch.setattr(monitor_mod.AITBCHTTPClient, "get", _boom, raising=True)
    result = CliRunner().invoke(cli, ["monitor", "sweepers"])
    assert result.exit_code != 0


def test_a_jwt_credential_is_sent_as_a_bearer_token(monkeypatch):
    """/v1/admin rejects X-API-Key, so the admin client must send Bearer."""
    monkeypatch.setattr(monitor_mod.AuthManager, "get_credential", lambda self, name, quiet=False: "ey.header.sig")
    captured = {}

    class _Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def get(self, endpoint, **kw):
            return REPORT

    monkeypatch.setattr(monitor_mod, "AITBCHTTPClient", _Client)
    result = CliRunner().invoke(cli, ["monitor", "sweepers"])

    assert result.exit_code == 0, result.output
    assert captured["headers"] == {"Authorization": "Bearer ey.header.sig"}
    assert "api_key" not in captured


def test_a_non_jwt_credential_falls_back_to_the_api_key_header(monkeypatch):
    monkeypatch.setattr(monitor_mod.AuthManager, "get_credential", lambda self, name, quiet=False: "plain-key")
    captured = {}

    class _Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def get(self, endpoint, **kw):
            return REPORT

    monkeypatch.setattr(monitor_mod, "AITBCHTTPClient", _Client)
    result = CliRunner().invoke(cli, ["monitor", "sweepers"])

    assert result.exit_code == 0, result.output
    assert captured["api_key"] == "plain-key"
    assert "headers" not in captured


def test_a_missing_credential_does_not_corrupt_json_output(monkeypatch):
    """The credential store warns on stdout; probing for an optional admin
    credential must not put that warning in front of the JSON."""
    monkeypatch.setattr(monitor_mod.AuthManager, "get_credential", lambda self, name, quiet=False: None)
    monkeypatch.setattr(monitor_mod.AITBCHTTPClient, "get", lambda self, endpoint, **kw: REPORT, raising=True)

    result = CliRunner().invoke(cli, ["--output", "json", "monitor", "sweepers"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == REPORT
