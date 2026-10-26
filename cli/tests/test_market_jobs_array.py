"""CLI-MARKET-JOBS-ARRAY-1 (#490): `aitbc market jobs` must render the JSON
array returned by GET /v1/market/jobs.

The market service answers a bare JSON array for the jobs listing;
`AITBCHTTPClient.get()` narrows the body through `expect_object` and raises
TypeError on arrays, so every `aitbc market jobs` invocation tracebacks with
rc=1. The command must use `get_json()` and hand the array to `output()`,
which renders flat dict rows as a table (or the requested format).
"""

import json

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.market.host as host_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.market import market

_JOBS = [
    {"job_id": "job-1", "state": "active", "service_type": "ipfs", "amount": "5"},
    {"job_id": "job-2", "state": "completed", "service_type": "ipfs", "amount": "7"},
]


class _ArrayClient:
    """Mimics AITBCHTTPClient: get() narrows to object via expect_object."""

    def get(self, path, params=None):
        raise TypeError(f"Expected JSON object from http://hub{path}, got list")

    def get_json(self, path, params=None):
        return _JOBS

    def close(self):
        pass


class _FailingClient:
    def get_json(self, path, params=None):
        raise NetworkError("connection refused")

    def close(self):
        pass


@pytest.fixture
def runner():
    return CliRunner()


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(host_mod, "_hub_market_client", lambda *a, **kw: client)


def test_market_jobs_array_json_output(runner, monkeypatch):
    _patch_client(monkeypatch, _ArrayClient())
    result = runner.invoke(market, ["jobs", "--output", "json"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert [row["job_id"] for row in payload] == ["job-1", "job-2"]


def test_market_jobs_array_table_output(runner, monkeypatch):
    _patch_client(monkeypatch, _ArrayClient())
    result = runner.invoke(market, ["jobs"], obj={})
    assert result.exit_code == 0, result.output
    assert "job-1" in result.output
    assert "job-2" in result.output
    assert "Market Jobs" in result.output


def test_market_jobs_network_error_still_aborts(runner, monkeypatch):
    _patch_client(monkeypatch, _FailingClient())
    result = runner.invoke(market, ["jobs"], obj={})
    assert result.exit_code != 0
    assert "Could not list market jobs" in result.output
