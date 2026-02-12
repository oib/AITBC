"""Monitoring and dashboard commands for AITBC CLI"""

import click
import httpx
import json
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
from ..utils import output, error, success, console


@click.group()
def monitor():
    """Monitoring, metrics, and alerting commands"""
    pass


@monitor.command()
@click.option("--refresh", type=int, default=5, help="Refresh interval in seconds")
@click.option("--duration", type=int, default=0, help="Duration in seconds (0 = indefinite)")
@click.pass_context
def dashboard(ctx, refresh: int, duration: int):
    """Real-time system dashboard"""
    config = ctx.obj['config']
    start_time = time.time()

    try:
        while True:
            elapsed = time.time() - start_time
            if duration > 0 and elapsed >= duration:
                break

            console.clear()
            console.rule("[bold blue]AITBC Dashboard[/bold blue]")
            console.print(f"[dim]Refreshing every {refresh}s | Elapsed: {int(elapsed)}s[/dim]\n")

            # Fetch system status
            try:
                with httpx.Client(timeout=5) as client:
                    # Node status
                    try:
                        resp = client.get(
                            f"{config.coordinator_url}/v1/status",
                            headers={"X-Api-Key": config.api_key or ""}
                        )
                        if resp.status_code == 200:
                            status = resp.json()
                            console.print("[bold green]Coordinator:[/bold green] Online")
                            for k, v in status.items():
                                console.print(f"  {k}: {v}")
                        else:
                            console.print(f"[bold yellow]Coordinator:[/bold yellow] HTTP {resp.status_code}")
                    except Exception:
                        console.print("[bold red]Coordinator:[/bold red] Offline")

                    console.print()

                    # Jobs summary
                    try:
                        resp = client.get(
                            f"{config.coordinator_url}/v1/jobs",
                            headers={"X-Api-Key": config.api_key or ""},
                            params={"limit": 5}
                        )
                        if resp.status_code == 200:
                            jobs = resp.json()
                            if isinstance(jobs, list):
                                console.print(f"[bold cyan]Recent Jobs:[/bold cyan] {len(jobs)}")
                                for job in jobs[:5]:
                                    status_color = "green" if job.get("status") == "completed" else "yellow"
                                    console.print(f"  [{status_color}]{job.get('id', 'N/A')}: {job.get('status', 'unknown')}[/{status_color}]")
                    except Exception:
                        console.print("[dim]Jobs: unavailable[/dim]")

                    console.print()

                    # Miners summary
                    try:
                        resp = client.get(
                            f"{config.coordinator_url}/v1/miners",
                            headers={"X-Api-Key": config.api_key or ""}
                        )
                        if resp.status_code == 200:
                            miners = resp.json()
                            if isinstance(miners, list):
                                online = sum(1 for m in miners if m.get("status") == "ONLINE")
                                console.print(f"[bold cyan]Miners:[/bold cyan] {online}/{len(miners)} online")
                    except Exception:
                        console.print("[dim]Miners: unavailable[/dim]")

            except Exception as e:
                console.print(f"[red]Error fetching data: {e}[/red]")

            console.print(f"\n[dim]Press Ctrl+C to exit[/dim]")
            time.sleep(refresh)

    except KeyboardInterrupt:
        console.print("\n[bold]Dashboard stopped[/bold]")


@monitor.command()
@click.option("--period", default="24h", help="Time period (1h, 24h, 7d, 30d)")
@click.option("--export", "export_path", type=click.Path(), help="Export metrics to file")
@click.pass_context
def metrics(ctx, period: str, export_path: Optional[str]):
    """Collect and display system metrics"""
    config = ctx.obj['config']

    # Parse period
    multipliers = {"h": 3600, "d": 86400}
    unit = period[-1]
    value = int(period[:-1])
    seconds = value * multipliers.get(unit, 3600)
    since = datetime.now() - timedelta(seconds=seconds)

    metrics_data = {
        "period": period,
        "since": since.isoformat(),
        "collected_at": datetime.now().isoformat(),
        "coordinator": {},
        "jobs": {},
        "miners": {}
    }

    try:
        with httpx.Client(timeout=10) as client:
            # Coordinator metrics
            try:
                resp = client.get(
                    f"{config.coordinator_url}/v1/status",
                    headers={"X-Api-Key": config.api_key or ""}
                )
                if resp.status_code == 200:
                    metrics_data["coordinator"] = resp.json()
                    metrics_data["coordinator"]["status"] = "online"
                else:
                    metrics_data["coordinator"]["status"] = f"error_{resp.status_code}"
            except Exception:
                metrics_data["coordinator"]["status"] = "offline"

            # Job metrics
            try:
                resp = client.get(
                    f"{config.coordinator_url}/v1/jobs",
                    headers={"X-Api-Key": config.api_key or ""},
                    params={"limit": 100}
                )
                if resp.status_code == 200:
                    jobs = resp.json()
                    if isinstance(jobs, list):
                        metrics_data["jobs"] = {
                            "total": len(jobs),
                            "completed": sum(1 for j in jobs if j.get("status") == "completed"),
                            "pending": sum(1 for j in jobs if j.get("status") == "pending"),
                            "failed": sum(1 for j in jobs if j.get("status") == "failed"),
                        }
            except Exception:
                metrics_data["jobs"] = {"error": "unavailable"}

            # Miner metrics
            try:
                resp = client.get(
                    f"{config.coordinator_url}/v1/miners",
                    headers={"X-Api-Key": config.api_key or ""}
                )
                if resp.status_code == 200:
                    miners = resp.json()
                    if isinstance(miners, list):
                        metrics_data["miners"] = {
                            "total": len(miners),
                            "online": sum(1 for m in miners if m.get("status") == "ONLINE"),
                            "offline": sum(1 for m in miners if m.get("status") != "ONLINE"),
                        }
            except Exception:
                metrics_data["miners"] = {"error": "unavailable"}

    except Exception as e:
        error(f"Failed to collect metrics: {e}")

    if export_path:
        with open(export_path, "w") as f:
            json.dump(metrics_data, f, indent=2)
        success(f"Metrics exported to {export_path}")

    output(metrics_data, ctx.obj['output_format'])


@monitor.command()
@click.argument("action", type=click.Choice(["add", "list", "remove", "test"]))
@click.option("--name", help="Alert name")
@click.option("--type", "alert_type", type=click.Choice(["coordinator_down", "miner_offline", "job_failed", "low_balance"]), help="Alert type")
@click.option("--threshold", type=float, help="Alert threshold value")
@click.option("--webhook", help="Webhook URL for notifications")
@click.pass_context
def alerts(ctx, action: str, name: Optional[str], alert_type: Optional[str],
           threshold: Optional[float], webhook: Optional[str]):
    """Configure monitoring alerts"""
    alerts_dir = Path.home() / ".aitbc" / "alerts"
    alerts_dir.mkdir(parents=True, exist_ok=True)
    alerts_file = alerts_dir / "alerts.json"

    # Load existing alerts
    existing = []
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
            "enabled": True
        }
        existing.append(alert)
        with open(alerts_file, "w") as f:
            json.dump(existing, f, indent=2)
        success(f"Alert '{name}' added")
        output(alert, ctx.obj['output_format'])

    elif action == "list":
        if not existing:
            output({"message": "No alerts configured"}, ctx.obj['output_format'])
        else:
            output(existing, ctx.obj['output_format'])

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
        alert = next((a for a in existing if a["name"] == name), None)
        if not alert:
            error(f"Alert '{name}' not found")
            return
        if alert.get("webhook"):
            try:
                with httpx.Client(timeout=10) as client:
                    resp = client.post(alert["webhook"], json={
                        "alert": name,
                        "type": alert["type"],
                        "message": f"Test alert from AITBC CLI",
                        "timestamp": datetime.now().isoformat()
                    })
                    output({"status": "sent", "response_code": resp.status_code}, ctx.obj['output_format'])
            except Exception as e:
                error(f"Webhook test failed: {e}")
        else:
            output({"status": "no_webhook", "alert": alert}, ctx.obj['output_format'])


@monitor.command()
@click.option("--period", default="7d", help="Analysis period (1d, 7d, 30d)")
@click.pass_context
def history(ctx, period: str):
    """Historical data analysis"""
    config = ctx.obj['config']

    multipliers = {"h": 3600, "d": 86400}
    unit = period[-1]
    value = int(period[:-1])
    seconds = value * multipliers.get(unit, 3600)
    since = datetime.now() - timedelta(seconds=seconds)

    analysis = {
        "period": period,
        "since": since.isoformat(),
        "analyzed_at": datetime.now().isoformat(),
        "summary": {}
    }

    try:
        with httpx.Client(timeout=10) as client:
            try:
                resp = client.get(
                    f"{config.coordinator_url}/v1/jobs",
                    headers={"X-Api-Key": config.api_key or ""},
                    params={"limit": 500}
                )
                if resp.status_code == 200:
                    jobs = resp.json()
                    if isinstance(jobs, list):
                        completed = [j for j in jobs if j.get("status") == "completed"]
                        failed = [j for j in jobs if j.get("status") == "failed"]
                        analysis["summary"] = {
                            "total_jobs": len(jobs),
                            "completed": len(completed),
                            "failed": len(failed),
                            "success_rate": f"{len(completed) / max(1, len(jobs)) * 100:.1f}%",
                        }
            except Exception:
                analysis["summary"] = {"error": "Could not fetch job data"}

    except Exception as e:
        error(f"Analysis failed: {e}")

    output(analysis, ctx.obj['output_format'])


@monitor.command()
@click.argument("action", type=click.Choice(["add", "list", "remove", "test"]))
@click.option("--name", help="Webhook name")
@click.option("--url", help="Webhook URL")
@click.option("--events", help="Comma-separated event types (job_completed,miner_offline,alert)")
@click.pass_context
def webhooks(ctx, action: str, name: Optional[str], url: Optional[str], events: Optional[str]):
    """Manage webhook notifications"""
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
            "enabled": True
        }
        existing.append(webhook)
        with open(webhooks_file, "w") as f:
            json.dump(existing, f, indent=2)
        success(f"Webhook '{name}' added")
        output(webhook, ctx.obj['output_format'])

    elif action == "list":
        if not existing:
            output({"message": "No webhooks configured"}, ctx.obj['output_format'])
        else:
            output(existing, ctx.obj['output_format'])

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
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(wh["url"], json={
                    "event": "test",
                    "source": "aitbc-cli",
                    "message": "Test webhook notification",
                    "timestamp": datetime.now().isoformat()
                })
                output({"status": "sent", "response_code": resp.status_code}, ctx.obj['output_format'])
        except Exception as e:
            error(f"Webhook test failed: {e}")


CAMPAIGNS_DIR = Path.home() / ".aitbc" / "campaigns"


def _ensure_campaigns():
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    campaigns_file = CAMPAIGNS_DIR / "campaigns.json"
    if not campaigns_file.exists():
        # Seed with default campaigns
        default = {"campaigns": [
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
                "rewards_distributed": 0
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
                "rewards_distributed": 0
            }
        ]}
        with open(campaigns_file, "w") as f:
            json.dump(default, f, indent=2)
    return campaigns_file


@monitor.command()
@click.option("--status", type=click.Choice(["active", "ended", "all"]), default="all", help="Filter by status")
@click.pass_context
def campaigns(ctx, status: str):
    """List active incentive campaigns"""
    campaigns_file = _ensure_campaigns()
    with open(campaigns_file) as f:
        data = json.load(f)

    campaign_list = data.get("campaigns", [])

    # Auto-update status
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
        output({"message": "No campaigns found"}, ctx.obj['output_format'])
        return

    output(campaign_list, ctx.obj['output_format'])


@monitor.command(name="campaign-stats")
@click.argument("campaign_id", required=False)
@click.pass_context
def campaign_stats(ctx, campaign_id: Optional[str]):
    """Campaign performance metrics (TVL, participants, rewards)"""
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

        stats.append({
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
            "end_date": c["end_date"]
        })

    if len(stats) == 1:
        output(stats[0], ctx.obj['output_format'])
    else:
        output(stats, ctx.obj['output_format'])
