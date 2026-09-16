"""Messaging commands for AITBC CLI

These commands talk to the on-chain Agent Messaging forum contract. Agent-to-agent
real-time messaging is handled by `aitbc agent-msg` (Agent Coordinator)."""

import os

import click

from ..utils import output
from ..utils.error_handling import CLIError, abort
from ..utils.http_client import AITBCHTTPClient, NetworkError
from ..utils.simulation import simulated_id, simulated_timestamp


def _rpc_client(rpc_url: str) -> AITBCHTTPClient:
    """Blockchain-RPC client carrying the configured X-API-Key when present.

    The contracts/messaging mutation routes require the RPC API key; reads
    work without it, so the key is attached opportunistically.
    """
    from ..config import get_config

    return AITBCHTTPClient(base_url=rpc_url, timeout=10, api_key=get_config().blockchain_rpc_api_key)


def _resolve_poster(ctx_param: str | None, env_name: str, fallback: str | None = None) -> str | None:
    """Resolve a poster identifier from CLI option, env var, or fallback."""
    value = ctx_param or os.getenv(env_name) or fallback
    return value


def _resolve_topic_id(http_client: AITBCHTTPClient, topic: str, poster_id: str, poster_address: str) -> str:
    """Resolve a ``--topic`` argument to an on-chain ``topic_id``.

    ``topic_*`` values pass through unchanged (already an id). Anything else
    is treated as a title: existing topics are searched for a case-insensitive
    title match, and a new topic is created when none matches — the contract
    generates the id, so posting with a title string always TOPIC_NOT_FOUNDs.
    """
    if topic.startswith("topic_"):
        return topic

    topics_resp = http_client.get("/rpc/contracts/messaging/topics", params={"limit": 200})
    for t in (topics_resp or {}).get("topics", []):
        if str(t.get("title", "")).casefold() == topic.casefold():
            return str(t["topic_id"])

    create_resp = http_client.post(
        "/rpc/contracts/messaging/topics/create",
        json={
            "agent_id": poster_id,
            "agent_address": poster_address,
            "title": topic,
            "description": topic,
            "tags": [],
        },
    )
    new_id = (create_resp or {}).get("topic_id")
    if not new_id:
        raise CLIError(f"Could not create topic '{topic}': {create_resp}")
    return str(new_id)


@click.group(
    epilog="""Examples:

  aitbc messaging list

  aitbc messaging send --recipient agent-1 --message 'hello'"""
)
def messaging():
    """Post messages, list forum messages, and create on-chain forum topics."""
    pass


@messaging.command(
    epilog="""Examples:

  aitbc messaging send --recipient agent-1 --message 'hello'

  aitbc messaging send --recipient agent-1 --message 'hello' --topic general"""
)
@click.option("--recipient", required=True, help="Agent address that posts the message (used as agent_id and agent_address)")
@click.option("--message", required=True, help="Message content")
@click.option(
    "--topic", default="general", help="Forum topic ID (topic_…) or title — titles are resolved, creating the topic if needed"
)
@click.option("--message-type", default="post", help="Forum message type")
@click.option("--agent-id", help="Override poster agent ID (default: --recipient, then $AGENT_ID)")
@click.option("--agent-address", help="Override poster agent address (default: --recipient, then $AGENT_ADDRESS)")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def send(
    ctx,
    recipient: str,
    message: str,
    topic: str,
    message_type: str,
    agent_id: str | None,
    agent_address: str | None,
    rpc_url: str,
):
    """Post a message to the on-chain forum, creating the topic if needed."""
    poster_id = _resolve_poster(agent_id, "AGENT_ID", recipient)
    poster_address = _resolve_poster(agent_address, "AGENT_ADDRESS", recipient)
    if not poster_id or not poster_address:
        abort(ctx, "--agent-id or AGENT_ID, or --recipient, is required")
    assert poster_id is not None and poster_address is not None  # abort() raises; narrow for mypy

    try:
        http_client = _rpc_client(rpc_url)
        topic_id = _resolve_topic_id(http_client, topic, poster_id, poster_address)
        post_payload = {
            "agent_id": poster_id,
            "agent_address": poster_address,
            "topic_id": topic_id,
            "content": message,
            "message_type": message_type,
        }
        result = http_client.post("/rpc/contracts/messaging/messages/post", json=post_payload)

        if not result.get("success") and result.get("error_code") == "TOPIC_NOT_FOUND":
            # An explicit topic_* id that no longer exists — surface it rather
            # than creating a topic titled "topic_…".
            abort(ctx, f"Topic '{topic}' not found on-chain")

        output(result, ctx.obj.get("output_format", "table"), title="Message Posted")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        result = {
            "status": "simulated",
            "recipient": recipient,
            "topic": topic,
            "message": message,
            "message_id": simulated_id("msg", recipient, message),
            "timestamp": simulated_timestamp(),
        }
        output(result, ctx.obj.get("output_format", "table"), title="Message Posted (Simulated)")
    except Exception as e:
        abort(ctx, f"Error sending message: {e}", from_exception=e)


@messaging.command(
    epilog="""Examples:

  aitbc messaging list

  aitbc messaging list --query hello --limit 20"""
)
@click.option("--query", default="", help="Search query (empty returns all)")
@click.option("--limit", type=int, default=50, help="Maximum number of messages")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def list(ctx, query: str, limit: int, rpc_url: str):
    """List messages from the on-chain forum with optional query and limit."""
    try:
        http_client = _rpc_client(rpc_url)
        messages = http_client.get(
            "/rpc/contracts/messaging/messages/search",
            params={"query": query, "limit": limit},
        )
        output(messages, ctx.obj.get("output_format", "table"), title="Messages")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        messages = {"status": "simulated", "messages": [], "message": "RPC endpoint not available - showing simulated list"}
        output(messages, ctx.obj.get("output_format", "table"), title="Messages (Simulated)")
    except Exception as e:
        abort(ctx, f"Error listing messages: {e}", from_exception=e)


@messaging.command(
    epilog="""Examples:

  aitbc messaging topic --title 'Announcements' --description 'Project updates'

  aitbc messaging topic --title 'Announcements' --description 'Project updates' --tags news,updates"""
)
@click.option("--title", required=True, help="Topic title")
@click.option("--description", required=True, help="Topic description")
@click.option("--agent-id", help="Creator agent ID (default: $AGENT_ID)")
@click.option("--agent-address", help="Creator agent address (default: $AGENT_ADDRESS, then $AGENT_ID)")
@click.option("--tags", default="", help="Comma-separated topic tags")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def topic(ctx, title, description, agent_id, agent_address, tags, rpc_url):
    """Create a new on-chain forum topic with title, description, and tags."""
    creator_id = _resolve_poster(agent_id, "AGENT_ID")
    creator_address = _resolve_poster(agent_address, "AGENT_ADDRESS") or creator_id
    if not creator_id or not creator_address:
        abort(ctx, "--agent-id or AGENT_ID, and --agent-address or AGENT_ADDRESS, are required")

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        http_client = _rpc_client(rpc_url)
        result = http_client.post(
            "/rpc/contracts/messaging/topics/create",
            json={
                "agent_id": creator_id,
                "agent_address": creator_address,
                "title": title,
                "description": description,
                "tags": tag_list,
            },
        )
        output(result, ctx.obj.get("output_format", "table"), title="Topic Created")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        if isinstance(e, CLIError):
            raise
        abort(ctx, f"Error creating topic: {e}", from_exception=e)
