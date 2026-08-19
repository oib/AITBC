"""Reputation management commands for AITBC CLI"""

import json
from decimal import Decimal
from typing import Any, cast

import click

from ..config import get_config
from ..utils import success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)

DEFAULT_COORDINATOR_URL = "http://localhost:8203"


def _coordinator_client(ctx: click.Context | None = None) -> AITBCHTTPClient:
    """Return an HTTP client for the coordinator API."""
    config = get_config()
    base_url = (config.coordinator_api_url or DEFAULT_COORDINATOR_URL).rstrip("/")
    api_key = config.api_key
    if ctx and ctx.obj:
        api_key = ctx.obj.get("api_key") or api_key
    return AITBCHTTPClient(base_url=base_url, api_key=api_key, timeout=30)


def _reputation_endpoint(path: str) -> str:
    """Build a /v1/reputation/* endpoint path."""
    return f"/v1/reputation{path}"


@click.group(name="reputation")
@click.pass_context
def reputation(ctx):
    """Reputation management commands"""
    ctx.ensure_object(dict)


@reputation.command("profile")
@click.argument("agent_id")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def get_profile(ctx, agent_id: str, format: str):
    """Get reputation profile for an agent"""
    try:
        http_client = _coordinator_client(ctx)
        resp = http_client.get(_reputation_endpoint(f"/profile/{agent_id}"))
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
        abort(ctx, f"Network error: {e}")
    except Exception as e:
        abort(ctx, f"Error getting reputation profile: {e}", from_exception=e)


@reputation.command("trust-score")
@click.argument("agent_id")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def trust_score(ctx, agent_id: str, format: str):
    """Get detailed trust score breakdown for an agent"""
    try:
        http_client = _coordinator_client(ctx)
        resp = http_client.get(_reputation_endpoint(f"/trust-score/{agent_id}"))
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


@reputation.command("leaderboard")
@click.option("--category", default="trust_score", help="Category to rank by")
@click.option("--limit", type=int, default=10, help="Number of results")
@click.option("--region", default=None, help="Filter by region")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def leaderboard(ctx, category: str, limit: int, region: str | None, format: str):
    """Get reputation leaderboard"""
    try:
        params: dict[str, Any] = {"category": category, "limit": limit}
        if region:
            params["region"] = region

        http_client = _coordinator_client(ctx)
        resp = http_client.get(_reputation_endpoint("/leaderboard"), params=params)
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


@reputation.command("metrics")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def metrics(ctx, format: str):
    """Get overall reputation system metrics"""
    try:
        http_client = _coordinator_client(ctx)
        resp = http_client.get(_reputation_endpoint("/metrics"))
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


@reputation.command("create-profile")
@click.argument("agent_id")
@click.pass_context
def create_profile(ctx, agent_id: str):
    """Create a new reputation profile for an agent"""
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


@reputation.command("feedback")
@click.argument("agent_id")
@click.argument("reviewer_id")
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
    """Add community feedback for an agent"""
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
