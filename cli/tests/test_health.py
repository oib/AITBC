"""Unit tests for the aitbc health command."""

from __future__ import annotations

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


def test_health_command_registered_in_cli(runner):
    """`aitbc health --help` must be reachable from the top-level CLI."""
    from aitbc_cli.core.main import cli

    result = runner.invoke(cli, ["health", "--help"])
    assert result.exit_code == 0, result.output
    assert "--host" in result.output
    assert "--services" in result.output


def test_health_probes_requested_services(runner, monkeypatch):
    """The command probes only the services requested by --services."""
    from aitbc_cli.core.main import cli

    calls: list[str] = []

    def fake_probe(url, timeout):
        calls.append(url)
        return {
            "url": url,
            "status_code": 200,
            "status": "healthy",
            "latency_ms": 1.0,
            "error": None,
        }

    monkeypatch.setattr("aitbc_cli.commands.health._probe_url", fake_probe)

    result = runner.invoke(
        cli,
        ["health", "--host", "node2.aitbc.bubuit.net", "--services", "blockchain-rpc,edge"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0, result.output
    assert any("8202" in c for c in calls)
    assert any("8111" in c for c in calls)
    assert not any("8102" in c for c in calls)


def test_health_rejects_unknown_services(runner):
    """An unknown service name must cause a non-zero exit."""
    from aitbc_cli.core.main import cli

    result = runner.invoke(
        cli,
        ["health", "--host", "127.0.0.1", "--services", "does-not-exist"],
        obj={"output_format": "table"},
    )

    assert result.exit_code != 0
    assert "Unknown service" in (result.output + str(result.exception))


def test_health_accepts_full_url(runner, monkeypatch):
    """A full URL host must be probed directly."""
    from aitbc_cli.core.main import cli

    calls: list[str] = []

    def fake_probe(url, timeout):
        calls.append(url)
        return {
            "url": url,
            "status_code": 200,
            "status": "healthy",
            "latency_ms": 1.0,
            "error": None,
        }

    monkeypatch.setattr("aitbc_cli.commands.health._probe_url", fake_probe)

    result = runner.invoke(
        cli,
        ["health", "--host", "https://hub.aitbc.bubuit.net"],
        obj={"output_format": "table"},
    )

    assert result.exit_code == 0, result.output
    assert any("https://hub.aitbc.bubuit.net/health" in c for c in calls)
