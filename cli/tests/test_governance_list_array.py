"""CLI-ARRAY-SWEEP-1 (#552): `aitbc governance list` must render the JSON
array returned by GET /v1/governance/proposals.

The governance service handler ``return``s ``list[Proposal]`` — a bare JSON
array, confirmed live on node2 ("returned a JSON array, not an object").
``AITBCHTTPClient.get()`` narrows the body through ``expect_object`` and
raises TypeError on arrays, so every `aitbc governance list` invocation
aborts (same class as #490 / #529 / #543). The command must use
``get_json()`` and pass either shape through to the output renderer.
"""

import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.governance as governance_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.governance import governance

_PROPOSALS = [
    {"proposal_id": "prop-1", "title": "Raise bond floor", "status": "active"},
    {"proposal_id": "prop-2", "title": "Fee change", "status": "active"},
]


class _ArrayClient:
    """Mimics AITBCHTTPClient: get() narrows to object via expect_object."""

    def __init__(self, payload):
        self._payload = payload

    def get(self, path, params=None):
        raise TypeError(f"Expected JSON object from http://gov{path}, got list")

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
    monkeypatch.setattr(governance_mod, "AITBCHTTPClient", lambda *a, **kw: client)


def _obj():
    return {"config": SimpleNamespace(governance_service_url="")}


def test_governance_list_array_json_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_PROPOSALS))
    result = runner.invoke(governance, ["list", "--format", "json"], obj=_obj())
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert [row["proposal_id"] for row in payload] == ["prop-1", "prop-2"]


def test_governance_list_array_table_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_PROPOSALS))
    result = runner.invoke(governance, ["list"], obj=_obj())
    assert result.exit_code == 0, result.output
    assert "prop-1" in result.output
    assert "Raise bond floor" in result.output


def test_governance_list_object_shape_still_works(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient({"proposals": _PROPOSALS}))
    result = runner.invoke(governance, ["list", "--format", "json"], obj=_obj())
    assert result.exit_code == 0, result.output


def test_governance_list_network_error_still_aborts(runner, monkeypatch):
    _patch(monkeypatch, _FailingClient())
    result = runner.invoke(governance, ["list"], obj=_obj())
    assert result.exit_code != 0
    assert "Error listing proposals" in result.output or "Network error" in result.output
