"""ANALYTICS-NODECFG-STALE-1 (#2219): stale multichain registry must not
silently produce fake analytics or look like live fleet state.

Covers:
- ``ChainAnalytics`` marks local-RPC-fallback metrics ``synthetic`` and never
  derives alerts / health scores / predictions / recommendations from them.
- ``node_status`` records per-node reachability for honest "no sources"
  reporting.
- ``get_cross_chain_analysis`` returns ``{}`` instead of fabricated totals.
- ``aitbc node list`` probes endpoints, flags unreachable rows, warns when
  nothing answers, and shows the live local node from ``/rpc/network-info``.
- ``aitbc analytics alerts`` says "no reachable sources" instead of the
  misleading "No alerts found" when nothing live was collected.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aitbc_cli.core.analytics import ChainAnalytics, ChainMetrics
from aitbc_cli.core.config import MultiChainConfig, NodeConfig


def _metrics(chain_id="c1", node_id="n1", synthetic=False, age_minutes=0):
    return ChainMetrics(
        chain_id=chain_id,
        node_id=node_id,
        timestamp=datetime.now() - timedelta(minutes=age_minutes),
        block_height=100,
        tps=15.0,
        avg_block_time=3.0,
        gas_price=1,
        memory_usage_mb=256.0,
        disk_usage_mb=1024.0,
        active_nodes=5,
        client_count=10,
        miner_count=2,
        agent_count=2,
        network_in_mb=1.0,
        network_out_mb=1.0,
        synthetic=synthetic,
    )


def _analytics(nodes=None):
    config = MultiChainConfig(nodes=nodes or {})
    return ChainAnalytics(config)


class TestSyntheticFallback:
    """The local-RPC fallback window is synthetic: labelled, alert-free."""

    def test_fallback_metrics_are_synthetic_and_alert_free(self):
        analytics = _analytics()

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"chain_id": "ait-test", "height": 42, "genesis_params": {}}

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def get(self, url):
                return _Resp()

        with patch("aitbc_cli.core.analytics.httpx") as mock_httpx:
            mock_httpx.AsyncClient = _Client
            metrics = asyncio.run(analytics._collect_from_rpc_fallback())

        assert metrics, "fallback should produce the synthetic window"
        assert all(m.synthetic for m in metrics)
        assert analytics.rpc_fallback_used is True
        assert analytics.alerts == [], "synthetic rows must not fabricate alerts"
        assert analytics.health_scores == {}, "synthetic rows must not fabricate health scores"
        assert analytics.has_live_metrics() is False

    def test_fallback_failure_leaves_no_flag(self):
        import httpx

        analytics = _analytics()

        class _HttpFail:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def get(self, url):
                raise httpx.ConnectError("refused")

        with patch("aitbc_cli.core.analytics.httpx") as mock_httpx:
            mock_httpx.AsyncClient = _HttpFail
            result = asyncio.run(analytics._collect_from_rpc_fallback())

        assert result == []
        assert analytics.rpc_fallback_used is False


class TestNodeStatusTracking:
    def test_unreachable_node_recorded(self):
        analytics = _analytics({"dead": NodeConfig(id="dead", endpoint="http://127.0.0.1:1")})

        class _DeadClient:
            def __init__(self, cfg):
                pass

            async def __aenter__(self):
                import httpx

                raise httpx.ConnectError("refused")

            async def __aexit__(self, *a):
                pass

        with (
            patch("aitbc_cli.core.analytics.NodeClient", _DeadClient),
            patch.object(ChainAnalytics, "_collect_from_rpc_fallback", AsyncMock(return_value=[])),
        ):
            asyncio.run(analytics.collect_all_metrics())

        assert analytics.node_status == {"dead": "unreachable"}
        assert analytics.has_live_metrics() is False

    def test_reachable_node_with_no_chains_recorded(self):
        analytics = _analytics({"ok": NodeConfig(id="ok", endpoint="http://127.0.0.1:8202")})

        class _OkClient:
            def __init__(self, cfg):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def get_hosted_chains(self):
                return []

        with (
            patch("aitbc_cli.core.analytics.NodeClient", _OkClient),
            patch.object(ChainAnalytics, "_collect_from_rpc_fallback", AsyncMock(return_value=[])),
        ):
            asyncio.run(analytics.collect_all_metrics())

        assert analytics.node_status == {"ok": "reachable"}


class TestLiveMetricsGating:
    def test_synthetic_only_chain_gets_no_predictions_or_recommendations(self):
        analytics = _analytics()
        for i in range(12):
            analytics.metrics_history["c1"].append(_metrics(synthetic=True, age_minutes=11 - i))

        assert analytics.has_live_metrics() is False
        assert asyncio.run(analytics.predict_chain_performance("c1", 24)) == []
        assert analytics.get_optimization_recommendations("c1") == []

    def test_live_metrics_unlock_predictions_path(self):
        analytics = _analytics()
        for i in range(12):
            analytics.metrics_history["c1"].append(_metrics(synthetic=False, age_minutes=11 - i))

        assert analytics.has_live_metrics() is True
        # predictions need >= 10 points — live rows now qualify
        preds = asyncio.run(analytics.predict_chain_performance("c1", 24))
        assert isinstance(preds, list)

    def test_mixed_history_counts_as_live(self):
        analytics = _analytics()
        analytics.metrics_history["c1"].append(_metrics(synthetic=True))
        analytics.metrics_history["c1"].append(_metrics(synthetic=False))
        assert analytics.has_live_metrics() is True


class TestCrossChainAnalysisHonesty:
    def test_empty_history_returns_empty_not_fabricated(self):
        analytics = _analytics()
        assert analytics.get_cross_chain_analysis() == {}

    def test_summary_marks_synthetic_source(self):
        analytics = _analytics()
        analytics.metrics_history["c1"].append(_metrics(synthetic=True))
        summary = analytics.get_chain_performance_summary("c1", 24)
        assert summary["data_source"] == "synthetic"

    def test_summary_marks_live_source(self):
        analytics = _analytics()
        analytics.metrics_history["c1"].append(_metrics(synthetic=False))
        summary = analytics.get_chain_performance_summary("c1", 24)
        assert summary["data_source"] == "live"


class _NoLiveAnalytics:
    """ChainAnalytics double: collection ran, nothing live answered."""

    def __init__(self, config):
        self.alerts = []
        self.node_status = {"aitbc-primary": "unreachable", "local-rpc": "unreachable"}
        self.metrics_history = {}

    async def collect_all_metrics(self):
        return {}

    def has_live_metrics(self):
        return False


class _LiveNoAlertsAnalytics(_NoLiveAnalytics):
    def has_live_metrics(self):
        return True


class TestNodeListCommand:
    def _config(self):
        return MultiChainConfig(
            nodes={
                "aitbc-primary": NodeConfig(id="aitbc-primary", endpoint="http://127.0.0.1:8082"),
                "local-rpc": NodeConfig(id="local-rpc", endpoint="http://127.0.0.1:8202"),
            }
        )

    def test_all_unreachable_warns_stale(self, runner):
        from aitbc_cli.commands.node import node

        with (
            patch("aitbc_cli.commands.node.main.load_multichain_config", return_value=self._config()),
            patch("aitbc_cli.commands.node.main.probe_nodes", AsyncMock(return_value={"aitbc-primary": False, "local-rpc": False})),
            patch("aitbc_cli.commands.node.main._live_local_node", return_value=None),
        ):
            result = runner.invoke(node, ["list"], obj={"output_format": "table"})

        assert result.exit_code == 0, result.output
        assert "unreachable" in result.output
        assert "may be stale" in result.output
        assert "aitbc network peers" in result.output

    def test_mixed_reachability_marks_rows(self, runner):
        from aitbc_cli.commands.node import node

        with (
            patch("aitbc_cli.commands.node.main.load_multichain_config", return_value=self._config()),
            patch("aitbc_cli.commands.node.main.probe_nodes", AsyncMock(return_value={"aitbc-primary": False, "local-rpc": True})),
            patch("aitbc_cli.commands.node.main._live_local_node", return_value=None),
        ):
            result = runner.invoke(node, ["list"], obj={"output_format": "table"})

        assert result.exit_code == 0, result.output
        assert "reachable" in result.output
        assert "unreachable" in result.output
        assert "may be stale" in result.output  # partial staleness still warned

    def test_no_probe_skips_status_column(self, runner):
        from aitbc_cli.commands.node import node

        probe = AsyncMock(return_value={})
        with (
            patch("aitbc_cli.commands.node.main.load_multichain_config", return_value=self._config()),
            patch("aitbc_cli.commands.node.main.probe_nodes", probe),
            patch("aitbc_cli.commands.node.main._live_local_node", return_value=None),
        ):
            result = runner.invoke(node, ["list", "--no-probe"], obj={"output_format": "table"})

        assert result.exit_code == 0, result.output
        probe.assert_not_called()
        assert "Status" not in result.output

    def test_live_local_node_shown(self, runner):
        from aitbc_cli.commands.node import node

        live = {"node_id": "node0", "role": "customer", "chain_id": "ait-island-1", "island_id": "i1", "endpoint": "http://127.0.0.1:8202/rpc"}
        with (
            patch("aitbc_cli.commands.node.main.load_multichain_config", return_value=self._config()),
            patch("aitbc_cli.commands.node.main.probe_nodes", AsyncMock(return_value={"aitbc-primary": True, "local-rpc": True})),
            patch("aitbc_cli.commands.node.main._live_local_node", return_value=live),
        ):
            result = runner.invoke(node, ["list"], obj={"output_format": "table"})

        assert result.exit_code == 0, result.output
        assert "Live local node" in result.output
        assert "node0" in result.output


class TestAnalyticsAlertsHonesty:
    def test_no_live_sources_reports_honestly(self, runner):
        from aitbc_cli.commands.analytics import analytics

        with (
            patch("aitbc_cli.commands.analytics.load_multichain_config", return_value=MultiChainConfig()),
            patch("aitbc_cli.commands.analytics.ChainAnalytics", _NoLiveAnalytics),
        ):
            result = runner.invoke(analytics, ["alerts"], obj={"output_format": "table"})

        assert result.exit_code == 0, result.output
        assert "No alerts evaluated" in result.output
        assert "no reachable node sources" in result.output
        assert "aitbc-primary" in result.output  # unreachable names surfaced
        assert "No alerts found" not in result.output

    def test_live_sources_with_no_alerts_still_says_no_alerts(self, runner):
        from aitbc_cli.commands.analytics import analytics

        with (
            patch("aitbc_cli.commands.analytics.load_multichain_config", return_value=MultiChainConfig()),
            patch("aitbc_cli.commands.analytics.ChainAnalytics", _LiveNoAlertsAnalytics),
        ):
            result = runner.invoke(analytics, ["alerts"], obj={"output_format": "table"})

        assert result.exit_code == 0, result.output
        assert "No alerts found" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
