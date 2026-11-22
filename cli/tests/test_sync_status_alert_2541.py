"""#2541: `aitbc sync status --alert` must fail (exit 1) when the hub is
unreachable or not configured, and AHEAD_BY must honour --gap-threshold.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.sync import status as status_cmd
from aitbc_cli.utils.http_client import NetworkError

NODE = "http://node:8202"
HUB = "http://hub:8202"


class _FakeClient:
    hub_mode = "ok"  # "ok" | "unreachable"
    hub_height = 100

    def __init__(self, base_url, timeout=30, api_key=None):
        self.base_url = base_url

    def get(self, path, params=None):
        if self.base_url == HUB:
            if _FakeClient.hub_mode == "unreachable":
                raise NetworkError("connection refused")
            if path == "/rpc/head":
                return {"chain_id": "test", "height": _FakeClient.hub_height, "hash": "0xhub"}
            if path == "/rpc/network-info":
                return {"chain_id": "test"}
        if path == "/rpc/head":
            return {"chain_id": "test", "height": 100, "hash": "0xlocal"}
        if path == "/rpc/network-info":
            return {"chain_id": "test"}
        if path == "/rpc/sync/config":
            return {"error": "unsupported"}
        raise AssertionError(f"unexpected GET {path}")

    def close(self):
        pass


@pytest.fixture
def fake_client(monkeypatch):
    _FakeClient.hub_mode = "ok"
    _FakeClient.hub_height = 100
    monkeypatch.setattr("aitbc_cli.commands.sync.AITBCHTTPClient", _FakeClient)
    monkeypatch.delenv("HUB_RPC_URL", raising=False)
    return _FakeClient


def _invoke(*extra):
    return CliRunner().invoke(status_cmd, ["--node-url", NODE, *extra])


def test_alert_unreachable_hub_exits_1(fake_client):
    fake_client.hub_mode = "unreachable"
    r = _invoke("--hub-url", HUB, "--alert")
    assert r.exit_code == 1
    assert "HUB_UNREACHABLE" in r.output


def test_alert_missing_hub_exits_1(fake_client):
    r = _invoke("--alert")
    assert r.exit_code == 1


def test_alert_ahead_beyond_threshold_exits_1(fake_client):
    fake_client.hub_height = 90  # local is 10 ahead; default threshold is 5
    r = _invoke("--hub-url", HUB, "--alert")
    assert r.exit_code == 1
    assert "AHEAD_BY_10" in r.output


def test_alert_ahead_within_threshold_exits_0(fake_client):
    fake_client.hub_height = 97  # local is 3 ahead; inside the threshold of 5
    r = _invoke("--hub-url", HUB, "--alert")
    assert r.exit_code == 0, r.output
    assert "AHEAD_BY" not in r.output
