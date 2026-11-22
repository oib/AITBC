"""AUDIT-NETWORKERROR-UNREACHABLE-1 (#2585): pool-hub ``status``/``sla`` and
``performance benchmark`` reported ANY ``NetworkError`` — including a real
HTTP 4xx/5xx answer — as "unreachable". The handlers must split the two:

- server answered (status recoverable from the exception chain, or the
  "NNN Client/Server Error" text a RetryError keeps after 5xx retries) →
  message names the status;
- genuine transport failure (no response anywhere) → still "unreachable".
"""

import pytest
import requests
from click.testing import CliRunner

import aitbc_cli.commands.pool_hub as pool_hub_mod
import aitbc_cli.utils.http_client as http_client_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.performance import performance
from aitbc_cli.commands.pool_hub import pool_hub


class _Resp:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def json(self):
        return {"detail": f"status {self.status_code}"}


def _answered_error(status: int) -> NetworkError:
    """NetworkError wrapping an HTTPError carrying a real response (4xx path)."""
    http_err = requests.HTTPError(f"{status} Client Error for url: http://x/y")
    http_err.response = _Resp(status)
    try:
        raise NetworkError(f"GET request failed: {status} Client Error for url: http://x/y") from http_err
    except NetworkError as e:
        return e


def _retried_5xx_error() -> NetworkError:
    """5xx after retries: RetryError drops the response, only text survives."""
    return NetworkError("GET request failed: Request failed: 503 Server Error: Service Unavailable for url: http://x/y")


class _RefusingClient:
    """First call raises the given error; records nothing else."""

    def __init__(self, exc: Exception):
        self._exc = exc

    def get(self, path, params=None):
        raise self._exc

    def get_json(self, path, params=None):
        raise self._exc

    def close(self):
        pass


@pytest.fixture
def runner():
    return CliRunner()


def _patch_pool_hub(monkeypatch, client):
    monkeypatch.setattr(pool_hub_mod, "AITBCHTTPClient", lambda *a, **kw: client)


def _patch_rpc(monkeypatch, client):
    monkeypatch.setattr(http_client_mod, "AITBCHTTPClient", lambda *a, **kw: client)


@pytest.mark.parametrize("status", [403, 404])
@pytest.mark.parametrize("sub", ["status", "sla"])
def test_pool_hub_http_status_names_status(runner, monkeypatch, sub, status):
    _patch_pool_hub(monkeypatch, _RefusingClient(_answered_error(status)))
    result = runner.invoke(pool_hub, [sub, "--pool-hub-url", "http://poolhub"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert f"answered HTTP {status}" in result.output
    assert "unreachable" not in result.output


@pytest.mark.parametrize("status", [403, 404])
def test_performance_benchmark_http_status_names_status(runner, monkeypatch, status):
    _patch_rpc(monkeypatch, _RefusingClient(_answered_error(status)))
    result = runner.invoke(performance, ["benchmark", "--rpc-url", "http://rpc"])
    assert result.exit_code != 0
    assert f"answered HTTP {status}" in result.output
    assert "unreachable" not in result.output


@pytest.mark.parametrize("sub", ["status", "sla"])
def test_pool_hub_transport_failure_still_unreachable(runner, monkeypatch, sub):
    _patch_pool_hub(monkeypatch, _RefusingClient(NetworkError("Connection refused")))
    result = runner.invoke(pool_hub, [sub, "--pool-hub-url", "http://poolhub"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "unreachable" in result.output


def test_performance_benchmark_transport_failure_still_unreachable(runner, monkeypatch):
    _patch_rpc(monkeypatch, _RefusingClient(NetworkError("Connection refused")))
    result = runner.invoke(performance, ["benchmark", "--rpc-url", "http://rpc"])
    assert result.exit_code != 0
    assert "unreachable" in result.output


def test_pool_hub_status_5xx_retry_error_names_status(runner, monkeypatch):
    """A 5xx that exhausted retries keeps only message text — still named."""
    _patch_pool_hub(monkeypatch, _RefusingClient(_retried_5xx_error()))
    result = runner.invoke(pool_hub, ["status", "--pool-hub-url", "http://poolhub"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "answered HTTP 503" in result.output
    assert "unreachable" not in result.output
