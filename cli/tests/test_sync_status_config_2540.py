"""#2540: `aitbc sync status` must not abort 'Cannot connect to node' when
only the optional /rpc/sync/config call is refused — it degrades to no
optimisation info. head/network-info failures still abort.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.sync as sync_mod
from aitbc_cli.commands.sync import status as status_cmd
from aitbc_cli.utils.http_client import NetworkError

NODE = "http://node:8202"


class _FakeClient:
    config_mode = "ok"  # "ok" | "refused"
    head_mode = "ok"  # "ok" | "refused"

    def __init__(self, base_url, timeout=30, api_key=None):
        self.base_url = base_url

    def get(self, path, params=None):
        if path == "/rpc/sync/config":
            if _FakeClient.config_mode == "refused":
                raise NetworkError("HTTP 403 Forbidden")
            return {"error": "unsupported"}
        if path == "/rpc/head":
            if _FakeClient.head_mode == "refused":
                raise NetworkError("connection refused")
            return {"chain_id": "test", "height": 100, "hash": "0xlocal"}
        if path == "/rpc/network-info":
            return {"chain_id": "test"}
        raise AssertionError(f"unexpected GET {path}")

    def close(self):
        pass


@pytest.fixture
def fake(monkeypatch):
    _FakeClient.config_mode = "ok"
    _FakeClient.head_mode = "ok"
    monkeypatch.setattr(sync_mod, "AITBCHTTPClient", _FakeClient)
    monkeypatch.delenv("HUB_RPC_URL", raising=False)
    return _FakeClient


def _invoke():
    return CliRunner().invoke(status_cmd, ["--node-url", NODE])


def test_sync_config_refused_still_shows_status(fake):
    fake.config_mode = "refused"
    r = _invoke()
    assert r.exit_code == 0, r.output
    assert "100" in r.output  # head height rendered
    assert "Cannot connect" not in r.output


def test_head_refused_still_aborts(fake):
    fake.head_mode = "refused"
    r = _invoke()
    assert r.exit_code != 0
    assert "Cannot connect to node" in r.output
