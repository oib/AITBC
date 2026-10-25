"""Both-shape acceptance for `governance get` and `reputation leaderboard` (CLI-ARRAY-1).

`AITBCHTTPClient.get` raises TypeError on a JSON array; these endpoints can
answer a bare array on some deployments and an object on others, so the
callers use `get_json` and handle both shapes.
"""

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.governance as gov_mod
import aitbc_cli.commands.reputation as rep_mod
from aitbc_cli.commands.governance import governance
from aitbc_cli.commands.reputation import reputation


@pytest.fixture
def runner():
    return CliRunner()


class _StubClient:
    def __init__(self, payload, **kw):
        self.payload = payload

    def get_json(self, path, params=None):
        return self.payload

    def get(self, path, params=None):
        raise AssertionError("client.get must not be used on array-shaped endpoints")

    def close(self):
        pass


def _stub(monkeypatch, module, payload):
    monkeypatch.setattr(module, "AITBCHTTPClient", lambda **kw: _StubClient(payload))
    if module is rep_mod:
        monkeypatch.setattr(rep_mod, "_coordinator_client", lambda ctx=None: _StubClient(payload))
    else:
        monkeypatch.setattr(gov_mod, "_get_client", lambda ctx=None, url=None: _StubClient(payload))


def test_governance_get_object_shape(runner, monkeypatch):
    _stub(monkeypatch, gov_mod, {"proposal_id": "p1", "title": "t"})
    result = runner.invoke(governance, obj={"output_format": "json"}, args=["get", "--proposal-id", "p1"])
    assert result.exit_code == 0
    assert "p1" in result.output


def test_governance_get_array_shape_selects_id(runner, monkeypatch):
    payload = [{"proposal_id": "p1", "title": "one"}, {"proposal_id": "p2", "title": "two"}]
    _stub(monkeypatch, gov_mod, payload)
    result = runner.invoke(governance, obj={"output_format": "json"}, args=["get", "--proposal-id", "p2"])
    assert result.exit_code == 0
    assert "two" in result.output


def test_governance_get_array_missing_id_not_found(runner, monkeypatch):
    _stub(monkeypatch, gov_mod, [{"proposal_id": "p1"}])
    result = runner.invoke(governance, obj={"output_format": "json"}, args=["get", "--proposal-id", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_governance_get_null_not_found(runner, monkeypatch):
    _stub(monkeypatch, gov_mod, None)
    result = runner.invoke(governance, obj={"output_format": "json"}, args=["get", "--proposal-id", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_leaderboard_array_shape(runner, monkeypatch):
    payload = [{"rank": 1, "agent_id": "a1", "trust_score": 900, "reputation_level": "legendary", "transaction_count": 5}]
    _stub(monkeypatch, rep_mod, payload)
    result = runner.invoke(reputation, obj={"output_format": "json"}, args=["leaderboard"])
    assert result.exit_code == 0
    assert "a1" in result.output


def test_leaderboard_object_shape(runner, monkeypatch):
    payload = {
        "leaderboard": [{"rank": 1, "agent_id": "a2", "trust_score": 10, "reputation_level": "x", "transaction_count": 1}]
    }
    _stub(monkeypatch, rep_mod, payload)
    result = runner.invoke(reputation, obj={"output_format": "json"}, args=["leaderboard"])
    assert result.exit_code == 0
    assert "a2" in result.output
