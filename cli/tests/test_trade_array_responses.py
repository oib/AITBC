"""CLI-TRADE-ARRAY-1 (#529): six `aitbc trade` list commands must render the
bare JSON arrays returned by the trading service.

`chains`, `list`, `history`, `search`, `sync-status` and
`subscription-status` call endpoints that answer a bare JSON array, but the
commands used `AITBCHTTPClient.get()`, which narrows the body through
`expect_object` and raises TypeError on arrays — every invocation aborts.
Same defect class as #490 (`market jobs`): the commands must use
`get_json()` and handle both array and object shapes.
"""

import json

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.trade as trade_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.trade import trade

_ARRAY = [
    {"id": "row-1", "status": "active"},
    {"id": "row-2", "status": "completed"},
]
_OBJECT = {"rows": [{"id": "row-3", "status": "pending"}]}


class _ArrayThenObjectClient:
    """Mimics AITBCHTTPClient: get() narrows to object via expect_object.

    Alternates between an array and an object payload so each command is
    exercised against both shapes.
    """

    def __init__(self):
        self._payloads = [_ARRAY, _OBJECT]
        self.calls = 0

    def get(self, path, params=None):
        raise TypeError(f"Expected JSON object from http://hub{path}, got list")

    def get_json(self, path, params=None):
        payload = self._payloads[self.calls % len(self._payloads)]
        self.calls += 1
        return payload

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
    monkeypatch.setattr(trade_mod, "_get_client", lambda *a, **kw: client)


_COMMANDS = ["chains", "list", "history", "search", "sync-status", "subscription-status"]


@pytest.mark.parametrize("command", _COMMANDS)
def test_trade_command_array_shape(runner, monkeypatch, command):
    _patch_client(monkeypatch, _ArrayThenObjectClient())
    result = runner.invoke(trade, [command, "--format", "json"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert [row["id"] for row in payload] == ["row-1", "row-2"]


@pytest.mark.parametrize("command", _COMMANDS)
def test_trade_command_object_shape(runner, monkeypatch, command):
    client = _ArrayThenObjectClient()
    client.calls = 1  # force the object payload
    _patch_client(monkeypatch, client)
    result = runner.invoke(trade, [command, "--format", "json"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    assert "row-3" in result.output


@pytest.mark.parametrize("command", _COMMANDS)
def test_trade_command_table_output(runner, monkeypatch, command):
    _patch_client(monkeypatch, _ArrayThenObjectClient())
    result = runner.invoke(trade, [command], obj={})
    assert result.exit_code == 0, result.output
    assert "row-1" in result.output
    assert "row-2" in result.output


def test_trade_network_error_still_aborts(runner, monkeypatch):
    _patch_client(monkeypatch, _FailingClient())
    result = runner.invoke(trade, ["chains"], obj={})
    assert result.exit_code != 0
    assert "Error" in result.output or "error" in result.output


# --- Group-level --api-key (#2437) ---
#
# S77's bad-key 401 legs need a deliberately wrong key per invocation; the
# group flag must reach the X-Trading-Api-Key header ahead of env/config.


class _RecordingClient:
    headers: dict | None = None

    def __init__(self, base_url=None, timeout=None, headers=None):
        type(self).headers = headers

    def get_json(self, path, params=None):
        return []

    def get(self, path, params=None):
        return {}

    def post(self, path, json=None):
        return {"ok": True}

    def close(self):
        pass


class _Secret:
    def __init__(self, value):
        self._value = value

    def get_secret_value(self):
        return self._value


def _config(api_key=None):
    from types import SimpleNamespace

    return SimpleNamespace(
        trading_service_url="http://trading.test",
        trading_api_key=_Secret(api_key) if api_key else None,
    )


def test_group_api_key_override_reaches_headers(runner, monkeypatch):
    monkeypatch.setattr(trade_mod, "AITBCHTTPClient", _RecordingClient)
    result = runner.invoke(
        trade,
        ["--api-key", "wrong-key-123", "chains"],
        obj={"config": _config(), "output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    assert _RecordingClient.headers == {"X-Trading-Api-Key": "wrong-key-123"}


def test_env_key_still_used_without_flag(runner, monkeypatch):
    monkeypatch.setattr(trade_mod, "AITBCHTTPClient", _RecordingClient)
    key = _config(api_key="env-key")
    result = runner.invoke(trade, ["chains"], obj={"config": key, "output_format": "json"})
    assert result.exit_code == 0, result.output
    assert _RecordingClient.headers == {"X-Trading-Api-Key": "env-key"}


def test_watch_accepts_bounds(runner):
    result = runner.invoke(trade, ["watch", "--help"])
    assert result.exit_code == 0
    assert "--max-events" in result.output
    assert "--timeout" in result.output
