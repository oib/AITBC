"""Monitoring and dashboard commands for AITBC CLI"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from ..utils import error, output, success
from ..utils.http_client import AITBCHTTPClient, get_logger

logger = get_logger(__name__)
console = Console()


def _monitoring_client(ctx: click.Context, timeout: int = 10) -> AITBCHTTPClient:
    """Build an HTTP client for the coordinator monitoring endpoints."""
    config = ctx.obj["config"]
    base_url = ctx.obj.get("url") or config.coordinator_api_url or "http://localhost:8203"
    api_key = ctx.obj.get("api_key") or config.api_key
    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key
    return AITBCHTTPClient(base_url=base_url, headers=headers, timeout=timeout)


@click.group(
    epilog="""Examples:

  aitbc monitor dashboard

  aitbc monitor metrics --period 24h"""
)
def monitor():
    """Monitor coordinator services, view metrics, manage alerts, and inspect campaign statistics."""
    pass


@monitor.command(
    epilog="""Examples:

  aitbc monitor dashboard

  aitbc monitor dashboard --refresh 5 --duration 60"""
)
@click.option("--refresh", type=int, default=5, help="Refresh interval in seconds")
@click.option("--duration", type=int, default=0, help="Duration in seconds (0 = indefinite)")
@click.pass_context
def dashboard(ctx, refresh: int, duration: int):
    """Show a real-time system dashboard with service status."""
    start_time = time.time()

    try:
        while True:
            elapsed = time.time() - start_time
            if duration > 0 and elapsed >= duration:
                break

            console.clear()
            console.rule("[bold blue]AITBC Dashboard[/bold blue]")
            console.print(f"[dim]Refreshing every {refresh}s | Elapsed: {int(elapsed)}s[/dim]\n")
            try:
                client = _monitoring_client(ctx, timeout=30)
                data = client.get("/v1/monitoring/dashboard")
                console.print("[bold green]Dashboard Status:[/bold green] Online")
                overall = data.get("overall_status", "unknown")
                console.print(f"  Overall Status: {overall}")
                services = data.get("services", {})
                console.print(f"  Services: {len(services)}")
                for service_name, service_data in services.items():
                    status = service_data.get("status", "unknown")
                    console.print(f"    {service_name}: {status}")
                metrics = data.get("metrics", {})
                if metrics:
                    console.print(f"  Health: {metrics.get('health_percentage', 0):.1f}%")
            except Exception as e:
                console.print(f"[red]Error fetching data: {e}[/red]")
            console.print("\n[dim]Press Ctrl+C to exit[/dim]")
            time.sleep(refresh)
    except KeyboardInterrupt:
        console.print("\n[bold]Dashboard stopped[/bold]")


@monitor.command(
    epilog="""Examples:

  aitbc monitor metrics --period 24h

  aitbc monitor metrics --period 7d --export /tmp/metrics.json"""
)
@click.option("--period", default="24h", help="Time period (1h, 24h, 7d, 30d)")
@click.option("--export", "export_path", type=click.Path(), help="Export metrics to file")
@click.pass_context
def metrics(ctx, period: str, export_path: str | None):
    """Collect and display system metrics for a time period."""
    multipliers = {"h": 3600, "d": 86400}
    unit = period[-1]
    value = int(period[:-1])
    seconds = value * multipliers.get(unit, 3600)
    since = datetime.now() - timedelta(seconds=seconds)

    metrics_data: dict[str, Any] = {
        "period": period,
        "since": since.isoformat(),
        "collected_at": datetime.now().isoformat(),
        "coordinator": {"status": "offline"},
        "jobs": {"total": 0, "completed": 0, "pending": 0, "failed": 0},
        "miners": {"total": 0, "online": 0, "offline": 0},
    }

    try:
        client = _monitoring_client(ctx, timeout=10)
        data = client.get("/v1/monitoring/metrics")
        metrics_data["coordinator"] = data.get("coordinator", {"status": "online"})
        metrics_data["jobs"] = data.get("jobs", metrics_data["jobs"])
        metrics_data["miners"] = data.get("miners", metrics_data["miners"])
    except Exception as e:
        logger.error("Failed to collect metrics: %s", e)

    if export_path:
        with open(export_path, "w") as f:
            json.dump(metrics_data, f, indent=2)
        success(f"Metrics exported to {export_path}")

    output(metrics_data, ctx.obj["output_format"])


@monitor.command(
    epilog="""Examples:

  aitbc monitor alerts --action list

  aitbc monitor alerts --action create --name high-load --type cpu --threshold 90"""
)
@click.argument("action", type=click.Choice(["add", "list", "remove", "test"]))
@click.option("--name", help="Alert name")
@click.option(
    "--type",
    "alert_type",
    type=click.Choice(["coordinator_down", "miner_offline", "job_failed", "low_balance"]),
    help="Alert type",
)
@click.option("--threshold", type=float, help="Alert threshold value")
@click.option("--webhook", help="Webhook URL for notifications")
@click.pass_context
def alerts(ctx, action: str, name: str | None, alert_type: str | None, threshold: float | None, webhook: str | None):
    """Configure or query monitoring alerts by name, type, and threshold."""
    alerts_dir = Path.home() / ".aitbc" / "alerts"
    alerts_dir.mkdir(parents=True, exist_ok=True)
    alerts_file = alerts_dir / "alerts.json"

    existing: list[dict[str, Any]] = []
    if alerts_file.exists():
        with open(alerts_file) as f:
            existing = json.load(f)

    if action == "add":
        if not name or not alert_type:
            error("Alert name and type required (--name, --type)")
            return
        alert = {
            "name": name,
            "type": alert_type,
            "threshold": threshold,
            "webhook": webhook,
            "created_at": datetime.now().isoformat(),
            "enabled": True,
        }
        existing.append(alert)
        with open(alerts_file, "w") as f:
            json.dump(existing, f, indent=2)
        success(f"Alert '{name}' added")
        output(alert, ctx.obj["output_format"])

    elif action == "list":
        if not existing:
            output({"message": "No alerts configured"}, ctx.obj["output_format"])
        else:
            output(existing, ctx.obj["output_format"])

    elif action == "remove":
        if not name:
            error("Alert name required (--name)")
            return
        existing = [a for a in existing if a["name"] != name]
        with open(alerts_file, "w") as f:
            json.dump(existing, f, indent=2)
        success(f"Alert '{name}' removed")

    elif action == "test":
        if not name:
            error("Alert name required (--name)")
            return
        alert = next((a for a in existing if a["name"] == name), None)  # type: ignore[arg-type]
        if not alert:
            error(f"Alert '{name}' not found")
            return
        webhook_url = alert.get("webhook")
        if webhook_url and isinstance(webhook_url, str):
            try:
                http_client = AITBCHTTPClient(base_url=webhook_url, timeout=10)
                resp = http_client.post(
                    "",
                    json={
                        "alert": name,
                        "type": alert["type"],
                        "message": "Test alert from AITBC CLI",
                        "timestamp": datetime.now().isoformat(),
                    },
                )
                output({"status": "sent", "response": resp}, ctx.obj["output_format"])
            except Exception as e:
                error(f"Webhook test failed: {e}")
        else:
            output({"status": "no_webhook", "alert": alert}, ctx.obj["output_format"])


@monitor.command(
    epilog="""Examples:

  aitbc monitor history --period 24h

  aitbc monitor history --period 7d"""
)
@click.option("--period", default="7d", help="Analysis period (1d, 7d, 30d)")
@click.pass_context
def history(ctx, period: str):
    """Show historical monitoring data for a period."""
    multipliers = {"h": 3600, "d": 86400}
    unit = period[-1]
    value = int(period[:-1])
    seconds = value * multipliers.get(unit, 3600)
    since = datetime.now() - timedelta(seconds=seconds)

    analysis = {
        "period": period,
        "since": since.isoformat(),
        "analyzed_at": datetime.now().isoformat(),
        "summary": {},
    }

    try:
        client = _monitoring_client(ctx, timeout=10)
        data = client.get("/v1/monitoring/metrics")
        jobs = data.get("jobs", {})
        total = jobs.get("total", 0)
        completed = jobs.get("completed", 0)
        failed = jobs.get("failed", 0)
        success_rate = f"{completed / max(1, total) * 100:.1f}%"
        analysis["summary"] = {
            "total_jobs": total,
            "completed": completed,
            "failed": failed,
            "success_rate": success_rate,
        }
    except Exception:
        analysis["summary"] = {"error": "Could not fetch job data"}

    output(analysis, ctx.obj["output_format"])


@monitor.command(
    epilog="""Examples:

  aitbc monitor webhooks --action list

  aitbc monitor webhooks --action create --name alert-hook --url https://example.com/hook --events alert"""
)
@click.argument("action", type=click.Choice(["add", "list", "remove", "test"]))
@click.option("--name", help="Webhook name")
@click.option("--url", help="Webhook URL")
@click.option("--events", help="Comma-separated event types (job_completed,miner_offline,alert)")
@click.pass_context
def webhooks(ctx, action: str, name: str | None, url: str | None, events: str | None):
    """Register, list, or remove monitoring webhooks."""
    webhooks_dir = Path.home() / ".aitbc" / "webhooks"
    webhooks_dir.mkdir(parents=True, exist_ok=True)
    webhooks_file = webhooks_dir / "webhooks.json"

    existing = []
    if webhooks_file.exists():
        with open(webhooks_file) as f:
            existing = json.load(f)

    if action == "add":
        if not name or not url:
            error("Webhook name and URL required (--name, --url)")
            return
        webhook = {
            "name": name,
            "url": url,
            "events": events.split(",") if events else ["all"],
            "created_at": datetime.now().isoformat(),
            "enabled": True,
        }
        existing.append(webhook)
        with open(webhooks_file, "w") as f:
            json.dump(existing, f, indent=2)
        success(f"Webhook '{name}' added")
        output(webhook, ctx.obj["output_format"])

    elif action == "list":
        if not existing:
            output({"message": "No webhooks configured"}, ctx.obj["output_format"])
        else:
            output(existing, ctx.obj["output_format"])

    elif action == "remove":
        if not name:
            error("Webhook name required (--name)")
            return
        existing = [w for w in existing if w["name"] != name]
        with open(webhooks_file, "w") as f:
            json.dump(existing, f, indent=2)
        success(f"Webhook '{name}' removed")

    elif action == "test":
        if not name:
            error("Webhook name required (--name)")
            return
        wh = next((w for w in existing if w["name"] == name), None)
        if not wh:
            error(f"Webhook '{name}' not found")
            return
        webhook_url = wh.get("url")
        if webhook_url and isinstance(webhook_url, str):
            try:
                http_client = AITBCHTTPClient(base_url=webhook_url, timeout=10)
                resp = http_client.post(
                    "",
                    json={
                        "event": "test",
                        "source": "aitbc-cli",
                        "message": "Test webhook notification",
                        "timestamp": datetime.now().isoformat(),
                    },
                )
                output({"status": "sent", "response": resp}, ctx.obj["output_format"])
            except Exception as e:
                error(f"Webhook test failed: {e}")
        else:
            error(f"Webhook '{name}' has no valid URL")


CAMPAIGNS_DIR = Path.home() / ".aitbc" / "campaigns"


def _ensure_campaigns():
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    campaigns_file = CAMPAIGNS_DIR / "campaigns.json"
    if not campaigns_file.exists():
        default = {
            "campaigns": [
                {
                    "id": "staking_launch",
                    "name": "Staking Launch Campaign",
                    "type": "staking",
                    "apy_boost": 2.0,
                    "start_date": "2026-02-01T00:00:00",
                    "end_date": "2026-04-01T00:00:00",
                    "status": "active",
                    "total_staked": 0,
                    "participants": 0,
                    "rewards_distributed": 0,
                },
                {
                    "id": "liquidity_mining_q1",
                    "name": "Q1 Liquidity Mining",
                    "type": "liquidity",
                    "apy_boost": 3.0,
                    "start_date": "2026-01-15T00:00:00",
                    "end_date": "2026-03-15T00:00:00",
                    "status": "active",
                    "total_staked": 0,
                    "participants": 0,
                    "rewards_distributed": 0,
                },
            ]
        }
        with open(campaigns_file, "w") as f:
            json.dump(default, f, indent=2)
    return campaigns_file


@monitor.command(
    epilog="""Examples:

  aitbc monitor campaigns

  aitbc monitor campaigns --status active"""
)
@click.option("--status", type=click.Choice(["active", "ended", "all"]), default="all", help="Filter by status")
@click.pass_context
def campaigns(ctx, status: str):
    """List active or completed monitoring campaigns."""
    campaigns_file = _ensure_campaigns()
    with open(campaigns_file) as f:
        data = json.load(f)

    campaign_list = data.get("campaigns", [])

    now = datetime.now()
    for c in campaign_list:
        end = datetime.fromisoformat(c["end_date"])
        if now > end and c["status"] == "active":
            c["status"] = "ended"
    with open(campaigns_file, "w") as f:
        json.dump(data, f, indent=2)

    if status != "all":
        campaign_list = [c for c in campaign_list if c["status"] == status]

    if not campaign_list:
        output({"message": "No campaigns found"}, ctx.obj["output_format"])
        return

    output(campaign_list, ctx.obj["output_format"])


@monitor.command(
    name="campaign-stats",
    epilog="""Examples:

  aitbc monitor campaign-stats

  aitbc monitor campaign-stats --campaign-id campaign-1""",
)
@click.argument("campaign_id", required=False)
@click.pass_context
def campaign_stats(ctx, campaign_id: str | None):
    """Show statistics for a monitoring campaign."""
    campaigns_file = _ensure_campaigns()
    with open(campaigns_file) as f:
        data = json.load(f)

    campaign_list = data.get("campaigns", [])

    if campaign_id:
        campaign = next((c for c in campaign_list if c["id"] == campaign_id), None)
        if not campaign:
            error(f"Campaign '{campaign_id}' not found")
            ctx.exit(1)
            return
        targets = [campaign]
    else:
        targets = campaign_list

    stats = []
    for c in targets:
        start = datetime.fromisoformat(c["start_date"])
        end = datetime.fromisoformat(c["end_date"])
        now = datetime.now()
        duration_days = (end - start).days
        elapsed_days = min((now - start).days, duration_days)
        progress_pct = round(elapsed_days / max(duration_days, 1) * 100, 1)

        stats.append(
            {
                "campaign_id": c["id"],
                "name": c["name"],
                "type": c["type"],
                "status": c["status"],
                "apy_boost": c.get("apy_boost", 0),
                "tvl": c.get("total_staked", 0),
                "participants": c.get("participants", 0),
                "rewards_distributed": c.get("rewards_distributed", 0),
                "duration_days": duration_days,
                "elapsed_days": elapsed_days,
                "progress_pct": progress_pct,
                "start_date": c["start_date"],
                "end_date": c["end_date"],
            }
        )

    if len(stats) == 1:
        output(stats[0], ctx.obj["output_format"])
    else:
        output(stats, ctx.obj["output_format"])
