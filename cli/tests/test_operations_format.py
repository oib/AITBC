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
