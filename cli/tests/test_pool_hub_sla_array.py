"""CLI-ARRAY-SWEEP-1 (#552): `aitbc pool-hub sla --violations` and
`aitbc pool-hub sla --miner <id>` must render the JSON arrays returned by
/v1/sla/violations and /v1/sla/metrics/{miner_id}.

Both pool-hub SLA routes declare ``response_model=list[...]`` — bare JSON
arrays, confirmed live on hub ("returned a JSON array, not an object").
``AITBCHTTPClient.get()`` narrows the body through ``expect_object`` and
raises TypeError on arrays, so both command paths abort (same class as
#490 / #529 / #543). They must use ``get_json()`` and pass either shape
through to the output renderer.
"""

import json

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.pool_hub as pool_hub_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.pool_hub import pool_hub

_VIOLATIONS = [
    {"violation_id": "v-1", "miner_id": "miner-a", "resolved": False},
    {"violation_id": "v-2", "miner_id": "miner-b", "resolved": False},
]

_METRICS = [
    {"miner_id": "miner-a", "uptime_pct": 99.5, "hour": "2026-10-26T10:00"},
    {"miner_id": "miner-a", "uptime_pct": 99.9, "hour": "2026-10-26T11:00"},
]


class _ArrayClient:
    """Mimics AITBCHTTPClient: get() narrows to object via expect_object."""

    def __init__(self, payload):
        self._payload = payload

    def get(self, path, params=None):
        if isinstance(self._payload, dict):
            return self._payload
        raise TypeError(f"Expected JSON object from http://poolhub{path}, got list")

    def get_json(self, path, params=None):
        return self._payload

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


def _patch(monkeypatch, client):
    monkeypatch.setattr(pool_hub_mod, "AITBCHTTPClient", lambda *a, **kw: client)


def test_sla_violations_array_json_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_VIOLATIONS))
    result = runner.invoke(
        pool_hub,
        ["sla", "--violations", "--pool-hub-url", "http://poolhub"],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert [row["violation_id"] for row in payload] == ["v-1", "v-2"]


def test_sla_violations_array_table_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_VIOLATIONS))
    result = runner.invoke(
        pool_hub, ["sla", "--violations", "--pool-hub-url", "http://poolhub"], obj={"output_format": "table"}
    )
    assert result.exit_code == 0, result.output
    assert "v-1" in result.output
    assert "miner-a" in result.output


def test_sla_miner_metrics_array(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_METRICS))
    result = runner.invoke(
        pool_hub,
        ["sla", "--miner", "miner-a", "--pool-hub-url", "http://poolhub"],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert len(payload) == 2


def test_sla_status_object_still_works(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient({"miners": 3, "healthy": True}))
    result = runner.invoke(pool_hub, ["sla", "--pool-hub-url", "http://poolhub"], obj={"output_format": "table"})
    assert result.exit_code == 0, result.output


def test_sla_network_error_still_aborts(runner, monkeypatch):
    _patch(monkeypatch, _FailingClient())
    result = runner.invoke(
        pool_hub, ["sla", "--violations", "--pool-hub-url", "http://poolhub"], obj={"output_format": "table"}
    )
    assert result.exit_code != 0
    assert "Pool Hub" in result.output
