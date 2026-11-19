"""`aitbc market gpu list` (#2271): render GET /v1/market/gpu/list.

The coordinator answers a bare JSON array of GPU registry rows; the
command must use ``AITBCHTTPClient.get_json()`` (object-narrowing
``get()`` would TypeError on the array), map ``--status`` onto the
``available=true|false`` query param, honour ``--json-output``, and
abort cleanly on a non-list response.
"""

import json

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.market.gpu as gpu_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.market import market

_GPUS = [
    {
        "id": "gpu-1",
        "model": "RTX-4090",
        "price_per_hour": "0.25",
        "status": "available",
        "region": "eu-west",
        "memory_gb": 24,
    },
    {
        "id": "gpu-2",
        "model": "A100-80GB",
        "price_per_hour": "1.50",
        "status": "booked",
        "region": "us-east",
        "memory_gb": 80,
    },
]


class _ListClient:
    """Captures params and returns a canned get_json() payload."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def get_json(self, path, params=None):
        self.calls.append((path, params))
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
    monkeypatch.setattr(gpu_mod, "AITBCHTTPClient", lambda *a, **kw: client)


def test_gpu_list_empty_registry(runner, monkeypatch):
    _patch(monkeypatch, _ListClient([]))
    result = runner.invoke(market, ["gpu", "list"], obj={})
    assert result.exit_code == 0, result.output
    assert "No GPUs in the coordinator registry" in result.output


def test_gpu_list_row_rendering(runner, monkeypatch):
    _patch(monkeypatch, _ListClient(_GPUS))
    result = runner.invoke(market, ["gpu", "list"], obj={})
    assert result.exit_code == 0, result.output
    assert "gpu-1" in result.output
    assert "RTX-4090" in result.output
    assert "0.25/h" in result.output
    assert "status=available" in result.output
    assert "region=eu-west" in result.output
    assert "mem=24GB" in result.output
    assert "2 GPU(s) listed" in result.output


def test_gpu_list_status_filter_maps_to_available_param(runner, monkeypatch):
    client = _ListClient([])
    _patch(monkeypatch, client)

    result = runner.invoke(market, ["gpu", "list", "--status", "available"], obj={})
    assert result.exit_code == 0, result.output
    assert client.calls[-1][1]["available"] == "true"

    result = runner.invoke(market, ["gpu", "list", "--status", "booked"], obj={})
    assert result.exit_code == 0, result.output
    assert client.calls[-1][1]["available"] == "false"

    # Default / "all" sends no available filter.
    result = runner.invoke(market, ["gpu", "list"], obj={})
    assert result.exit_code == 0, result.output
    assert "available" not in client.calls[-1][1]


def test_gpu_list_json_output(runner, monkeypatch):
    _patch(monkeypatch, _ListClient(_GPUS))
    result = runner.invoke(market, ["gpu", "list", "--json-output"], obj={})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert [row["id"] for row in payload] == ["gpu-1", "gpu-2"]


def test_gpu_list_non_list_response_aborts(runner, monkeypatch):
    _patch(monkeypatch, _ListClient({"gpus": _GPUS}))
    result = runner.invoke(market, ["gpu", "list"], obj={})
    assert result.exit_code != 0
    assert "Unexpected response shape" in result.output


def test_gpu_list_network_error_aborts(runner, monkeypatch):
    _patch(monkeypatch, _FailingClient())
    result = runner.invoke(market, ["gpu", "list"], obj={})
    assert result.exit_code != 0
    assert "Failed to list GPUs" in result.output
