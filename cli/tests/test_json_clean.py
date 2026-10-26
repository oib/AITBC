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


def _market_offers_mod():
    import aitbc_cli.commands.market.offers as offers

    return offers


class _EmptySourceClient:
    """Fake HTTP client where every endpoint answers with an empty result."""

    def __init__(self, **kw):
        pass

    def get(self, path, params=None, **kw):
        return {"offers": [], "transactions": []}

    def get_json(self, path, params=None, **kw):
        return []


class _DeadSourceClient:
    """Fake HTTP client where every endpoint is unreachable."""

    def __init__(self, **kw):
        pass

    def get(self, path, params=None, **kw):
        import aitbc_cli.commands.market.offers as offers

        raise offers.NetworkError("connection refused")

    def get_json(self, path, params=None, **kw):
        import aitbc_cli.commands.market.offers as offers

        raise offers.NetworkError("connection refused")


def _patch_market_env(monkeypatch, offers, client_cls):
    from types import SimpleNamespace

    config = SimpleNamespace(
        hub_discovery_url="http://127.0.0.1:9",
        market_service_url="",
        coordinator_api_url="",
        blockchain_rpc_url="http://127.0.0.1:9",
    )
    monkeypatch.setattr(offers, "AITBCHTTPClient", client_cls)
    monkeypatch.setattr(offers, "get_config", lambda: config)
    monkeypatch.setattr(offers, "_hub_base_url", lambda cfg: "http://127.0.0.1:9")


def test_market_list_empty_answer_json(monkeypatch):
    """A source that answers with a real empty list -> bare ``[]``, rc 0."""
    offers = _market_offers_mod()
    _patch_market_env(monkeypatch, offers, _EmptySourceClient)

    r = CliRunner().invoke(offers.list_offers, ["--format", "json"], obj={"output_format": "table"})
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout) == []


def test_market_list_all_sources_fail_leaf_format_json(monkeypatch):
    """Every source unreachable -> non-zero exit with an error, never ``[]``."""
    offers = _market_offers_mod()
    _patch_market_env(monkeypatch, offers, _DeadSourceClient)

    r = CliRunner().invoke(offers.list_offers, ["--format", "json"], obj={"output_format": "table"})
    assert r.exit_code != 0
    payload = json.loads(r.stdout)
    assert "error" in payload
    assert payload != []


def test_market_list_all_sources_fail_output_json(monkeypatch):
    """Same failure via the global ``--output json`` path."""
    offers = _market_offers_mod()
    _patch_market_env(monkeypatch, offers, _DeadSourceClient)

    r = CliRunner().invoke(offers.list_offers, [], obj={"output_format": "json"})
    assert r.exit_code != 0
    payload = json.loads(r.stdout)
    assert "error" in payload
    assert payload != []


def test_market_list_mixed_empty_and_dead_json(monkeypatch):
    """One base answers empty, the other is dead -> ``[]``, rc 0."""
    offers = _market_offers_mod()
    _patch_market_env(monkeypatch, offers, _EmptySourceClient)

    calls = []

    class _Mixed:
        def __init__(self, base_url=None, **kw):
            self.base_url = base_url

        def get(self, path, params=None, **kw):
            calls.append(self.base_url)
            if self.base_url == "http://dead":
                raise offers.NetworkError("connection refused")
            return {"offers": []}

        def get_json(self, path, params=None, **kw):
            raise offers.NetworkError("connection refused")

    monkeypatch.setattr(offers, "AITBCHTTPClient", _Mixed)
    monkeypatch.setattr(offers, "_candidate_bases", lambda hub, cfg: ["http://dead", "http://alive"])

    r = CliRunner().invoke(offers.list_offers, ["--format", "json"], obj={"output_format": "table"})
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout) == []
    assert calls[:2] == ["http://dead", "http://alive"]


def _fake_analytics_cls():
    """ChainAnalytics double producing both the overview and comparison sets."""

    class _Metrics:
        chain_id = "bc-2"
        timestamp = None
        tps = 1.0
        avg_block_time = 2.0
        gas_price = 5

    class _A:
        def __init__(self, config):
            pass

        async def collect_all_metrics(self):
            return {"bc-2": [_Metrics()]}

        def get_cross_chain_analysis(self):
            return {
                "total_chains": 1,
                "active_chains": 1,
                "alerts_summary": {"total_alerts": 0, "critical_alerts": 0},
                "resource_usage": {"total_memory_mb": 1.0, "total_disk_mb": 2.0, "total_clients": 0, "total_agents": 0},
                "performance_comparison": {"bc-2": {"tps": 1.0, "block_time": 2.0, "health_score": 99.0}},
            }

        def get_chain_performance_summary(self, chain_id, hours=24):
            return {
                "chain_id": "bc-2",
                "time_range_hours": hours,
                "data_points": 1,
                "health_score": 99.0,
                "active_alerts": 0,
                "statistics": {
                    "tps": {"avg": 1.0},
                    "block_time": {"avg": 2.0},
                    "gas_price": {"avg": 5},
                },
            }

    return _A


def test_analytics_summary_cross_chain_json_is_one_document(monkeypatch):
    """`analytics summary` (no --chain-id) must emit ONE JSON document.

    Regresses CLI-JSON-CLEAN-1: the overview table and the performance
    comparison table were each pushed through ``output()`` so stdout held
    two JSON documents and ``json.loads`` failed with 'Extra data'.
    """
    import aitbc_cli.commands.analytics as an

    monkeypatch.setattr(an, "load_multichain_config", lambda: object())
    monkeypatch.setattr(an, "ChainAnalytics", _fake_analytics_cls())

    r = CliRunner().invoke(an.summary, [], obj={"output_format": "json"})
    assert r.exit_code == 0, r.output
    doc = json.loads(r.stdout)  # Extra data -> failure if two docs emitted
    assert set(doc) == {"overview", "comparison"}
    assert doc["comparison"][0]["Chain ID"] == "bc-2"


def test_analytics_summary_chain_id_json_is_one_document(monkeypatch):
    """`analytics summary --chain-id bc-2` must emit ONE JSON document."""
    import aitbc_cli.commands.analytics as an

    monkeypatch.setattr(an, "load_multichain_config", lambda: object())
    monkeypatch.setattr(an, "ChainAnalytics", _fake_analytics_cls())

    r = CliRunner().invoke(an.summary, ["--chain-id", "bc-2"], obj={"output_format": "json"})
    assert r.exit_code == 0, r.output
    doc = json.loads(r.stdout)
    assert doc[0]["Value"] == "bc-2"


def test_analytics_summary_abort_emits_one_json_error(monkeypatch):
    """No data -> abort() prints the error ONCE, not twice.

    The ``except Exception`` wrapper used to catch the CLIError raised by the
    inner abort() and abort again, producing a second JSON error document.
    """
    import aitbc_cli.commands.analytics as an

    class _Empty:
        def __init__(self, config):
            pass

        async def collect_all_metrics(self):
            return {}

        def get_chain_performance_summary(self, chain_id, hours=24):
            return {}

        def get_cross_chain_analysis(self):
            return {}

    monkeypatch.setattr(an, "load_multichain_config", lambda: object())
    monkeypatch.setattr(an, "ChainAnalytics", _Empty)

    r = CliRunner().invoke(an.summary, ["--chain-id", "bc-2"], obj={"output_format": "json"})
    assert r.exit_code != 0
    doc = json.loads(r.stdout)
    assert doc["error"]


def test_analytics_summary_table_keeps_two_sections(monkeypatch):
    """Table mode is unchanged: two titled sections on stdout."""
    import aitbc_cli.commands.analytics as an

    monkeypatch.setattr(an, "load_multichain_config", lambda: object())
    monkeypatch.setattr(an, "ChainAnalytics", _fake_analytics_cls())

    r = CliRunner().invoke(an.summary, [], obj={"output_format": "table"})
    assert r.exit_code == 0, r.output
    assert "Cross-Chain Analysis Overview" in r.stdout
    assert "Chain Performance Comparison" in r.stdout


def test_market_list_abort_json_payload_exit_code_matches_process_exit(monkeypatch, capsys):
    """CLI-JSON-CLEAN-1: the JSON error payload's ``exit_code`` must be the
    code the process actually exits with through ``main()``.

    Regression: ``list_offers`` used to translate the ``CLIError`` raised by
    ``abort()`` into ``click.Abort()``, so the process exited 1 while the
    payload still claimed ``exit_code: 2`` (NetworkError).
    """
    offers = _market_offers_mod()
    _patch_market_env(monkeypatch, offers, _DeadSourceClient)

    from aitbc_cli.core.main import main

    rc = main(["market", "list", "--format", "json"])
    out = capsys.readouterr()
    assert rc != 0
    doc = json.loads(out.out)  # exactly one JSON document
    assert doc["error"]
    assert doc["exit_code"] == rc


def test_market_list_all_sources_fail_table_prints_error_once(monkeypatch, capsys):
    """Table mode: the all-sources-dead error is printed exactly once.

    Regression: the broad ``except Exception`` wrapper caught the CLIError
    already reported by abort() and printed it again (plus a bare
    ``Aborted!`` from the translated ``click.Abort``).
    """
    offers = _market_offers_mod()
    _patch_market_env(monkeypatch, offers, _DeadSourceClient)

    from aitbc_cli.core.main import main

    rc = main(["market", "list"])
    out = capsys.readouterr()
    combined = out.out + out.err
    assert rc != 0
    assert combined.count("No market data source answered") == 1
    assert "Error listing GPU market" not in combined
    assert "Aborted!" not in combined
