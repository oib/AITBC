"""Prometheus querying and alerting commands for AITBC CLI."""

from __future__ import annotations

import json
from typing import cast
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import httpx

from ..utils import error, output, success
from ..utils.http_client import get_logger

logger = get_logger(__name__)

DEFAULT_PROMETHEUS_URL = "http://127.0.0.1:9090"


def _prometheus_url(ctx: click.Context, url: str | None) -> str:
    """Resolve Prometheus URL from option, config, or default."""
    if url:
        return url.rstrip("/")
    config = ctx.obj.get("config")
    if config is not None:
        configured = getattr(config, "prometheus_url", None)
        if configured:
            return str(configured).rstrip("/")
    return DEFAULT_PROMETHEUS_URL


def _prometheus_get(url: str, path: str, params: dict[str, Any] | None = None, timeout: int = 10) -> dict[str, Any]:
    """Issue a GET against the Prometheus expression/admin API."""
    try:
        response = httpx.get(f"{url}{path}", params=params, timeout=timeout)
        response.raise_for_status()
        return cast(dict[str, Any], response.json())
    except httpx.RequestError as e:
        error(f"Could not reach Prometheus at {url}: {e}")
        return {}
    except httpx.HTTPStatusError as e:
        error(f"Prometheus returned {e.response.status_code}: {e}")
        return {}


@click.group(
    epilog="""Examples:

  aitbc prometheus targets

  aitbc prometheus query --expr 'up'"""
)
def prometheus():
    """Query Prometheus, inspect targets, rules, alerts, and validate configuration."""
    pass


@prometheus.command(
    epilog="""Examples:

  aitbc prometheus targets

  aitbc prometheus targets --prometheus-url http://127.0.0.1:9090"""
)
@click.option("--prometheus-url", default=None, help="Prometheus base URL (default: http://127.0.0.1:9090)")
@click.pass_context
def targets(ctx: click.Context, prometheus_url: str | None):
    """Show the health of every Prometheus scrape target."""
    url = _prometheus_url(ctx, prometheus_url)
    data = _prometheus_get(url, "/api/v1/targets")
    active = data.get("data", {}).get("activeTargets", [])
    dropped = data.get("data", {}).get("droppedTargets", [])

    result = {
        "targets": [
            {
                "job": t.get("labels", {}).get("job"),
                "instance": t.get("labels", {}).get("instance"),
                "health": t.get("health"),
                "last_error": t.get("lastError", ""),
            }
            for t in active
        ],
        "dropped_count": len(dropped),
    }
    output(result, ctx.obj["output_format"])


@prometheus.command(
    epilog="""Examples:

  aitbc prometheus rules

  aitbc prometheus rules --prometheus-url http://127.0.0.1:9090"""
)
@click.option("--prometheus-url", default=None, help="Prometheus base URL (default: http://127.0.0.1:9090)")
@click.pass_context
def rules(ctx: click.Context, prometheus_url: str | None):
    """List loaded Prometheus recording and alerting rules."""
    url = _prometheus_url(ctx, prometheus_url)
    data = _prometheus_get(url, "/api/v1/rules")
    result = []
    for group in data.get("data", {}).get("groups", []):
        result.append(
            {
                "name": group.get("name"),
                "file": group.get("file"),
                "rules": [r.get("name") for r in group.get("rules", [])],
            }
        )
    output({"groups": result}, ctx.obj["output_format"])


@prometheus.command(
    epilog="""Examples:

  aitbc prometheus alerts

  aitbc prometheus alerts --watch --interval 15"""
)
@click.option("--prometheus-url", default=None, help="Prometheus base URL (default: http://127.0.0.1:9090)")
@click.option("--watch", is_flag=True, help="Poll continuously and emit firing alerts")
@click.option("--interval", type=int, default=15, help="Poll interval in seconds (watch mode)")
@click.option("--emit/--no-emit", default=True, help="Emit one structured log line per firing alert (watch mode)")
@click.pass_context
def alerts(ctx: click.Context, prometheus_url: str | None, watch: bool, interval: int, emit: bool):
    """Show current Prometheus alerts and optionally watch for firing alerts."""
    url = _prometheus_url(ctx, prometheus_url)

    def _fetch() -> list[dict[str, Any]]:
        data = _prometheus_get(url, "/api/v1/alerts")
        return cast(list[dict[str, Any]], data.get("data", {}).get("alerts", []))

    def _present(raw_alerts: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "alerts": [
                {
                    "name": a.get("labels", {}).get("alertname"),
                    "state": a.get("state"),
                    "severity": a.get("labels", {}).get("severity"),
                    "summary": a.get("annotations", {}).get("summary"),
                    "description": a.get("annotations", {}).get("description"),
                    "active_at": a.get("activeAt"),
                    "labels": a.get("labels"),
                }
                for a in raw_alerts
            ],
            "firing": sum(1 for a in raw_alerts if a.get("state") == "firing"),
            "pending": sum(1 for a in raw_alerts if a.get("state") == "pending"),
            "checked_at": datetime.utcnow().isoformat(),
        }

    if not watch:
        output(_present(_fetch()), ctx.obj["output_format"])
        return

    seen: set[str] = set()
    try:
        while True:
            raw = _fetch()
            summary = _present(raw)
            if ctx.obj["output_format"] == "json":
                output(summary, "json")
            for alert in raw:
                if alert.get("state") != "firing":
                    continue
                alert_id = f"{alert.get('labels', {}).get('alertname')}{json.dumps(alert.get('labels', {}), sort_keys=True)}"
                if alert_id not in seen:
                    seen.add(alert_id)
                    if emit:
                        # Structured line for journalctl / external watchers
                        line = json.dumps(
                            {
                                "event": "prometheus_alert_firing",
                                "alertname": alert.get("labels", {}).get("alertname"),
                                "state": alert.get("state"),
                                "severity": alert.get("labels", {}).get("severity"),
                                "summary": alert.get("annotations", {}).get("summary"),
                                "description": alert.get("annotations", {}).get("description"),
                                "labels": alert.get("labels"),
                                "active_at": alert.get("activeAt"),
                                "timestamp": datetime.utcnow().isoformat(),
                            },
                            sort_keys=True,
                        )
                        click.echo(line, file=sys.stdout)
                        logger.warning(line)
            time.sleep(interval)
    except KeyboardInterrupt:
        click.echo("\nWatch stopped")


@prometheus.command(
    epilog="""Examples:

  aitbc prometheus query --expr 'up'

  aitbc prometheus query --expr 'up' --prometheus-url http://127.0.0.1:9090"""
)
@click.option("--expr", "expr", required=True, help="The Expr.")
@click.option("--prometheus-url", default=None, help="Prometheus base URL (default: http://127.0.0.1:9090)")
@click.option("--time", default=None, help="Evaluation timestamp (RFC3339 or Unix)")
@click.option("--timeout", default=30, help="Query timeout in seconds")
@click.pass_context
def query(ctx: click.Context, expr: str, prometheus_url: str | None, time: str | None, timeout: int):
    """Run a PromQL query against Prometheus."""
    url = _prometheus_url(ctx, prometheus_url)
    params: dict[str, Any] = {"query": expr, "timeout": timeout}
    if time:
        params["time"] = time
    data = _prometheus_get(url, "/api/v1/query", params=params, timeout=timeout + 5)
    output(data.get("data", {}), ctx.obj["output_format"])


@prometheus.command(
    epilog="""Examples:

  aitbc prometheus check

  aitbc prometheus check --config /etc/prometheus/prometheus.yml --rules /etc/prometheus/aitbc_rules.yml"""
)
@click.option("--config", "config_path", default="/etc/prometheus/prometheus.yml", help="Prometheus config file")
@click.option("--rules", "rules_path", default="/etc/prometheus/aitbc_rules.yml", help="Prometheus rules file")
@click.pass_context
def check(ctx: click.Context, config_path: str, rules_path: str):
    """Validate Prometheus config and rules with promtool."""
    config_file = Path(config_path)
    rules_file = Path(rules_path)
    results: dict[str, Any] = {"config": None, "rules": None}

    if config_file.exists():
        try:
            proc = subprocess.run(
                ["promtool", "check", "config", str(config_file)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            results["config"] = {"ok": proc.returncode == 0, "output": proc.stdout + proc.stderr}
        except FileNotFoundError:
            results["config"] = {"ok": False, "output": "promtool not found in PATH"}
        except subprocess.TimeoutExpired:
            results["config"] = {"ok": False, "output": "promtool timed out"}
    else:
        results["config"] = {"ok": False, "output": f"config not found: {config_file}"}

    if rules_file.exists():
        try:
            proc = subprocess.run(
                ["promtool", "check", "rules", str(rules_file)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            results["rules"] = {"ok": proc.returncode == 0, "output": proc.stdout + proc.stderr}
        except FileNotFoundError:
            results["rules"] = {"ok": False, "output": "promtool not found in PATH"}
        except subprocess.TimeoutExpired:
            results["rules"] = {"ok": False, "output": "promtool timed out"}
    else:
        results["rules"] = {"ok": False, "output": f"rules not found: {rules_file}"}

    all_ok = all(r["ok"] for r in results.values() if r is not None)
    output(results, ctx.obj["output_format"])
    if all_ok:
        success("Prometheus config and rules are valid")
    else:
        error("Prometheus config or rules validation failed")


@prometheus.command(
    epilog="""Examples:

  aitbc prometheus series

  aitbc prometheus series --prometheus-url http://127.0.0.1:9090"""
)
@click.option("--prometheus-url", default=None, help="Prometheus base URL (default: http://127.0.0.1:9090)")
@click.pass_context
def series(ctx: click.Context, prometheus_url: str | None):
    """Show the count of currently loaded metric series for cardinality."""
    url = _prometheus_url(ctx, prometheus_url)
    data = _prometheus_get(url, "/api/v1/label/__name__/values")
    names = data.get("data", [])
    output({"metric_names": len(names)}, ctx.obj["output_format"])
