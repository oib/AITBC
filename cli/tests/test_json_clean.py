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


def test_market_list_leaf_format_json_routes_status_to_stderr(monkeypatch):
    """Leaf ``--format json`` must keep the 'Found N market offers' label off stdout.

    Regresses CLI-JSON-CLEAN-1: leaves declare the option via OUTPUT_FORMAT_OPTION
    (param name ``output_format``), which the old ``params["format"]`` check missed.
    """
    import aitbc_cli.commands.market.offers as offers
    from aitbc_cli.utils.output import output as render_output, success

    def fake_list(bases, config, fmt, *args):
        render_output([{"id": "o1"}], fmt)
        success("Found 1 market offers")
        return True

    monkeypatch.setattr(offers, "get_config", lambda: object())
    monkeypatch.setattr(offers, "_hub_base_url", lambda config: "http://x")
    monkeypatch.setattr(offers, "_candidate_bases", lambda hub, config: ["http://x"])
    monkeypatch.setattr(offers, "_list_offers_via_market_api", fake_list)

    r = CliRunner().invoke(offers.list_offers, ["--format", "json"], obj={"output_format": "table"})
    assert r.exit_code == 0, r.output
    assert "Found" not in r.stdout
    json.loads(r.stdout)
    assert "Found 1 market offers" in r.stderr


def test_exchange_list_empty_json(monkeypatch, tmp_path):
    """No exchanges.json -> bare ``[]`` on stdout under json."""
    from pathlib import Path

    import aitbc_cli.commands.exchange.main as ex

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    r = CliRunner().invoke(ex.list, obj={"output_format": "json"})
    assert r.exit_code == 0, r.output
    assert r.stdout == "[]\n"


def test_coin_requests_list_empty_json(monkeypatch):
    """Empty ledger -> bare ``[]`` on stdout under json."""
    import aitbc_cli.commands.coin_requests as cr

    class _Query:
        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return []

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query(self, *args):
            return _Query()

    monkeypatch.setattr(cr, "get_db_session", lambda: _Session())
    r = CliRunner().invoke(cr.list, obj={"output_format": "json"})
    assert r.exit_code == 0, r.output
    assert r.stdout == "[]\n"
