"""CLI dispute reads print one clean line and exit non-zero on a 404 (RPC-DISPUTE-EVIDENCE-1).

Before this fix the rpc answered 500 for an unknown dispute id on the
evidence and votes routes; once the rpc answers 404 the CLI must not dump
the raw request error — it prints ``Dispute N not found`` and exits
non-zero via the shared abort path.
"""

import pytest
import requests
from click.testing import CliRunner

import aitbc_cli.commands.dispute as dispute_mod
from aitbc_cli.commands.dispute import dispute
from aitbc_cli.utils.http_client import NetworkError


@pytest.fixture
def runner():
    return CliRunner()


def _network_error(status_code: int) -> NetworkError:
    """Build the NetworkError AITBCHTTPClient raises for an HTTP error."""
    response = requests.models.Response()
    response.status_code = status_code
    response.url = "http://node.test/rpc/disputes/999999/evidence"
    http_error = requests.HTTPError(f"{status_code} Client Error", response=response)
    err = NetworkError(f"GET request failed: {http_error}")
    err.__cause__ = http_error
    return err


class _BoomClient:
    error: NetworkError

    def __init__(self, base_url, timeout=10, **kwargs):
        self.base_url = base_url

    def get(self, path, params=None):
        raise self.error

    def close(self):
        pass


def _stub_client(monkeypatch, error: NetworkError) -> None:
    class C(_BoomClient):
        pass

    C.error = error
    monkeypatch.setattr(dispute_mod, "AITBCHTTPClient", C)


@pytest.mark.parametrize("args", [["evidence", "list", "999999"], ["votes", "999999"]])
def test_unknown_dispute_prints_one_line(runner, monkeypatch, args):
    _stub_client(monkeypatch, _network_error(404))
    result = runner.invoke(dispute, obj={"output_format": "table"}, args=args)
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
    assert "999999" in result.output


@pytest.mark.parametrize("args", [["evidence", "list", "999999"], ["votes", "999999"]])
def test_non_404_keeps_rpc_error_line(runner, monkeypatch, args):
    _stub_client(monkeypatch, _network_error(500))
    result = runner.invoke(dispute, obj={"output_format": "table"}, args=args)
    assert result.exit_code != 0
    assert "Blockchain RPC error" in result.output
