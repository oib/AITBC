"""#2994: ``bridge oracle-status`` names the exception class when the
underlying httpx error stringifies to "" (ReadTimeout/ConnectError),
instead of printing a bare "Failed to get bridge oracle status: "."""

from __future__ import annotations

from unittest import mock

import httpx
import pytest
from click.testing import CliRunner

from aitbc_cli.commands import bridge as bridge_pkg
from aitbc_cli.commands.bridge._service import oracle_status


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _failing_client(exc: Exception) -> mock.Mock:
    client = mock.Mock()
    client.__aenter__ = mock.AsyncMock(return_value=client)
    client.__aexit__ = mock.AsyncMock(return_value=None)
    client.oracle_status = mock.AsyncMock(side_effect=exc)
    return client


def test_oracle_status_empty_error_names_exception_class(runner):
    client = _failing_client(httpx.ReadTimeout(""))
    with mock.patch.object(bridge_pkg, "_get_bridge_client", return_value=client):
        result = runner.invoke(oracle_status, args=["--rpc-url", "http://node:8202/rpc"])
    assert result.exit_code != 0
    assert "ReadTimeout" in result.output
    assert "Failed to get bridge oracle status: ReadTimeout" in result.output


def test_oracle_status_http_status_error_keeps_detail(runner):
    request = httpx.Request("GET", "http://node:8202/rpc/bridge/oracle/status")
    response = httpx.Response(503, request=request, json={"detail": "bridge module not available"})
    client = _failing_client(httpx.HTTPStatusError("Server error", request=request, response=response))
    with mock.patch.object(bridge_pkg, "_get_bridge_client", return_value=client):
        result = runner.invoke(oracle_status, args=["--rpc-url", "http://node:8202/rpc"])
    assert result.exit_code != 0
    assert "Server error" in result.output
    assert "bridge module not available" in result.output
