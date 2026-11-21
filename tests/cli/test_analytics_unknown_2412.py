"""#2412 residual pins — unknown is not zero, predict persists, noise classified.

Follow-up to ``test_analytics_block_time_2412.py`` (which covered the
blocks-range/network-info enrichment and the configured-interval block-time
threshold). This file pins the remaining issue items:

- ``active_nodes``/``memory_usage_mb``/... are ``None`` when the source does
  not measure them — never a fabricated 0.
- ``node_count_low`` does NOT fire critical on an unknown count; it still
  fires on a *measured* low count (fail-open on missing, fail-closed on
  measured — documented policy).
- Unmeasured metrics produce no alerts/recommendations and drop out of the
  health score (weights renormalize).
- Metrics history persists across CLI invocations so ``predict`` can
  accumulate the >=10 samples it needs.
- Unreachable nodes / dead chain stats are classified once per call
  (consolidated warning + ``node_status``), not per-call error spam, and
  ``last_collect_live`` reflects THIS pass only.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from aitbc_cli.core.analytics import ChainAnalytics, ChainMetrics
from aitbc_cli.core.config import MultiChainConfig, NodeConfig


def _metrics(**overrides) -> ChainMetrics:
    base = dict(
        chain_id="bc-2",
        node_id="n0",
        timestamp=datetime.now(),
        block_height=100,
        tps=0.0,
        avg_block_time=60.0,
        gas_price=0,
        memory_usage_mb=None,
        disk_usage_mb=None,
        active_nodes=None,
        client_count=None,
        miner_count=None,
        agent_count=None,
        network_in_mb=None,
        network_out_mb=None,
    )
    base.update(overrides)
    return ChainMetrics(**base)


def _analytics(tmp_path=None, nodes=None) -> ChainAnalytics:
    """ChainAnalytics with the history file redirected to a scratch dir.

    Always isolated — never the operator's real ``~/.aitbc`` store.
    """
    history_dir = Path(tmp_path) if tmp_path is not None else Path(tempfile.mkdtemp())
    env = {"AITBC_ANALYTICS_HISTORY": str(history_dir / "hist.json")}
    with patch.dict("os.environ", env, clear=False):
        return ChainAnalytics(MultiChainConfig(nodes=nodes or {}))


# --- unknown is not zero ---


@pytest.mark.asyncio
async def test_node_count_low_skipped_when_count_unknown():
    """active_nodes=None (RPC reported no validator list) must not page."""
    a = _analytics()
    await a._check_alerts(_metrics(active_nodes=None))
    assert not [x for x in a.alerts if x.alert_type == "node_count_low"]


@pytest.mark.asyncio
async def test_node_count_low_fires_on_measured_zero():
    """Fail-closed on measured data: a real 0 still alerts (documented)."""
    a = _analytics()
    await a._check_alerts(_metrics(active_nodes=0))
    hits = [x for x in a.alerts if x.alert_type == "node_count_low"]
    assert hits and hits[-1].severity == "critical"


@pytest.mark.asyncio
async def test_node_count_low_quiet_on_healthy_count():
    a = _analytics()
    await a._check_alerts(_metrics(active_nodes=4))
    assert not [x for x in a.alerts if x.alert_type == "node_count_low"]


@pytest.mark.asyncio
async def test_unmeasured_metrics_raise_no_alerts():
    """A bare rpc-head row (height + source only) alerts on nothing."""
    a = _analytics()
    await a._check_alerts(
        _metrics(tps=None, avg_block_time=None, memory_usage_mb=None, gas_price=None, active_nodes=None)
    )
    assert a.alerts == []


def test_health_score_renormalizes_over_measured_components():
    """Only measured components count; weights renormalize to 0-100."""
    a = _analytics()
    # tps=10 -> 100 on the tps component; everything else unmeasured.
    a.metrics_history["bc-2"].append(_metrics(tps=10.0, avg_block_time=None))
    a._calculate_health_score("bc-2")
    assert a.health_scores["bc-2"] == pytest.approx(100.0)

    # Nothing measured at all -> honest 0, no crash.
    a.metrics_history["bc-1"].append(_metrics(chain_id="bc-1", tps=None, avg_block_time=None))
    a._calculate_health_score("bc-1")
    assert a.health_scores["bc-1"] == 0.0


def test_summary_stats_unknown_not_zero():
    a = _analytics()
    a.metrics_history["bc-2"].append(_metrics(tps=None, avg_block_time=None, gas_price=None))
    summary = a.get_chain_performance_summary("bc-2", 24)
    assert summary["statistics"]["tps"]["avg"] is None
    assert summary["statistics"]["block_time"]["avg"] is None
    assert summary["statistics"]["gas_price"]["avg"] is None
    assert summary["latest_metrics"]["active_nodes"] is None


def test_no_recommendation_for_unmeasured_node_count():
    a = _analytics()
    a.metrics_history["bc-2"].append(_metrics(active_nodes=None, tps=50.0, avg_block_time=60.0))
    recs = a.get_optimization_recommendations("bc-2")
    assert not [r for r in recs if r["issue"] == "Low node count"]


def test_resource_totals_none_when_nothing_reported():
    a = _analytics()
    a.metrics_history["bc-2"].append(_metrics())
    analysis = a.get_cross_chain_analysis()
    usage = analysis["resource_usage"]
    assert usage["total_memory_mb"] is None
    assert usage["total_disk_mb"] is None
    assert usage["total_clients"] is None
    assert "_resource_samples" not in analysis


def test_resource_totals_sum_only_measured():
    a = _analytics()
    a.metrics_history["bc-2"].append(_metrics(memory_usage_mb=100.0, client_count=3))
    a.metrics_history["bc-3"].append(_metrics(chain_id="bc-3"))  # all unmeasured
    usage = a.get_cross_chain_analysis()["resource_usage"]
    assert usage["total_memory_mb"] == pytest.approx(100.0)
    assert usage["total_clients"] == 3
    assert usage["total_disk_mb"] is None


# --- display layer renders unknown ---


def test_monitor_rows_render_unknown():
    from aitbc_cli.commands.analytics import _mb, _num, _single_chain_monitor_rows

    assert _num(None) == "unknown"
    assert _mb(None) == "unknown"
    summary = {
        "chain_id": "bc-2",
        "health_score": 50.0,
        "active_alerts": 0,
        "statistics": {"tps": {"avg": None}, "block_time": {"avg": None}},
        "latest_metrics": {
            "memory_usage_mb": None,
            "disk_usage_mb": None,
            "active_nodes": None,
            "client_count": None,
            "agent_count": None,
        },
    }
    rows = {r["Metric"]: r["Value"] for r in _single_chain_monitor_rows(summary)}
    assert rows["Current TPS"] == "unknown"
    assert rows["Current Block Time"] == "unknown"
    assert rows["Memory Usage"] == "unknown"
    assert rows["Active Nodes"] == "unknown"


# --- persistence across invocations ---


def test_history_persists_across_instances(tmp_path):
    a1 = _analytics(tmp_path)
    for i in range(12):
        a1.metrics_history["bc-2"].append(
            _metrics(tps=10.0 + i * 0.1, timestamp=datetime.now() - timedelta(minutes=i))
        )
    a1._save_history()

    a2 = _analytics(tmp_path)
    assert len(a2.metrics_history["bc-2"]) == 12
    preds = asyncio.run(a2.predict_chain_performance("bc-2", 24))
    assert preds, "predict must work from accumulated cross-invocation samples"
    assert any(p.metric == "tps" for p in preds)


def test_synthetic_rows_are_not_persisted(tmp_path):
    a1 = _analytics(tmp_path)
    for _ in range(12):
        a1.metrics_history["bc-2"].append(_metrics(synthetic=True))
    a1._save_history()
    a2 = _analytics(tmp_path)
    assert len(a2.metrics_history.get("bc-2", ())) == 0


def test_corrupt_history_file_degrades_to_empty(tmp_path):
    (tmp_path / "hist.json").write_text("{not json")
    a = _analytics(tmp_path)
    assert len(a.metrics_history) == 0


# --- collection noise classification ---


class _DeadNodeClient:
    def __init__(self, cfg):
        pass

    async def __aenter__(self):
        raise httpx.ConnectError("All connection attempts failed")

    async def __aexit__(self, *a):
        pass


@pytest.mark.asyncio
async def test_unreachable_nodes_warn_once_not_error_spam(tmp_path, caplog):
    nodes = {
        "aitbc-primary": NodeConfig(id="aitbc-primary", endpoint="http://127.0.0.1:1"),
        "aitbc-secondary": NodeConfig(id="aitbc-secondary", endpoint="http://127.0.0.1:2"),
    }
    a = _analytics(tmp_path, nodes=nodes)
    with (
        patch("aitbc_cli.core.analytics.NodeClient", _DeadNodeClient),
        patch.object(ChainAnalytics, "_collect_from_rpc_fallback", new=AsyncMock(return_value=[])),
        caplog.at_level(logging.WARNING),
    ):
        await a.collect_all_metrics()

    assert a.node_status == {"aitbc-primary": "unreachable", "aitbc-secondary": "unreachable"}
    assert a.last_collect_live is False
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warns) == 1, f"expected one consolidated warning, got: {[r.getMessage() for r in warns]}"
    assert "aitbc-primary" in warns[0].getMessage() and "aitbc-secondary" in warns[0].getMessage()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


class _StatsFailClient:
    """Node answers hosted-chains but every chain's stats endpoint dies."""

    def __init__(self, cfg):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get_hosted_chains(self):
        return [SimpleNamespace(id="bc-2-island-1"), SimpleNamespace(id="bc-2")]

    async def get_chain_stats(self, chain_id):
        raise RuntimeError("Chain head request failed: 503")


@pytest.mark.asyncio
async def test_dead_chain_stats_warn_once(tmp_path, caplog):
    a = _analytics(tmp_path, nodes={"n0": NodeConfig(id="n0", endpoint="http://x/rpc")})
    with (
        patch("aitbc_cli.core.analytics.NodeClient", _StatsFailClient),
        patch.object(ChainAnalytics, "_collect_from_rpc_fallback", new=AsyncMock(return_value=[])),
        caplog.at_level(logging.WARNING),
    ):
        await a.collect_all_metrics()

    assert a.node_status == {"n0": "reachable"}
    assert a.last_collect_live is False
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 1
    assert "bc-2-island-1" in warns[0].getMessage() and "bc-2" in warns[0].getMessage()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


class _LiveClient:
    def __init__(self, cfg):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get_hosted_chains(self):
        return [SimpleNamespace(id="bc-2")]

    async def get_chain_stats(self, chain_id):
        return {
            "block_height": 100,
            "tps": 0.0,
            "avg_block_time": 61.0,
            "active_nodes": 4,
            "expected_block_time": 60.0,
        }

    async def get_node_info(self):
        return {}


@pytest.mark.asyncio
async def test_last_collect_live_reflects_this_pass_only(tmp_path):
    a = _analytics(tmp_path, nodes={"n0": NodeConfig(id="n0", endpoint="http://x/rpc")})
    with patch("aitbc_cli.core.analytics.NodeClient", _LiveClient):
        await a.collect_all_metrics()
    assert a.last_collect_live is True
    assert a.node_status == {"n0": "reachable"}
    # The live row persisted; a later all-dead pass must NOT fall back to
    # synthetic and must report last_collect_live False — while predict
    # history (has_live_metrics) still sees the persisted live row.
    a2 = _analytics(tmp_path, nodes={"dead": NodeConfig(id="dead", endpoint="http://127.0.0.1:1")})
    with (
        patch("aitbc_cli.core.analytics.NodeClient", _DeadNodeClient),
        patch.object(ChainAnalytics, "_collect_from_rpc_fallback", new=AsyncMock(return_value=[])),
    ):
        await a2.collect_all_metrics()
    assert a2.last_collect_live is False
    assert a2.has_live_metrics() is True
