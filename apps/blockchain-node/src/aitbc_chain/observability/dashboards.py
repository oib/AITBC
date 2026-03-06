"""Generate Grafana dashboards for the devnet observability stack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable


def _timeseries_panel(
    panel_id: int,
    title: str,
    expr: str,
    grid_x: int,
    grid_y: int,
    datasource_uid: str,
) -> Dict[str, object]:
    return {
        "datasource": {"type": "prometheus", "uid": datasource_uid},
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "green", "value": None},
                        {"color": "red", "value": 80},
                    ],
                },
            },
            "overrides": [],
        },
        "gridPos": {"h": 8, "w": 12, "x": grid_x, "y": grid_y},
        "id": panel_id,
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi", "sort": "none"},
        },
        "targets": [
            {
                "datasource": {"type": "prometheus", "uid": datasource_uid},
                "expr": expr,
                "refId": "A",
            }
        ],
        "title": title,
        "type": "timeseries",
    }


def _stat_panel(
    panel_id: int,
    title: str,
    expr: str,
    grid_x: int,
    grid_y: int,
    datasource_uid: str,
) -> Dict[str, object]:
    return {
        "datasource": {"type": "prometheus", "uid": datasource_uid},
        "fieldConfig": {
            "defaults": {
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "green", "value": None},
                        {"color": "orange", "value": 5},
                        {"color": "red", "value": 10},
                    ],
                },
            },
            "overrides": [],
        },
        "gridPos": {"h": 4, "w": 6, "x": grid_x, "y": grid_y},
        "id": panel_id,
        "options": {
            "colorMode": "value",
            "graphMode": "none",
            "justifyMode": "auto",
            "orientation": "horizontal",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": "auto",
        },
        "targets": [
            {
                "datasource": {"type": "prometheus", "uid": datasource_uid},
                "expr": expr,
                "refId": "A",
            }
        ],
        "title": title,
        "type": "stat",
    }


def _coordinator_dashboard(datasource_uid: str) -> Dict[str, object]:
    return {
        "uid": "aitbc-coordinator",
        "title": "AITBC Coordinator Overview",
        "editable": True,
        "tags": ["aitbc", "coordinator"],
        "timezone": "",
        "schemaVersion": 38,
        "version": 1,
        "refresh": "10s",
        "style": "dark",
        "annotations": {"list": []},
        "templating": {"list": []},
        "time": {"from": "now-5m", "to": "now"},
        "timepicker": {},
        "panels": [
            _timeseries_panel(
                panel_id=1,
                title="Jobs Submitted",
                expr="rate(coordinator_jobs_submitted_total[1m])",
                grid_x=0,
                grid_y=0,
                datasource_uid=datasource_uid,
            ),
            _timeseries_panel(
                panel_id=2,
                title="Jobs Completed",
                expr="rate(coordinator_jobs_completed_total[1m])",
                grid_x=12,
                grid_y=0,
                datasource_uid=datasource_uid,
            ),
            _timeseries_panel(
                panel_id=3,
                title="Jobs Failed",
                expr="rate(coordinator_jobs_failed_total[1m])",
                grid_x=0,
                grid_y=8,
                datasource_uid=datasource_uid,
            ),
            _timeseries_panel(
                panel_id=6,
                title="Average Bid Price",
                expr="avg_over_time(coordinator_job_price[5m])",
                grid_x=12,
                grid_y=8,
                datasource_uid=datasource_uid,
            ),
            _stat_panel(
                panel_id=4,
                title="Active Jobs",
                expr="miner_active_jobs",
                grid_x=0,
                grid_y=16,
                datasource_uid=datasource_uid,
            ),
            _stat_panel(
                panel_id=5,
                title="Miner Error Rate",
                expr="miner_error_rate",
                grid_x=6,
                grid_y=16,
                datasource_uid=datasource_uid,
            ),
            _stat_panel(
                panel_id=7,
                title="Avg Compute Units",
                expr="avg_over_time(coordinator_job_compute_units[5m])",
                grid_x=12,
                grid_y=16,
                datasource_uid=datasource_uid,
            ),
        ],
    }


def _node_dashboard(datasource_uid: str) -> Dict[str, object]:
    return {
        "uid": "aitbc-node",
        "title": "AITBC Blockchain Node",
        "editable": True,
        "tags": ["aitbc", "blockchain"],
        "timezone": "",
        "schemaVersion": 38,
        "version": 1,
        "refresh": "10s",
        "style": "dark",
        "annotations": {"list": []},
        "templating": {"list": []},
        "time": {"from": "now-5m", "to": "now"},
        "timepicker": {},
        "panels": [
            _timeseries_panel(
                panel_id=1,
                title="Block Production Interval (seconds)",
                expr="1 / rate(blockchain_block_height[1m])",
                grid_x=0,
                grid_y=0,
                datasource_uid=datasource_uid,
            ),
            _timeseries_panel(
                panel_id=2,
                title="Mempool Queue Depth",
                expr="avg_over_time(mempool_queue_depth[1m])",
                grid_x=12,
                grid_y=0,
                datasource_uid=datasource_uid,
            ),
            _timeseries_panel(
                panel_id=5,
                title="Proposer Rotation Count",
                expr="increase(poa_proposer_rotations_total[5m])",
                grid_x=0,
                grid_y=8,
                datasource_uid=datasource_uid,
            ),
            _timeseries_panel(
                panel_id=3,
                title="Miner Queue Depth",
                expr="avg_over_time(miner_queue_depth[1m])",
                grid_x=12,
                grid_y=8,
                datasource_uid=datasource_uid,
            ),
            _timeseries_panel(
                panel_id=4,
                title="Miner Job Duration Seconds",
                expr="avg_over_time(miner_job_duration_seconds_sum[1m]) / avg_over_time(miner_job_duration_seconds_count[1m])",
                grid_x=0,
                grid_y=16,
                datasource_uid=datasource_uid,
            ),
            _timeseries_panel(
                panel_id=6,
                title="RPC 95th Percentile Latency",
                expr="histogram_quantile(0.95, sum(rate(rpc_request_duration_seconds_bucket[5m])) by (le))",
                grid_x=12,
                grid_y=16,
                datasource_uid=datasource_uid,
            ),
        ],
    }


def _dashboard_payloads(datasource_uid: str) -> Iterable[tuple[str, Dict[str, object]]]:
    return (
        ("coordinator-overview.json", _coordinator_dashboard(datasource_uid)),
        ("blockchain-node-overview.json", _node_dashboard(datasource_uid)),
    )


def generate_default_dashboards(output_dir: Path, datasource_uid: str = "${DS_PROMETHEUS}") -> None:
    """Write Grafana dashboard JSON exports to ``output_dir``.

    Parameters
    ----------
    output_dir:
        Directory that will receive the generated JSON files. It is created if
        it does not already exist.
    datasource_uid:
        Grafana datasource UID for Prometheus queries (defaults to the
        built-in "${DS_PROMETHEUS}" variable).
    """

    output_dir.mkdir(parents=True, exist_ok=True)

    for filename, payload in _dashboard_payloads(datasource_uid):
        dashboard_path = output_dir / filename
        with dashboard_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, sort_keys=True)
