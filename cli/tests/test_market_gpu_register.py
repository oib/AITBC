"""`aitbc market gpu register` (#2291): POST /v1/market/gpu/register."""

import json

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.market.gpu as gpu_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.market import market


class _Client:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.calls = result, exc, []

    def post(self, path, json=None):
        self.calls.append((path, json))
        if self.exc:
            raise self.exc
        return self.result

    def close(self):
        pass


def _run(monkeypatch, client, args):
    monkeypatch.setattr(gpu_mod, "AITBCHTTPClient", lambda *a, **k: client)
    monkeypatch.setattr(gpu_mod, "_auth_headers", lambda ctx: {})
    return CliRunner().invoke(market, ["gpu", "register", *args])


@pytest.mark.unit
def test_register_posts_specs(monkeypatch):
    c = _Client({"gpu_id": "gpu_ab12", "status": "registered", "already_registered": False})
    r = _run(
        monkeypatch,
        c,
        ["--name", "RTX 4060 Ti", "--memory-gb", "16", "--price-per-hour", "0.05", "--resource-id", "node2-rtx4060ti"],
    )
    assert r.exit_code == 0, r.output
    assert "gpu_ab12" in r.output
    path, body = c.calls[0]
    assert path == "/v1/market/gpu/register"
    assert body["gpu"]["name"] == "RTX 4060 Ti"
    assert body["gpu"]["price_per_hour"] == "0.05"
    assert body["gpu"]["resource_id"] == "node2-rtx4060ti"


@pytest.mark.unit
def test_register_reports_already_registered(monkeypatch):
    c = _Client({"gpu_id": "gpu_ab12", "already_registered": True})
    r = _run(monkeypatch, c, ["--name", "X", "--memory-gb", "8", "--price-per-hour", "1"])
    assert r.exit_code == 0
    assert "already registered" in r.output


@pytest.mark.unit
def test_register_json_output(monkeypatch):
    c = _Client({"gpu_id": "gpu_ab12"})
    r = _run(monkeypatch, c, ["--name", "X", "--memory-gb", "8", "--price-per-hour", "1", "--json-output"])
    assert r.exit_code == 0
    assert json.loads(r.output)["gpu_id"] == "gpu_ab12"


@pytest.mark.unit
@pytest.mark.parametrize("price", ["abc", "-1", "NaN", "Infinity"])
def test_register_rejects_bad_price_before_any_request(monkeypatch, price):
    c = _Client({"gpu_id": "x"})
    r = _run(monkeypatch, c, ["--name", "X", "--memory-gb", "8", "--price-per-hour", price])
    assert r.exit_code != 0
    assert c.calls == []


@pytest.mark.unit
def test_register_network_error_aborts(monkeypatch):
    c = _Client(exc=NetworkError("403 forbidden"))
    r = _run(monkeypatch, c, ["--name", "X", "--memory-gb", "8", "--price-per-hour", "1"])
    assert r.exit_code != 0
    assert "Failed to register GPU" in r.output
