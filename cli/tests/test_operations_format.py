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


def _spy_fmt(monkeypatch):
    """Patch resolve_output_format to spy it is invoked with the flag."""
    calls = []
    real = ops.resolve_output_format

    def spy(ctx, fmt):
        calls.append(fmt)
        return real(ctx, fmt)

    monkeypatch.setattr(ops, "resolve_output_format", spy)
    return calls


def _pure_json(out):
    # A resolver-less table render has no JSON body; with a label prefix the
    # json tail must still parse (#562 moves labels to stderr separately).
    i = min([x for x in (out.find("{"), out.find("[")) if x >= 0], default=-1)
    assert i >= 0
    json.loads(out[i:])


def test_get_proposal_json(monkeypatch):
    calls = _spy_fmt(monkeypatch)

    class C:
        def __init__(self, **kw):
            pass

        def get(self, path):
            return {"id": "p1"}

    monkeypatch.setattr(ops, "AITBCHTTPClient", C)
    monkeypatch.setattr(ops, "get_config", _cfg)
    r = CliRunner().invoke(ops.get_proposal, ["--proposal-id", "p1", "--format", "json"])
    assert r.exit_code == 0 and calls == ["json"]
    _pure_json(r.output)


def test_proposal_json(monkeypatch):
    calls = _spy_fmt(monkeypatch)

    class C:
        def __init__(self, **kw):
            pass

        def post(self, path, json=None):
            return {"id": "p1"}

    monkeypatch.setattr(ops, "AITBCHTTPClient", C)
    monkeypatch.setattr(ops, "get_config", _cfg)
    monkeypatch.setattr(ops, "find_wallet_file", lambda w: "/tmp/w.json")
    monkeypatch.setattr(ops, "_load_wallet", lambda *a, **k: {"address": "0x0000000000000000000000000000000000000001"})
    import aitbc_cli.utils.chain_id as cid

    monkeypatch.setattr(cid, "resolve_chain_id", lambda *a, **k: "bc-2")
    r = CliRunner().invoke(
        ops.proposal, ["--proposal-id", "p1", "--title", "t", "--description", "d", "--wallet", "w", "--format", "json"]
    )
    assert r.exit_code == 0 and calls == ["json"]
    _pure_json(r.output)


def test_vote_json(monkeypatch):
    calls = _spy_fmt(monkeypatch)

    class C:
        def __init__(self, **kw):
            pass

        def post(self, path, json=None):
            return {"voted": 1}

    monkeypatch.setattr(ops, "AITBCHTTPClient", C)
    monkeypatch.setattr(ops, "get_config", _cfg)
    monkeypatch.setattr(ops, "find_wallet_file", lambda w: "/tmp/w.json")
    monkeypatch.setattr(ops, "_load_wallet", lambda *a, **k: {"address": "0x0000000000000000000000000000000000000001"})
    import aitbc_cli.utils.chain_id as cid

    monkeypatch.setattr(cid, "resolve_chain_id", lambda *a, **k: "bc-2")
    r = CliRunner().invoke(ops.vote, ["--proposal-id", "p1", "--vote", "for", "--wallet", "w", "--format", "json"])
    assert r.exit_code == 0 and calls == ["json"]
    _pure_json(r.output)
