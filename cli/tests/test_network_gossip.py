"""Tests for ``aitbc network gossip``.

The command joins two sources that disagree in kind: a JSON validator list and
a Prometheus text exposition. Most of what can go wrong is in the parsing and
in the fallback that decides which of the two connection signals to trust, so
that is what these cover.
"""

from __future__ import annotations

from click.testing import CliRunner

from aitbc_cli.commands import network as network_mod
from aitbc_cli.core.main import cli

NETWORK_INFO = {
    "node_id": "node-test",
    "chain_id": "ait-test",
    "gossip_websocket_url": "wss://node-test/rpc/gossip/ws",
    "gossip_auth_required": True,
    "validators": [
        {"address": "0xAAA", "stake": "1000"},
        {"address": "0xBBB", "stake": "1000"},
        {"address": "0xCCC", "stake": "1000"},
    ],
}

WITH_GAUGE = """\
# HELP blockchain_gossip_auth_accepted_total Total gossip websocket auth successes
blockchain_gossip_auth_accepted_total{address="0xAAA"} 4.0
blockchain_gossip_auth_accepted_total{address="0xBBB"} 2.0
blockchain_gossip_authenticated_connections{address="0xAAA"} 1.0
blockchain_gossip_authenticated_connections{address="0xBBB"} 0.0
blockchain_gossip_open_connections 7.0
blockchain_gossip_messages_published_total{topic="blocks.ait-test"} 9.0
process_start_time_seconds 1.0
"""

WITHOUT_GAUGE = """\
blockchain_gossip_auth_accepted_total{address="0xAAA"} 4.0
blockchain_gossip_auth_accepted_total{address="0xBBB"} 2.0
blockchain_gossip_auth_rejected_total{reason="bad_signature"} 3.0
process_start_time_seconds 1.0
"""


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def _run(monkeypatch, metrics_text: str, *args):
    monkeypatch.setattr(network_mod.AITBCHTTPClient, "get", lambda self, endpoint, **kw: NETWORK_INFO, raising=True)
    monkeypatch.setattr(network_mod.requests, "get", lambda url, timeout=None: _FakeResponse(metrics_text), raising=True)
    return CliRunner().invoke(cli, ["--output", "json", "network", "gossip", *args])


def test_prefers_the_liveness_gauge_over_the_auth_counter(monkeypatch):
    """0xBBB authenticated in the past but holds no socket now, so it is down."""
    result = _run(monkeypatch, WITH_GAUGE)
    assert result.exit_code == 0, result.output
    payload = __import__("json").loads(result.output)
    summary = payload["summary"]
    assert summary["basis"] == "live connections"
    assert summary["peers_connected"] == 1
    assert summary["peers_expected"] == 2
    assert summary["verdict"] == "degraded"
    assert summary["open_connections"] == 7
    by_address = {row["address"]: row for row in payload["peers"]}
    assert by_address["0xAAA"]["connected"] == "yes"
    assert by_address["0xBBB"]["connected"] == "no"
    assert by_address["0xBBB"]["auth_ok"] == 2
    assert "auth_failed" not in by_address["0xBBB"]
    assert by_address["0xCCC"]["connected"] == "no"


def test_falls_back_to_counters_when_the_node_has_no_gauge(monkeypatch):
    """An older node exposes no gauge; the weaker signal is used and labelled."""
    result = _run(monkeypatch, WITHOUT_GAUGE)
    assert result.exit_code == 0, result.output
    payload = __import__("json").loads(result.output)
    summary = payload["summary"]
    assert "auth counters" in summary["basis"]
    assert summary["peers_connected"] == 2
    assert summary["peers_expected"] == 2
    assert summary["verdict"] == "ok"
    assert summary["open_connections"] == "-"
    assert summary["auth_failures"] == 3
    assert payload["auth_rejections"] == [{"reason": "bad_signature", "count": 3}]


def test_scrape_indexes_labelled_and_bare_samples(monkeypatch):
    """Both `name{label="v"} 1.0` and bare `name 1.0` lines must be indexed."""
    monkeypatch.setattr(network_mod.requests, "get", lambda url, timeout=None: _FakeResponse(WITH_GAUGE), raising=True)
    samples = network_mod._scrape_prom("http://ignored/metrics", 1)

    # Comment lines are skipped, not parsed as samples.
    assert "# HELP blockchain_gossip_auth_accepted_total" not in samples
    assert network_mod._sample_map(samples, "blockchain_gossip_auth_accepted_total", "address") == {
        "0xAAA": 4.0,
        "0xBBB": 2.0,
    }
    assert network_mod._sample_total(samples, "blockchain_gossip_open_connections") == 7.0
    # A label that the metric does not carry yields no rows rather than raising.
    assert network_mod._sample_map(samples, "blockchain_gossip_open_connections", "address") == {}
