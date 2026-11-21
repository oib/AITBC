"""
Chain analytics and monitoring system
"""

import asyncio
import json
import os
import random
import statistics
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from aitbc_cli.core.config import MultiChainConfig, NodeConfig
from aitbc_cli.core.node_client import NodeClient

from aitbc import get_logger

logger = get_logger(__name__)

# Failure surface for the NodeClient/httpx collection paths plus the in-memory
# stats arithmetic (TypeError/ValueError/ArithmeticError on bad metrics).
_COLLECT_ERRORS = (
    httpx.HTTPError,
    RuntimeError,
    TypeError,
    ValueError,
    KeyError,
    AttributeError,
    ArithmeticError,
)


@dataclass
class ChainMetrics:
    """Chain performance metrics"""

    chain_id: str
    node_id: str
    timestamp: datetime
    block_height: int
    # Measured fields are Optional: ``None`` means "the source did not
    # report this" (e.g. the chain RPC publishes no memory/disk/host
    # telemetry), which must surface as unknown — never as a fabricated 0
    # that feeds alerts, recommendations, or health scores (#2412).
    tps: float | None
    avg_block_time: float | None
    gas_price: int | None
    memory_usage_mb: float | None
    disk_usage_mb: float | None
    active_nodes: int | None
    client_count: int | None
    miner_count: int | None
    agent_count: int | None
    network_in_mb: float | None
    network_out_mb: float | None
    # True when the row comes from the synthetic local-RPC fallback rather
    # than a real node metrics endpoint — synthetic rows must never feed
    # alerts, health scores, predictions, or recommendations (#2219).
    synthetic: bool = False
    # Configured block interval reported by the node (PBFT/PoA chains run
    # ~60s blocks by design). 0 means unknown — block-time alerts and the
    # health score then fall back to the flat PoW-era thresholds (#2412).
    expected_block_time: float = 0.0


@dataclass
class ChainAlert:
    """Chain performance alert"""

    chain_id: str
    alert_type: str
    severity: str
    message: str
    timestamp: datetime
    threshold: float
    current_value: float


@dataclass
class ChainPrediction:
    """Chain performance prediction"""

    chain_id: str
    metric: str
    predicted_value: float
    confidence: float
    time_horizon_hours: int
    created_at: datetime


class ChainAnalytics:
    """Advanced chain analytics and monitoring"""

    def __init__(self, config: MultiChainConfig):
        self.config = config
        self.metrics_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.alerts: list[ChainAlert] = []
        self.predictions: dict[str, list[ChainPrediction]] = defaultdict(list)
        self.health_scores: dict[str, float] = {}
        self.performance_benchmarks: dict[str, dict[str, float]] = {}
        # Per-node outcome of the last collect_all_metrics() pass:
        # "reachable" when the node answered get_hosted_chains, "unreachable"
        # when it did not. Read by `analytics alerts` to report "no sources"
        # honestly instead of "No alerts found" against dead endpoints (#2219).
        self.node_status: dict[str, str] = {}
        self.rpc_fallback_used = False
        # True when the most recent collect_all_metrics() pass produced at
        # least one live (non-synthetic) row. Distinct from
        # has_live_metrics(), which also counts rows loaded from the
        # persisted history file — alerts must judge THIS run's sources,
        # not yesterday's (#2412).
        self.last_collect_live = False
        # Rolling sample store so `predict` accumulates across CLI
        # invocations instead of restarting from one data point every call
        # (#2412). Synthetic fallback rows are never persisted.
        self._history_file = Path(
            os.environ.get("AITBC_ANALYTICS_HISTORY") or (Path.home() / ".aitbc" / "analytics_metrics.json")
        )
        self._load_history()

        # Alert thresholds
        self.thresholds = {
            "tps_low": 1.0,
            "tps_high": 100.0,
            "block_time_high": 10.0,
            "memory_usage_high": 80.0,  # percentage
            "disk_usage_high": 85.0,  # percentage
            "node_count_low": 1,
            "client_count_low": 5,
        }

    async def collect_metrics(self, chain_id: str, node_id: str) -> ChainMetrics:
        """Collect metrics for a specific chain"""
        if node_id not in self.config.nodes:
            raise ValueError(f"Node {node_id} not configured")

        node_config = self.config.nodes[node_id]

        try:
            async with NodeClient(node_config) as client:
                chain_stats = await client.get_chain_stats(chain_id)
                node_info = await client.get_node_info()

                metrics = ChainMetrics(
                    chain_id=chain_id,
                    node_id=node_id,
                    timestamp=datetime.now(),
                    block_height=chain_stats.get("block_height", 0),
                    # Absent keys stay None — the RPC simply does not
                    # measure them; a 0 here would be a fabricated zero
                    # (#2412).
                    tps=chain_stats.get("tps"),
                    avg_block_time=chain_stats.get("avg_block_time"),
                    gas_price=chain_stats.get("gas_price"),
                    memory_usage_mb=chain_stats.get("memory_usage_mb"),
                    disk_usage_mb=chain_stats.get("disk_usage_mb"),
                    active_nodes=chain_stats.get("active_nodes"),
                    client_count=chain_stats.get("client_count"),
                    miner_count=chain_stats.get("miner_count"),
                    agent_count=chain_stats.get("agent_count"),
                    network_in_mb=node_info.get("network_in_mb"),
                    network_out_mb=node_info.get("network_out_mb"),
                    expected_block_time=float(chain_stats.get("expected_block_time") or 0.0),
                )

                # Store metrics history
                self.metrics_history[chain_id].append(metrics)
                self._save_history()

                # Check for alerts
                await self._check_alerts(metrics)

                # Update health score
                self._calculate_health_score(chain_id)

                return metrics

        except _COLLECT_ERRORS as e:
            # Debug, not error: collect_all_metrics() classifies per-chain
            # failures into one consolidated warning — a per-call error line
            # per dead chain reads as command failure on an exit-0 partial
            # success (#2412, same pattern as #2424).
            logger.debug("Error collecting metrics for chain %s: %s", chain_id, e)
            raise

    async def _collect_from_rpc_fallback(self) -> list[ChainMetrics]:
        """Collect metrics from the local blockchain RPC when no multichain nodes are configured."""
        try:
            from ..config import get_config

            config = get_config()
            rpc_url = getattr(config, "blockchain_rpc_url", "http://127.0.0.1:8202").rstrip("/")
        except Exception as e:  # noqa: BLE001 - analytics is best-effort; default RPC fallback
            logger.debug("config load failed, using default rpc url: %s", type(e).__name__)
            rpc_url = "http://127.0.0.1:8202"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{rpc_url}/rpc/info")
                resp.raise_for_status()
                info = resp.json()
        except _COLLECT_ERRORS as e:
            logger.warning("Failed to collect metrics from blockchain RPC: %s", e)
            return []
        self.rpc_fallback_used = True

        chain_id = info.get("chain_id") or os.environ.get("CHAIN_ID") or "unconfigured"
        block_height = info.get("height", 0)

        # Synthesise a short historical window so summary/predict/optimize/alerts all have data.
        metrics: list[ChainMetrics] = []
        now = datetime.now()
        for i in range(12):
            ts = now - timedelta(minutes=(11 - i) * 5)
            noise = random.uniform(-0.2, 0.2)
            tps = max(0.0, 0.5 + noise) if i == 0 else max(0.0, 15.5 + noise)
            block_time = max(1.0, 3.2 + noise * 0.5)
            gas_price = int(info.get("genesis_params", {}).get("default_gas_price", 20000000000) or 20000000000)
            memory_mb = 256.0 + noise * 10
            metrics.append(
                ChainMetrics(
                    chain_id=chain_id,
                    node_id="local-rpc",
                    timestamp=ts,
                    block_height=block_height - (11 - i),
                    tps=tps,
                    avg_block_time=block_time,
                    gas_price=gas_price,
                    memory_usage_mb=memory_mb,
                    disk_usage_mb=10240.0 + noise * 100,
                    active_nodes=5,
                    client_count=25,
                    miner_count=8,
                    agent_count=8,
                    network_in_mb=10.5 + noise,
                    network_out_mb=8.2 + noise,
                    synthetic=True,
                )
            )

        # Synthetic rows carry no alerts or health score: deriving either
        # from invented tps/block-time values would fabricate alerts the
        # operator cannot act on (#2219). They exist only so summary/monitor
        # can still show that *something* answered.
        for m in metrics:
            self.metrics_history[chain_id].append(m)

        return metrics

    # Rows kept per chain in the persisted sample file — enough for
    # predict's >=10-point window with headroom, small enough to stay a
    # few hundred KB (#2412).
    _HISTORY_SAVE_LIMIT = 500

    def _load_history(self) -> None:
        """Restore persisted metrics samples from the previous CLI runs.

        Each ``aitbc analytics`` invocation is a fresh process; without a
        on-disk sample store ``predict`` could never accumulate the >=10
        points it needs (#2412). Corrupt or partial files degrade to an
        empty history rather than failing the command.
        """
        try:
            raw = json.loads(self._history_file.read_text())
        except (OSError, ValueError):
            return
        chains = raw.get("chains") if isinstance(raw, dict) else None
        if not isinstance(chains, dict):
            return
        for chain_id, rows in chains.items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                try:
                    if not isinstance(row, dict):
                        continue
                    row = dict(row)
                    row["timestamp"] = datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00"))
                    self.metrics_history[chain_id].append(ChainMetrics(**row))
                except (TypeError, ValueError, KeyError):
                    logger.debug("dropping unreadable analytics history row for %s", chain_id)

    def _save_history(self) -> None:
        """Persist live (non-synthetic) metrics samples for future runs.

        Synthetic local-RPC fallback rows are excluded: they are invented
        window dressing, and persisting them would let fake data accumulate
        across calls. Writes are atomic (tmp + replace) and skipped entirely
        when there is nothing worth keeping.
        """
        chains: dict[str, list[dict[str, Any]]] = {}
        for chain_id, rows in self.metrics_history.items():
            live = [m for m in rows if not m.synthetic]
            if not live:
                continue
            kept = live[-self._HISTORY_SAVE_LIMIT :]
            chains[chain_id] = [{**asdict(m), "timestamp": m.timestamp.isoformat()} for m in kept]
        if not chains:
            return
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._history_file.with_suffix(self._history_file.suffix + ".tmp")
            tmp.write_text(json.dumps({"version": 1, "chains": chains}))
            os.replace(tmp, self._history_file)
        except OSError as e:
            logger.debug("could not persist analytics history: %s", e)

    def _resolve_chain_id(self, chain_id: str) -> str | None:
        """Resolve a partial chain id (e.g. "ait-hub") to a known full chain id."""
        if chain_id in self.metrics_history:
            return chain_id
        for key in self.metrics_history:
            if key.endswith(chain_id) or chain_id in key:
                return key
        return None

    async def collect_all_metrics(self) -> dict[str, list[ChainMetrics]]:
        """Collect metrics for all chains across all nodes"""
        all_metrics: dict[str, list[ChainMetrics]] = {}
        unreachable_nodes: list[str] = []
        failed_chains: list[str] = []

        tasks = [
            self._collect_node_metrics(node_id, node_config, unreachable_nodes, failed_chains)
            for node_id, node_config in self.config.nodes.items()
        ]

        results = await asyncio.gather(*tasks)

        for node_metrics in results:
            for metrics in node_metrics:
                if metrics.chain_id not in all_metrics:
                    all_metrics[metrics.chain_id] = []
                all_metrics[metrics.chain_id].append(metrics)

        self._report_collection_failures(unreachable_nodes, failed_chains)

        # Fresh-live flag for this pass only — persisted history must not
        # make a fully-dead run look measured (#2412).
        self.last_collect_live = bool(all_metrics)

        if not all_metrics and not self.has_live_metrics():
            await self._collect_from_rpc_fallback()

        return all_metrics

    async def _collect_node_metrics(
        self,
        node_id: str,
        node_config: NodeConfig,
        unreachable_nodes: list[str],
        failed_chains: list[str],
    ) -> list[ChainMetrics]:
        """Collect every hosted chain's metrics from one node.

        Per-node and per-chain failures are recorded into the shared lists
        for one consolidated report — never raised, so one bad node or one
        dead chain (e.g. a ``supported_chains`` entry whose ``/head`` route
        503s) cannot hide the rest (#2412).
        """
        try:
            async with NodeClient(node_config) as client:
                chains = await client.get_hosted_chains()
        except _COLLECT_ERRORS as e:
            self.node_status[node_id] = "unreachable"
            # Debug here; the consolidated warning below carries the signal —
            # per-node error lines on every call read as command failure even
            # though sibling nodes answered (#2424 pattern, #2412).
            logger.debug("Node %s did not answer the hosted-chains query: %s", node_id, e)
            unreachable_nodes.append(node_id)
            return []
        self.node_status[node_id] = "reachable"
        node_metrics = []
        for chain in chains:
            try:
                metrics = await self.collect_metrics(chain.id, node_id)
                node_metrics.append(metrics)
            except _COLLECT_ERRORS as e:
                failed_chains.append(f"{chain.id} (node {node_id})")
                logger.debug("No metrics for chain %s on node %s: %s", chain.id, node_id, e)
        return node_metrics

    @staticmethod
    def _report_collection_failures(unreachable_nodes: list[str], failed_chains: list[str]) -> None:
        """One consolidated warning per failure class per call (#2424 shape)."""
        if unreachable_nodes:
            logger.warning(
                "Skipped %d configured node(s) that did not respond: %s",
                len(unreachable_nodes),
                ", ".join(unreachable_nodes),
            )
        if failed_chains:
            logger.warning(
                "Skipped %d chain(s) whose stats did not respond: %s",
                len(failed_chains),
                ", ".join(failed_chains),
            )

    def _chain_has_live_metrics(self, chain_id: str) -> bool:
        """True when the chain has at least one non-synthetic metrics row."""
        return any(not m.synthetic for m in self.metrics_history.get(chain_id, ()))

    def has_live_metrics(self) -> bool:
        """True when any chain has real (non-synthetic) metrics rows."""
        return any(self._chain_has_live_metrics(cid) for cid in self.metrics_history)

    def get_chain_performance_summary(self, chain_id: str, hours: int = 24) -> dict[str, Any]:
        """Get performance summary for a chain"""
        resolved = self._resolve_chain_id(chain_id)
        if not resolved:
            return {}
        chain_id = resolved

        # Filter metrics by time range
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_metrics = [m for m in self.metrics_history[chain_id] if m.timestamp >= cutoff_time]

        if not recent_metrics:
            return {}

        # Calculate statistics — None (unmeasured) values are excluded per
        # metric; a metric nothing reported yields None stats, which callers
        # must render as "unknown", not 0 (#2412).
        tps_values = [m.tps for m in recent_metrics]
        block_time_values = [m.avg_block_time for m in recent_metrics]
        gas_prices = [m.gas_price for m in recent_metrics]

        summary = {
            "chain_id": chain_id,
            "time_range_hours": hours,
            "data_points": len(recent_metrics),
            "latest_metrics": asdict(recent_metrics[-1]),
            "statistics": {
                "tps": self._metric_stats(tps_values),
                "block_time": self._metric_stats(block_time_values),
                "gas_price": self._metric_stats(gas_prices),
            },
            "health_score": self.health_scores.get(chain_id, 0.0),
            "active_alerts": len([a for a in self.alerts if a.chain_id == chain_id]),
            # Honest provenance: "synthetic" rows come from the local-RPC
            # fallback window, not a node metrics endpoint (#2219).
            "data_source": "synthetic" if recent_metrics[-1].synthetic else "live",
        }

        return summary

    @staticmethod
    def _metric_stats(values: list[Any]) -> dict[str, float | None]:
        """avg/min/max/median over the measured (non-None) values.

        All-None input returns None stats — "unknown", not a fabricated 0
        (#2412).
        """
        vals = [v for v in values if v is not None]
        if not vals:
            return {"avg": None, "min": None, "max": None, "median": None}
        return {
            "avg": statistics.mean(vals),
            "min": min(vals),
            "max": max(vals),
            "median": statistics.median(vals),
        }

    def get_cross_chain_analysis(self) -> dict[str, Any]:
        """Analyze performance across all chains"""
        if not self.metrics_history:
            # No data is not fabricated data: return empty so callers abort
            # with "No analytics data available" instead of printing invented
            # fleet totals (#2219, same class as the #2222 cluster fix).
            return {}

        analysis: dict[str, Any] = {
            "total_chains": len(self.metrics_history),
            "active_chains": len([c for c in self.metrics_history.keys() if self.health_scores.get(c, 0) > 0.5]),
            "chains_by_type": defaultdict(int),
            "performance_comparison": {},
            "resource_usage": self._resource_usage_totals(),
            "alerts_summary": {
                "total_alerts": len(self.alerts),
                "critical_alerts": len([a for a in self.alerts if a.severity == "critical"]),
                "warning_alerts": len([a for a in self.alerts if a.severity == "warning"]),
            },
        }

        # Analyze each chain
        for chain_id, metrics in self.metrics_history.items():
            if not metrics:
                continue

            latest = metrics[-1]

            # Chain type analysis
            # This would need chain info, using placeholder
            chains_by_type = analysis["chains_by_type"]
            if isinstance(chains_by_type, dict):
                chains_by_type["unknown"] = chains_by_type.get("unknown", 0) + 1

            # Performance comparison
            perf_comp = analysis["performance_comparison"]
            if isinstance(perf_comp, dict):
                perf_comp[chain_id] = {
                    "tps": latest.tps,
                    "block_time": latest.avg_block_time,
                    "health_score": self.health_scores.get(chain_id, 0.0),
                }

        return analysis

    # latest-metric field -> resource_usage key
    _RESOURCE_FIELDS = {
        "total_memory_mb": "memory_usage_mb",
        "total_disk_mb": "disk_usage_mb",
        "total_clients": "client_count",
        "total_agents": "agent_count",
    }

    def _resource_usage_totals(self) -> dict[str, float | int | None]:
        """Fleet resource totals over the latest row of each chain.

        Only *measured* values (non-None) are summed; a metric nothing
        reported stays None ("unknown") rather than totaling to a fake 0 —
        the same fabricated-zero bug at aggregate level (#2412).
        """
        samples: dict[str, list[float | int]] = {key: [] for key in self._RESOURCE_FIELDS}
        for metrics in self.metrics_history.values():
            if not metrics:
                continue
            latest = metrics[-1]
            for total_key, field in self._RESOURCE_FIELDS.items():
                value = getattr(latest, field)
                if value is not None:
                    samples[total_key].append(value)
        return {key: (sum(vals) if vals else None) for key, vals in samples.items()}

    async def predict_chain_performance(self, chain_id: str, hours: int = 24) -> list[ChainPrediction]:
        """Predict chain performance using historical data"""
        resolved = self._resolve_chain_id(chain_id)
        if not resolved:
            return []
        chain_id = resolved
        if len(self.metrics_history[chain_id]) < 10:
            return []
        if not self._chain_has_live_metrics(chain_id):
            # Synthetic fallback rows would produce invented predictions.
            return []

        metrics = list(self.metrics_history[chain_id])

        predictions = []

        # Simple linear regression for TPS prediction — unmeasured (None)
        # samples are excluded rather than treated as 0 (#2412).
        tps_values = [m.tps for m in metrics if m.tps is not None]
        if len(tps_values) >= 10:
            # Calculate trend
            recent_tps = tps_values[-5:]
            older_tps = tps_values[-10:-5]

            if len(recent_tps) > 0 and len(older_tps) > 0:
                recent_avg = statistics.mean(recent_tps)
                older_avg = statistics.mean(older_tps)
                trend = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0

                predicted_tps = recent_avg * (1 + trend * (hours / 24))
                confidence = max(0.1, 1.0 - abs(trend))  # Higher confidence for stable trends

                predictions.append(
                    ChainPrediction(
                        chain_id=chain_id,
                        metric="tps",
                        predicted_value=predicted_tps,
                        confidence=confidence,
                        time_horizon_hours=hours,
                        created_at=datetime.now(),
                    )
                )

        # Memory usage prediction
        memory_values = [m.memory_usage_mb for m in metrics if m.memory_usage_mb is not None]
        if len(memory_values) >= 10:
            recent_memory = memory_values[-5:]
            older_memory = memory_values[-10:-5]

            if len(recent_memory) > 0 and len(older_memory) > 0:
                recent_avg = statistics.mean(recent_memory)
                older_avg = statistics.mean(older_memory)
                growth_rate = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0

                predicted_memory = recent_avg * (1 + growth_rate * (hours / 24))
                confidence = max(0.1, 1.0 - abs(growth_rate))

                predictions.append(
                    ChainPrediction(
                        chain_id=chain_id,
                        metric="memory_usage_mb",
                        predicted_value=predicted_memory,
                        confidence=confidence,
                        time_horizon_hours=hours,
                        created_at=datetime.now(),
                    )
                )

        # Store predictions
        self.predictions[chain_id].extend(predictions)

        return predictions

    def get_optimization_recommendations(self, chain_id: str) -> list[dict[str, Any]]:
        """Get optimization recommendations for a chain"""
        recommendations: list[dict[str, Any]] = []

        resolved = self._resolve_chain_id(chain_id)
        if not resolved:
            return recommendations
        chain_id = resolved

        metrics = list(self.metrics_history[chain_id])
        if not metrics or not self._chain_has_live_metrics(chain_id):
            # Recommendations from synthetic fallback rows would be invented.
            return recommendations

        latest = metrics[-1]

        # TPS optimization — unmeasured metrics produce no recommendation:
        # "Low TPS: unknown" is not actionable (#2412).
        if latest.tps is not None and latest.tps < self.thresholds["tps_low"]:
            recommendations.append(
                {
                    "type": "performance",
                    "priority": "high",
                    "issue": "Low TPS",
                    "current_value": latest.tps,
                    "recommended_action": "Consider increasing block size or optimizing smart contracts",
                    "expected_improvement": "20-50% TPS increase",
                }
            )

        # Block time optimization — chains with a configured interval are
        # judged against 1.5× their target; others keep the flat 3s bar (#2412).
        block_ceiling = max(3.0, latest.expected_block_time * 1.5) if latest.expected_block_time > 0 else 3.0
        if latest.avg_block_time is not None and latest.avg_block_time > block_ceiling:
            recommendations.append(
                {
                    "type": "performance",
                    "priority": "medium",
                    "issue": "High block time",
                    "current_value": latest.avg_block_time,
                    "recommended_action": "Optimize consensus parameters or increase validator count",
                    "expected_improvement": "30-60% block time reduction",
                }
            )

        # Memory usage optimization
        if latest.memory_usage_mb is not None and latest.memory_usage_mb > 150.0:
            recommendations.append(
                {
                    "type": "resource",
                    "priority": "medium",
                    "issue": "High memory usage",
                    "current_value": latest.memory_usage_mb,
                    "recommended_action": "Implement data pruning or increase node memory",
                    "expected_improvement": "40-70% memory usage reduction",
                }
            )

        # Node count optimization — only a *measured* low count recommends
        # adding nodes; an unreported count is unknown, not zero (#2412).
        if latest.active_nodes is not None and latest.active_nodes < 3:
            recommendations.append(
                {
                    "type": "availability",
                    "priority": "high",
                    "issue": "Low node count",
                    "current_value": latest.active_nodes,
                    "recommended_action": "Add more nodes to improve network resilience",
                    "expected_improvement": "Improved fault tolerance and sync speed",
                }
            )

        return recommendations

    async def _check_alerts(self, metrics: ChainMetrics):
        """Check for performance alerts"""
        alerts = []

        # Every check is guarded on the metric being *measured*: None means
        # the source did not report the field, and alerting on an absent
        # value is exactly the fabricated-zero bug #2412 removes. Policy:
        # fail-open on missing data, fail-closed on measured data — a real
        # measured 0 still alerts.

        # TPS alerts
        if metrics.tps is not None and metrics.tps < self.thresholds["tps_low"]:
            alerts.append(
                ChainAlert(
                    chain_id=metrics.chain_id,
                    alert_type="tps_low",
                    severity="warning",
                    message=f"Low TPS detected: {metrics.tps:.2f}",
                    timestamp=metrics.timestamp,
                    threshold=self.thresholds["tps_low"],
                    current_value=metrics.tps,
                )
            )

        # Block time alerts — PBFT/PoA chains have a configured interval
        # (~60s) that makes the flat 10s PoW-era threshold meaningless; only
        # flag blocks running >50% slower than the chain's own target (#2412).
        block_time_ceiling = self._block_time_ceiling(metrics)
        if metrics.avg_block_time is not None and metrics.avg_block_time > block_time_ceiling:
            alerts.append(
                ChainAlert(
                    chain_id=metrics.chain_id,
                    alert_type="block_time_high",
                    severity="warning",
                    message=f"High block time: {metrics.avg_block_time:.2f}s",
                    timestamp=metrics.timestamp,
                    threshold=block_time_ceiling,
                    current_value=metrics.avg_block_time,
                )
            )

        # Memory usage alerts
        if metrics.memory_usage_mb is not None and metrics.memory_usage_mb > 2000:  # 2GB threshold
            alerts.append(
                ChainAlert(
                    chain_id=metrics.chain_id,
                    alert_type="memory_high",
                    severity="critical",
                    message=f"High memory usage: {metrics.memory_usage_mb:.1f}MB",
                    timestamp=metrics.timestamp,
                    threshold=2000,
                    current_value=metrics.memory_usage_mb,
                )
            )

        # Node count alerts — None (unreadable, e.g. /network-info exposed
        # no validator list) is unknown, NOT zero: the false "Low node
        # count: 0" critical against a live 4-validator chain was the #2412
        # headline bug. Only a measured count below threshold fires.
        if metrics.active_nodes is not None and metrics.active_nodes < self.thresholds["node_count_low"]:
            alerts.append(
                ChainAlert(
                    chain_id=metrics.chain_id,
                    alert_type="node_count_low",
                    severity="critical",
                    message=f"Low node count: {metrics.active_nodes}",
                    timestamp=metrics.timestamp,
                    threshold=self.thresholds["node_count_low"],
                    current_value=metrics.active_nodes,
                )
            )

        # Add to alerts list
        self.alerts.extend(alerts)

        # Keep only recent alerts (last 24 hours)
        cutoff_time = datetime.now() - timedelta(hours=24)
        self.alerts = [a for a in self.alerts if a.timestamp >= cutoff_time]

    def _block_time_ceiling(self, metrics: ChainMetrics) -> float:
        """Block-time ceiling for alerts/recommendations.

        Chains that report a configured interval (``expected_block_time``)
        are judged against 1.5× that target — a PBFT chain idling at its
        ~60s design interval is healthy, not "high". Unknown target falls
        back to the flat threshold (#2412).
        """
        if metrics.expected_block_time > 0:
            return max(self.thresholds["block_time_high"], metrics.expected_block_time * 1.5)
        return self.thresholds["block_time_high"]

    def _calculate_health_score(self, chain_id: str):
        """Calculate health score for a chain"""
        if chain_id not in self.metrics_history:
            self.health_scores[chain_id] = 0.0
            return

        metrics = list(self.metrics_history[chain_id])
        if not metrics:
            self.health_scores[chain_id] = 0.0
            return

        latest = metrics[-1]

        # Health score components (0-100). Unmeasured fields (None) drop
        # out of the weighted average and the remaining weights renormalize
        # — a chain the RPC cannot introspect is scored on what IS known,
        # not penalized for telemetry it never publishes (#2412).
        components: list[tuple[float, float]] = []

        if latest.tps is not None:
            components.append((max(0.0, min(100, (latest.tps / 10) * 100)), 0.3))  # 10 TPS = 100% score
        if latest.avg_block_time is not None:
            if latest.expected_block_time > 0:
                # Score against the chain's configured interval, not the PoW-era 5s.
                components.append(
                    (
                        max(
                            0.0,
                            min(100.0, (latest.expected_block_time / max(latest.avg_block_time, 1.0)) * 100),
                        ),
                        0.3,
                    )
                )
            else:
                components.append((max(0, 100 - (latest.avg_block_time - 5) * 10), 0.3))  # 5s = 100% score
        if latest.active_nodes is not None:
            components.append((min(100, (latest.active_nodes / 5) * 100), 0.3))  # 5 nodes = 100% score
        if latest.memory_usage_mb is not None:
            components.append((max(0, 100 - (latest.memory_usage_mb / 1000) * 50), 0.1))  # 1GB = 50% penalty

        if not components:
            self.health_scores[chain_id] = 0.0
            return

        total_weight = sum(weight for _, weight in components)
        health_score = sum(score * weight for score, weight in components) / total_weight

        self.health_scores[chain_id] = max(0, min(100, health_score))

    def get_dashboard_data(self) -> dict[str, Any]:
        """Get data for analytics dashboard"""
        dashboard: dict[str, Any] = {
            "overview": self.get_cross_chain_analysis(),
            "chain_summaries": {},
            "alerts": [asdict(alert) for alert in self.alerts[-20:]],  # Last 20 alerts
            "predictions": {},
            "recommendations": {},
        }

        # Chain summaries
        for chain_id in self.metrics_history.keys():
            chain_summaries = dashboard["chain_summaries"]
            if isinstance(chain_summaries, dict):
                chain_summaries[chain_id] = self.get_chain_performance_summary(chain_id, 24)
            recommendations = dashboard["recommendations"]
            if isinstance(recommendations, dict):
                recommendations[chain_id] = self.get_optimization_recommendations(chain_id)

            # Latest predictions
            if chain_id in self.predictions:
                dashboard["predictions"][chain_id] = [asdict(pred) for pred in self.predictions[chain_id][-5:]]

        return dashboard
