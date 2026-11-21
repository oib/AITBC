"""#2412 — analytics must read real chain data, not structural zeros.

The chain-rpc ``get_chain_stats`` fallback used to return only ``height``, so
``avg_block_time``/``active_nodes``/``tps`` defaulted to 0, were stored as
"live" metrics, and ``node_count_low`` fired a false critical alert against a
4-validator PBFT chain. The fallback now composes real values from
``/blocks-range``, ``/network-info`` and ``/info``, and block-time checks are
judged against the chain's configured ``block_time_seconds`` target.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import pytest

from aitbc_cli.core.analytics import ChainAnalytics, ChainMetrics
from aitbc_cli.core.config import MultiChainConfig, NodeConfig
from aitbc_cli.core.node_client import NodeClient


def _metrics(**overrides) -> ChainMetrics:
    base = dict(
        chain_id="bc-2",
        node_id="n0",
        timestamp=datetime.now(),
        block_height=100,
        tps=0.0,
        avg_block_time=0.0,
        gas_price=0,
        memory_usage_mb=0.0,
        disk_usage_mb=0.0,
        active_nodes=0,
        client_count=0,
        miner_count=0,
        agent_count=0,
        network_in_mb=0.0,
        network_out_mb=0.0,
    )
    base.update(overrides)
    return ChainMetrics(**base)


def _analytics() -> ChainAnalytics:
    return ChainAnalytics(MultiChainConfig(nodes={"n0": NodeConfig(id="n0", endpoint="http://x/rpc")}))


# --- node_client enrichment ---


def _ts(minutes_ago: float) -> str:
    return (datetime.now() - timedelta(minutes=minutes_ago)).isoformat()


@pytest.mark.asyncio
async def test_rpc_head_stats_enriched_from_public_routes(monkeypatch):
    """head + blocks-range + network-info + info -> real windowed stats."""
    blocks = [
        {"height": 100 - i, "timestamp": _ts(i * 1.0), "tx_count": 0}
        for i in range(11, -1, -1)
    ]

    range_params: dict[str, str] = {}

    def _h(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.endswith("/head"):
            return httpx.Response(200, json={"height": 100, "timestamp": _ts(0)})
        if path.endswith("/blocks-range"):
            range_params.update({k: v for k, v in req.url.params.items()})
            return httpx.Response(200, json={"success": True, "blocks": blocks, "count": len(blocks)})
        if path.endswith("/network-info"):
            return httpx.Response(200, json={"validators": [{"address": f"0x{i}"} for i in range(4)]})
        if path.endswith("/info"):
            return httpx.Response(200, json={"genesis_params": {"block_time_seconds": 60}})
        return httpx.Response(404, json={})

    orig = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: orig(transport=httpx.MockTransport(_h)))

    nc = NodeClient(NodeConfig(id="n0", endpoint="http://node.test:8202"))
    async with nc:
        stats = await nc.get_chain_stats("bc-2")

    assert stats["source"] == "rpc-head"
    assert stats["block_height"] == 100
    # 12 blocks 1 minute apart -> ~60s mean interval, ~0 TPS (empty blocks).
    assert stats["avg_block_time"] == pytest.approx(60.0, abs=1.0)
    assert stats["tps"] == pytest.approx(0.0, abs=0.01)
    assert stats["active_nodes"] == 4
    assert stats["expected_block_time"] == 60.0
    # The range route takes start/end heights — the window must be the
    # last ~12 blocks back from head height 100, not a `limit` param the
    # route ignores (which served genesis blocks 0-10).
    assert range_params.get("start") == "89"
    assert range_params.get("end") == "100"
    assert range_params.get("include_tx") == "false"


@pytest.mark.asyncio
async def test_rpc_head_stats_degrade_when_aux_routes_fail(monkeypatch):
    """Aux probes are best-effort: head alone still yields height + source."""

    def _h(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/head"):
            return httpx.Response(200, json={"height": 7})
        return httpx.Response(500, json={})

    orig = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: orig(transport=httpx.MockTransport(_h)))

    nc = NodeClient(NodeConfig(id="n0", endpoint="http://node.test:8202/rpc"))
    async with nc:
        stats = await nc.get_chain_stats("bc-2")

    assert stats["block_height"] == 7
    assert stats["source"] == "rpc-head"
    assert "avg_block_time" not in stats
    assert "active_nodes" not in stats
    assert "expected_block_time" not in stats


# --- analytics thresholds ---


@pytest.mark.asyncio
async def test_block_time_alert_uses_configured_target():
    """A PBFT chain at ~69s blocks vs a 60s target must not alert."""
    a = _analytics()
    m = _metrics(avg_block_time=69.0, expected_block_time=60.0, active_nodes=4)
    await a._check_alerts(m)
    assert not [x for x in a.alerts if x.alert_type == "block_time_high"]

    slow = _metrics(avg_block_time=120.0, expected_block_time=60.0)
    await a._check_alerts(slow)
    bt = [x for x in a.alerts if x.alert_type == "block_time_high"]
    assert bt and bt[-1].threshold == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_block_time_alert_legacy_threshold_without_target():
    a = _analytics()
    await a._check_alerts(_metrics(avg_block_time=12.0))
    bt = [x for x in a.alerts if x.alert_type == "block_time_high"]
    assert bt and bt[-1].threshold == a.thresholds["block_time_high"]


def test_health_score_block_time_uses_target_ratio():
    a = _analytics()
    a.metrics_history["bc-2"].append(_metrics(avg_block_time=60.0, expected_block_time=60.0, active_nodes=5, tps=10.0))
    a._calculate_health_score("bc-2")
    on_target = a.health_scores["bc-2"]
    a.metrics_history["bc-2"].append(_metrics(avg_block_time=120.0, expected_block_time=60.0, active_nodes=5, tps=10.0))
    a._calculate_health_score("bc-2")
    assert on_target > a.health_scores["bc-2"]


def test_recommendation_block_time_respects_target():
    a = _analytics()
    a.metrics_history["bc-2"].append(_metrics(avg_block_time=69.0, expected_block_time=60.0, active_nodes=4, tps=0.5))
    recs = a.get_optimization_recommendations("bc-2")
    assert not [r for r in recs if r["issue"] == "High block time"]
