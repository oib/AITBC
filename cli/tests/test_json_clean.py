"""CLI-JSON-CLEAN-1: under --output json, stdout must parse as JSON."""

import json
from click.testing import CliRunner

import aitbc_cli.commands.transactions as tx


class _C:
    def __init__(self, **kw):
        pass

    def get(self, path, **kw):
        return {"transactions": [], "ok": True}


def test_pending_json_clean(monkeypatch):
    monkeypatch.setattr(tx, "AITBCHTTPClient", _C)
    monkeypatch.setattr(tx, "_resolve_transaction_rpc_url", lambda x: "http://x")
    r = CliRunner().invoke(tx.pending, obj={"output_format": "json"})
    assert r.exit_code == 0
    json.loads(r.output)


def test_pending_table_keeps_lines(monkeypatch):
    monkeypatch.setattr(tx, "AITBCHTTPClient", _C)
    monkeypatch.setattr(tx, "_resolve_transaction_rpc_url", lambda x: "http://x")
    r = CliRunner().invoke(tx.pending, obj={"output_format": "table"})
    assert r.exit_code == 0


def test_status_stderr_routing(monkeypatch):
    """Pin: success/info/warning/error go to stderr under json, stdout in table."""
    import sys
    import click

    out = sys.modules["aitbc_cli.utils.output"]

    captured = []
    monkeypatch.setattr(out, "secho", lambda msg, **kw: captured.append((msg, kw.get("err"))))

    # table context -> stdout (err=False)
    with click.Context(click.Command("t"), obj={"output_format": "table"}):
        out.success("x")
    assert captured[-1][1] is False

    # json context -> stderr (err=True)
    with click.Context(click.Command("t"), obj={"output_format": "json"}):
        out.success("x")
    assert captured[-1][1] is True


def test_table_mode_keeps_stdout():
    """Table mode still emits label lines on stdout."""
    import aitbc_cli.commands.transactions as tx

    class C:
        def __init__(self, **kw):
            pass

        def get(self, path, **kw):
            return {"transactions": []}

    import unittest.mock as m

    with m.patch.object(tx, "AITBCHTTPClient", C), m.patch.object(tx, "_resolve_transaction_rpc_url", lambda x: "http://x"):
        r = CliRunner().invoke(tx.pending, obj={"output_format": "table"})
    assert "Pending transactions" in r.output
