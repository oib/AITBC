"""CLI-ARRAY-SWEEP-1 (#552): `aitbc developer list` must render the JSON array
returned by GET /v1/developers.

The coordinator developer router declares ``response_model=list[...]`` — a
bare JSON array; ``AITBCHTTPClient.get()`` narrows the body through
``expect_object`` and raises TypeError on arrays, so every
`aitbc developer list` invocation aborts (same class as #490 / #529 / #543).
The command must use ``get_json()`` and pass either shape through to the
output renderer.
"""

import json

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.developer as developer_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.developer import developer

_DEVELOPERS = [
    {"developer_id": "dev-1", "wallet_address": "0xabc", "name": "Ada"},
    {"developer_id": "dev-2", "wallet_address": "0xdef", "name": "Grace"},
]


class _ArrayClient:
    """Mimics AITBCHTTPClient: get() narrows to object via expect_object."""

    def __init__(self, payload):
        self._payload = payload

    def get(self, path, params=None):
        raise TypeError(f"Expected JSON object from http://coord{path}, got list")

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
    monkeypatch.setattr(developer_mod, "AITBCHTTPClient", lambda *a, **kw: client)


def test_developer_list_array_json_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_DEVELOPERS))
    result = runner.invoke(developer, ["list", "--format", "json"], obj={})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert [row["developer_id"] for row in payload] == ["dev-1", "dev-2"]


def test_developer_list_array_table_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_DEVELOPERS))
    result = runner.invoke(developer, ["list"], obj={})
    assert result.exit_code == 0, result.output
    assert "dev-1" in result.output
    assert "dev-2" in result.output


def test_developer_list_object_shape_still_works(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient({"developers": _DEVELOPERS}))
    result = runner.invoke(developer, ["list", "--format", "json"], obj={})
    assert result.exit_code == 0, result.output


def test_developer_list_network_error_still_aborts(runner, monkeypatch):
    _patch(monkeypatch, _FailingClient())
    result = runner.invoke(developer, ["list"], obj={})
    assert result.exit_code != 0
    assert "Error listing developers" in result.output or "Network error" in result.output
