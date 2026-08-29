"""Reputation management commands for AITBC CLI"""

import hashlib
import json
from decimal import Decimal
from typing import Any, cast

import click

from ..config import get_config
from ..utils import output, success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)

DEFAULT_COORDINATOR_URL = "http://localhost:8203"

SIMULATED_TIMESTAMP = "2026-01-01T00:00:00+00:00"


def _coordinator_client(ctx: click.Context | None = None) -> AITBCHTTPClient:
    """Return an HTTP client for the coordinator API."""
    config = get_config()
    base_url = (config.coordinator_api_url or DEFAULT_COORDINATOR_URL).rstrip("/")
    api_key = config.api_key
    if ctx and ctx.obj:
        api_key = ctx.obj.get("api_key") or api_key
    return AITBCHTTPClient(base_url=base_url, api_key=api_key, timeout=30)


def _reputation_endpoint(path: str) -> str:
    """Build a /reputation/* endpoint path under the /v1 base."""
    return f"/reputation{path}"


def _reputation_level(score: float) -> str:
    if score >= 900:
        return "legendary"
    if score >= 750:
        return "excellent"
    if score >= 600:
        return "good"
    if score >= 400:
        return "fair"
    if score >= 200:
        return "poor"
    return "untrusted"


def _hash_float(parts, low: float = 0.0, high: float = 1.0, decimals: int = 2) -> float:
    content = ":".join(str(p) for p in parts)
    normalized = int(hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:8], 16) / 0xFFFFFFFF
    return round(low + normalized * (high - low), decimals)


def _hash_int(parts, low: int, high: int) -> int:
    content = ":".join(str(p) for p in parts)
    normalized = int(hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:8], 16) / 0xFFFFFFFF
    return int(low + normalized * (high - low))


def _simulated_profile(agent_id: str) -> dict[str, Any]:
    base = ("reputation", "profile", agent_id)
    trust = _hash_float(base + ("trust",), 300.0, 980.0, 2)
    tx_count = _hash_int(base + ("tx_count",), 5, 10000)
    completed = _hash_int(base + ("completed",), 0, tx_count)
    return {
        "agent_id": agent_id,
        "trust_score": trust,
        "reputation_level": _reputation_level(trust),
        "performance_rating": _hash_float(base + ("performance",), 1.0, 5.0, 1),
        "reliability_score": _hash_float(base + ("reliability",), 50.0, 99.99, 2),
        "community_rating": _hash_float(base + ("community",), 1.0, 5.0, 1),
        "total_earnings": _hash_float(base + ("earnings",), 0.0, 50000.0, 4),
        "transaction_count": tx_count,
        "success_rate": _hash_float(base + ("success",), 70.0, 99.99, 2),
        "jobs_completed": completed,
        "jobs_failed": max(0, tx_count - completed),
    }


def _simulated_trust_score(agent_id: str) -> dict[str, Any]:
    base = ("reputation", "trust-score", agent_id)
    composite = _hash_float(base + ("composite",), 300.0, 980.0, 2)
    return {
        "agent_id": agent_id,
        "composite_score": composite,
        "performance_score": _hash_float(base + ("performance",), 200.0, 980.0, 2),
        "reliability_score": _hash_float(base + ("reliability",), 200.0, 980.0, 2),
        "community_score": _hash_float(base + ("community",), 200.0, 980.0, 2),
        "security_score": _hash_float(base + ("security",), 200.0, 980.0, 2),
        "economic_score": _hash_float(base + ("economic",), 200.0, 980.0, 2),
        "reputation_level": _reputation_level(composite),
        "calculated_at": SIMULATED_TIMESTAMP,
    }


def _simulated_leaderboard(category: str, limit: int, region: str | None) -> list[dict[str, Any]]:
    region_key = region or "global"
    entries = []
    for i in range(1, limit + 1):
        seed = ("reputation", "leaderboard", category, str(limit), region_key, str(i))
        trust = _hash_float(seed + ("trust",), 250.0, 990.0, 2)
        tx = _hash_int(seed + ("tx",), 10, 20000)
        agent_id = f"sim-agent-{i:04d}-{hashlib.md5(':'.join(seed).encode(), usedforsecurity=False).hexdigest()[:8]}"
        entries.append(
            {
                "rank": i,
                "agent_id": agent_id,
                "trust_score": trust,
                "reputation_level": _reputation_level(trust),
                "transaction_count": tx,
            }
        )
    entries.sort(key=lambda e: (-e["trust_score"], e["agent_id"]))
    for i, e in enumerate(entries, 1):
        e["rank"] = i
    return entries


def _simulated_metrics() -> dict[str, Any]:
    return {
        "status": "simulated",
        "total_agents": 1234,
        "average_trust_score": 624.56,
        "level_distribution": {
            "legendary": 12,
            "excellent": 120,
            "good": 410,
            "fair": 520,
            "poor": 150,
            "untrusted": 34,
        },
        "top_regions": [
            {"region": "EU", "count": 312},
            {"region": "US-East", "count": 298},
            {"region": "APAC", "count": 245},
            {"region": "US-West", "count": 180},
            {"region": "LATAM", "count": 99},
        ],
        "recent_activity": {
            "events_last_24h": 842,
            "active_agents": 180,
        },
    }


@click.group(
    name="reputation",
    epilog="""Examples:

  aitbc reputation profile --agent-id agent-1

  aitbc reputation leaderboard""",
)
@click.pass_context
def reputation(ctx):
    """Manage and query agent reputation profiles, trust scores, and feedback."""
    ctx.ensure_object(dict)


@reputation.command(
    "profile",
    epilog="""Examples:

  aitbc reputation profile --agent-id agent-1

  aitbc reputation profile --agent-id agent-1 --output json""",
)
@click.option("--agent-id", "agent_id", required=True, help="The Agent id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def get_profile(ctx, agent_id: str, format: str):
    """Get the reputation profile for an agent."""
    try:
        http_client = _coordinator_client(ctx)
        try:
            resp = http_client.get(_reputation_endpoint(f"/profile/{agent_id}"))
        except NetworkError:
            data = _simulated_profile(agent_id)
            if format == "json":
                click.echo(json.dumps(data, indent=2, default=str))
            else:
                output(data, format, title="Reputation Profile (Simulated)")
            return

        data: dict[str, Any] = resp

        if format == "json":
            click.echo(json.dumps(data, indent=2, default=str))
            return

        click.echo(f"Agent ID: {data.get('agent_id', agent_id)}")
        click.echo(f"Trust Score: {float(data.get('trust_score', 0)):.2f}/1000")
        click.echo(f"Reputation Level: {data.get('reputation_level', 'unknown')}")
        click.echo(f"Performance Rating: {float(data.get('performance_rating', 0)):.1f}/5.0")
        click.echo(f"Reliability Score: {float(data.get('reliability_score', 0)):.2f}%")
        click.echo(f"Community Rating: {float(data.get('community_rating', 0)):.1f}/5.0")
        click.echo(f"Total Earnings: {Decimal(data.get('total_earnings', 0)):.4f} AITBC")
        click.echo(f"Transaction Count: {data.get('transaction_count', 0)}")
        click.echo(f"Success Rate: {float(data.get('success_rate', 0)):.2f}%")
        click.echo(f"Jobs Completed: {data.get('jobs_completed', 0)}")
        click.echo(f"Jobs Failed: {data.get('jobs_failed', 0)}")
    except NetworkError as e:
        # Safety net for unexpected network failures.
        abort(ctx, f"Network error: {e}")
    except Exception as e:
        abort(ctx, f"Error getting reputation profile: {e}", from_exception=e)


@reputation.command(
    "trust-score",
    epilog="""Examples:

  aitbc reputation trust-score --agent-id agent-1

  aitbc reputation trust-score --agent-id agent-1 --output json""",
)
@click.option("--agent-id", "agent_id", required=True, help="The Agent id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def trust_score(ctx, agent_id: str, format: str):
    """Get a detailed trust score breakdown for an agent."""
    try:
        http_client = _coordinator_client(ctx)
        try:
            resp = http_client.get(_reputation_endpoint(f"/trust-score/{agent_id}"))
        except NetworkError:
            data = _simulated_trust_score(agent_id)
            if format == "json":
                click.echo(json.dumps(data, indent=2, default=str))
            else:
                output(data, format, title="Trust Score (Simulated)")
            return

        data: dict[str, Any] = resp

        if format == "json":
            click.echo(json.dumps(data, indent=2, default=str))
            return

        click.echo(f"Agent ID: {data.get('agent_id', agent_id)}")
        click.echo(f"Composite Score: {float(data.get('composite_score', 0)):.2f}/1000")
        click.echo(f"Performance Score: {float(data.get('performance_score', 0)):.2f}/1000")
        click.echo(f"Reliability Score: {float(data.get('reliability_score', 0)):.2f}/1000")
        click.echo(f"Community Score: {float(data.get('community_score', 0)):.2f}/1000")
        click.echo(f"Security Score: {float(data.get('security_score', 0)):.2f}/1000")
        click.echo(f"Economic Score: {float(data.get('economic_score', 0)):.2f}/1000")
        click.echo(f"Reputation Level: {data.get('reputation_level', 'unknown')}")
        click.echo(f"Calculated At: {data.get('calculated_at', 'unknown')}")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}")
    except Exception as e:
        abort(ctx, f"Error getting trust score: {e}", from_exception=e)


@reputation.command(
    "leaderboard",
    epilog="""Examples:

  aitbc reputation leaderboard

  aitbc reputation leaderboard --category trust_score --limit 20""",
)
@click.option("--category", default="trust_score", help="Category to rank by")
@click.option("--limit", type=int, default=10, help="Number of results")
@click.option("--region", default=None, help="Filter by region")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def leaderboard(ctx, category: str, limit: int, region: str | None, format: str):
    """Get the agent reputation leaderboard."""
    try:
        params: dict[str, Any] = {"category": category, "limit": limit}
        if region:
            params["region"] = region

        http_client = _coordinator_client(ctx)
        try:
            resp = http_client.get(_reputation_endpoint("/leaderboard"), params=params)
        except NetworkError:
            data = _simulated_leaderboard(category, limit, region)
            if format == "json":
                click.echo(json.dumps(data, indent=2, default=str))
            else:
                output(data, format, title="Reputation Leaderboard (Simulated)")
            return

        raw: Any = resp
        if isinstance(raw, list):
            data = raw
        else:
            data = cast(list, raw.get("leaderboard", []))

        if format == "json":
            click.echo(json.dumps(data, indent=2, default=str))
            return

        click.echo(f"{'Rank':<6} {'Agent ID':<30} {'Trust Score':<12} {'Level':<12} {'Transactions':<12}")
        click.echo("-" * 78)
        for entry in data:
            click.echo(
                f"{entry.get('rank', 0):<6} "
                f"{entry.get('agent_id', '')[:28]:<30} "
                f"{float(entry.get('trust_score', 0)):<12.2f} "
                f"{entry.get('reputation_level', ''):<12} "
                f"{entry.get('transaction_count', 0):<12}"
            )
    except NetworkError as e:
        abort(ctx, f"Network error: {e}")
    except Exception as e:
        abort(ctx, f"Error getting leaderboard: {e}", from_exception=e)


@reputation.command(
    "metrics",
    epilog="""Examples:

  aitbc reputation metrics

  aitbc reputation metrics --output json""",
)
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def metrics(ctx, format: str):
    """Get overall reputation system metrics."""
    try:
        http_client = _coordinator_client(ctx)
        try:
            resp = http_client.get(_reputation_endpoint("/metrics"))
        except NetworkError:
            data = _simulated_metrics()
            if format == "json":
                click.echo(json.dumps(data, indent=2, default=str))
            else:
                output(data, format, title="Reputation Metrics (Simulated)")
            return

        data: dict[str, Any] = resp

        if format == "json":
            click.echo(json.dumps(data, indent=2, default=str))
            return

        click.echo(f"Total Agents: {data.get('total_agents', 0)}")
        click.echo(f"Average Trust Score: {float(data.get('average_trust_score', 0)):.2f}/1000")
        click.echo("\nLevel Distribution:")
        for level, count in (data.get("level_distribution") or {}).items():
            click.echo(f"  {level}: {count}")
        click.echo("\nTop Regions:")
        for region in (data.get("top_regions") or [])[:5]:
            click.echo(f"  {region.get('region')}: {region.get('count')}")
        click.echo("\nRecent Activity (24h):")
        recent = data.get("recent_activity") or {}
        click.echo(f"  Events: {recent.get('events_last_24h', recent.get('events', 0))}")
        click.echo(f"  Active Agents: {recent.get('active_agents', 0)}")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}")
    except Exception as e:
        abort(ctx, f"Error getting metrics: {e}", from_exception=e)


@reputation.command(
    "create-profile",
    epilog="""Examples:

  aitbc reputation create-profile --agent-id agent-1""",
)
@click.option("--agent-id", "agent_id", required=True, help="The Agent id.")
@click.pass_context
def create_profile(ctx, agent_id: str):
    """Create a new reputation profile for an agent."""
    try:
        http_client = _coordinator_client(ctx)
        resp = http_client.post(_reputation_endpoint(f"/profile/{agent_id}"))
        data: dict[str, Any] = resp

        success("Reputation profile created successfully!")
        click.echo(f"Agent ID: {data.get('agent_id', agent_id)}")
        click.echo(f"Initial Trust Score: {data.get('trust_score', 0)}")
        click.echo(f"Reputation Level: {data.get('reputation_level', 'unknown')}")
        click.echo(f"Created At: {data.get('created_at', 'unknown')}")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}")
    except Exception as e:
        abort(ctx, f"Error creating profile: {e}", from_exception=e)


@reputation.command(
    "feedback",
    epilog="""Examples:

  aitbc reputation feedback --agent-id agent-1 --reviewer-id reviewer-1

  aitbc reputation feedback --agent-id agent-1 --reviewer-id reviewer-1 --overall 5 --text 'great work'""",
)
@click.option("--agent-id", "agent_id", required=True, help="The Agent id.")
@click.option("--reviewer-id", "reviewer_id", required=True, help="The Reviewer id.")
@click.option("--overall", type=float, default=3.0, help="Overall rating (1-5)")
@click.option("--performance", type=float, default=3.0, help="Performance rating (1-5)")
@click.option("--communication", type=float, default=3.0, help="Communication rating (1-5)")
@click.option("--reliability", type=float, default=3.0, help="Reliability rating (1-5)")
@click.option("--value", type=float, default=3.0, help="Value rating (1-5)")
@click.option("--text", default="", help="Feedback text")
@click.option("--tag", multiple=True, help="Feedback tags")
@click.pass_context
def add_feedback(
    ctx,
    agent_id: str,
    reviewer_id: str,
    overall: float,
    performance: float,
    communication: float,
    reliability: float,
    value: float,
    text: str,
    tag: tuple,
):
    """Add community feedback for an agent."""
    try:
        ratings = {
            "overall": overall,
            "performance": performance,
            "communication": communication,
            "reliability": reliability,
            "value": value,
        }

        payload = {
            "reviewer_id": reviewer_id,
            "ratings": ratings,
            "feedback_text": text,
            "tags": list(tag),
        }

        http_client = _coordinator_client(ctx)
        resp = http_client.post(_reputation_endpoint(f"/feedback/{agent_id}"), json=payload)
        data: dict[str, Any] = resp

        success("Feedback added successfully!")
        click.echo(f"Feedback ID: {data.get('id', data.get('feedback_id', 'unknown'))}")
        click.echo(f"Overall Rating: {data.get('overall_rating', overall)}/5.0")
        click.echo(f"Moderation Status: {data.get('moderation_status', 'pending')}")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}")
    except Exception as e:
        abort(ctx, f"Error adding feedback: {e}", from_exception=e)
