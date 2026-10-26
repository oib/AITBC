"""CLI-ARRAY-SWEEP-1 (#552): `aitbc dispute votes` and
`aitbc dispute evidence list` must render the JSON arrays returned by
/rpc/disputes/{id}/votes and /rpc/disputes/{id}/evidence.

Both RPC routes are annotated ``-> list[...]`` — bare JSON arrays;
``AITBCHTTPClient.get()`` narrows the body through ``expect_object`` and
raises TypeError on arrays, so both commands abort on any real dispute
(same class as #490 / #529 / #543). They must use ``get_json()`` and pass
either shape through to the output renderer.
"""

import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.dispute as dispute_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.dispute import dispute

_VOTES = [
    {"arbitrator": "0xaaa", "vote": "plaintiff", "reasoning": "evidence is conclusive"},
    {"arbitrator": "0xbbb", "vote": "defendant", "reasoning": "intent unclear"},
]

_EVIDENCE = [
    {"evidence_id": 1, "dispute_id": 42, "description": "log bundle", "submitted_by": "0xaaa"},
    {"evidence_id": 2, "dispute_id": 42, "description": "screen capture", "submitted_by": "0xbbb"},
]


class _ArrayClient:
    """Mimics AITBCHTTPClient: get() narrows to object via expect_object."""

    def __init__(self, payload):
        self._payload = payload

    def get(self, path, params=None):
        raise TypeError(f"Expected JSON object from http://rpc{path}, got list")

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
    monkeypatch.setattr(dispute_mod, "_chain_client", lambda *a, **kw: client)
    monkeypatch.setattr(
        dispute_mod,
        "get_config",
        lambda *a, **kw: SimpleNamespace(blockchain_rpc_url="http://rpc", blockchain_rpc_api_key=None, timeout=10),
    )


def test_dispute_votes_array_json_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_VOTES))
    result = runner.invoke(dispute, ["votes", "42", "--format", "json"], obj={})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert [row["arbitrator"] for row in payload] == ["0xaaa", "0xbbb"]


def test_dispute_votes_array_table_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_VOTES))
    result = runner.invoke(dispute, ["votes", "42"], obj={})
    assert result.exit_code == 0, result.output
    assert "0xaaa" in result.output
    assert "plaintiff" in result.output


def test_dispute_evidence_list_array_json_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_EVIDENCE))
    result = runner.invoke(dispute, ["evidence", "list", "42", "--format", "json"], obj={})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert [row["evidence_id"] for row in payload] == [1, 2]


def test_dispute_evidence_list_array_table_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_EVIDENCE))
    result = runner.invoke(dispute, ["evidence", "list", "42"], obj={})
    assert result.exit_code == 0, result.output
    assert "log bundle" in result.output


def test_dispute_votes_network_error_still_aborts(runner, monkeypatch):
    _patch(monkeypatch, _FailingClient())
    result = runner.invoke(dispute, ["votes", "42"], obj={})
    assert result.exit_code != 0
    assert "Error fetching votes" in result.output or "Blockchain RPC error" in result.output


def test_dispute_evidence_network_error_still_aborts(runner, monkeypatch):
    _patch(monkeypatch, _FailingClient())
    result = runner.invoke(dispute, ["evidence", "list", "42"], obj={})
    assert result.exit_code != 0
    assert "Error fetching evidence" in result.output or "Blockchain RPC error" in result.output
