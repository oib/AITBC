"""CLI-ARRAY-SWEEP-1 (#552): `aitbc grant list` must render the JSON array
returned by GET /v1/grants.

The coordinator grants router declares ``response_model=list[...]`` — a bare
JSON array; ``AITBCHTTPClient.get()`` narrows the body through
``expect_object`` and raises TypeError on arrays, so every `aitbc grant list`
invocation aborts (same class as #490 / #529 / #543). The command must use
``get_json()`` and pass either shape through to the output renderer.
"""

import json

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.grant as grant_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.grant import grant

_GRANTS = [
    {"grant_id": "grant-1", "title": "Build A", "status": "open"},
    {"grant_id": "grant-2", "title": "Build B", "status": "funded"},
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
    monkeypatch.setattr(grant_mod, "AITBCHTTPClient", lambda *a, **kw: client)


def test_grant_list_array_json_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_GRANTS))
    result = runner.invoke(grant, ["list", "--format", "json"], obj={})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert [row["grant_id"] for row in payload] == ["grant-1", "grant-2"]


def test_grant_list_array_table_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_GRANTS))
    result = runner.invoke(grant, ["list"], obj={})
    assert result.exit_code == 0, result.output
    assert "grant-1" in result.output
    assert "grant-2" in result.output


def test_grant_list_object_shape_still_works(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient({"grants": _GRANTS}))
    result = runner.invoke(grant, ["list", "--format", "json"], obj={})
    assert result.exit_code == 0, result.output


def test_grant_list_network_error_still_aborts(runner, monkeypatch):
    _patch(monkeypatch, _FailingClient())
    result = runner.invoke(grant, ["list"], obj={})
    assert result.exit_code != 0
    assert "Error listing grants" in result.output or "Network error" in result.output
