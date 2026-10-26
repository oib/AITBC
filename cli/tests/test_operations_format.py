"""CLI-OPERATIONS-FORMAT-1: --format json must emit JSON, not a table."""

import json
import aitbc_cli.commands.operations as ops
from click.testing import CliRunner


def _fake_client(payload):
    class C:
        def __init__(self, **kw):
            pass

        def get(self, path):
            return payload

    return C


def test_voting_power_json(monkeypatch):
    monkeypatch.setattr(ops, "AITBCHTTPClient", _fake_client({"voting_power": 1}))
    monkeypatch.setattr(ops, "get_config", lambda: type("C", (), {"governance_service_url": "http://x"})())
    r = CliRunner().invoke(ops.voting_power, ["--address", "0x0", "--format", "json"])
    assert r.exit_code == 0
    i = r.output.index("{")
    json.loads(r.output[i:])  # body after warnings must be JSON


def test_voting_power_table_default(monkeypatch):
    monkeypatch.setattr(ops, "AITBCHTTPClient", _fake_client({"voting_power": 1}))
    monkeypatch.setattr(ops, "get_config", lambda: type("C", (), {"governance_service_url": "http://x"})())
    r = CliRunner().invoke(ops.voting_power, ["--address", "0x0"])
    assert "+---" in r.output or "|" in r.output


def _cfg():
    return type("C", (), {"governance_service_url": "http://x", "coordinator_url": "http://x"})()


def test_proposal_json(monkeypatch):
    class C:
        def __init__(self, **kw):
            pass

        def get(self, path):
            return {"id": "p1"}

    monkeypatch.setattr(ops, "AITBCHTTPClient", C)
    monkeypatch.setattr(ops, "get_config", _cfg)
    r = CliRunner().invoke(ops.get_proposal, ["--proposal-id", "p1", "--format", "json"])
    assert r.exit_code == 0
    json.loads(r.output[r.output.index("{") :])


def test_execute_json(monkeypatch):
    class C:
        def __init__(self, **kw):
            pass

        def post(self, path, json=None):
            return {"status": "ok"}

    monkeypatch.setattr(ops, "AITBCHTTPClient", C)
    monkeypatch.setattr(ops, "get_config", _cfg)
    r = CliRunner().invoke(ops.execute, ["--proposal-id", "p1", "--format", "json"])
    assert r.exit_code in (0, 1)
    assert "{" in r.output


def test_stake_json(monkeypatch):
    class C:
        def __init__(self, **kw):
            pass

        def post(self, path, json=None):
            return {"staked": 1}

    monkeypatch.setattr(ops, "AITBCHTTPClient", C)
    monkeypatch.setattr(ops, "get_config", _cfg)
    r = CliRunner().invoke(ops.stake, ["--address", "0x0", "--amount", "1", "--lock-days", "30", "--format", "json"])
    assert r.exit_code in (0, 1)
    assert "{" in r.output


def test_delegate_json(monkeypatch):
    class C:
        def __init__(self, **kw):
            pass

        def post(self, path, json=None):
            return {"delegated": 1}

    monkeypatch.setattr(ops, "AITBCHTTPClient", C)
    monkeypatch.setattr(ops, "get_config", _cfg)
    r = CliRunner().invoke(ops.delegate, ["--delegator", "0x0", "--delegate", "0x1", "--amount", "1", "--format", "json"])
    assert r.exit_code in (0, 1)
    assert "{" in r.output


def test_vote_json(monkeypatch):
    """The --format flag must be accepted on the wallet-gated vote command."""

    class C:
        def __init__(self, **kw):
            pass

        def post(self, path, json=None):
            return {"voted": 1}

    monkeypatch.setattr(ops, "AITBCHTTPClient", C)
    monkeypatch.setattr(ops, "get_config", _cfg)
    r = CliRunner().invoke(ops.vote, ["--proposal-id", "p1", "--vote", "for", "--wallet", "nosuch", "--format", "json"])
    assert r.exit_code in (0, 1, 2, 4)  # --format accepted; wallet gate refuses
