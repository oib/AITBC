"""Cross-chain agent communication commands for AITBC CLI"""

from datetime import datetime
from typing import Any

import click

from ..utils import output, success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, get_logger

logger = get_logger(__name__)


def _fmt(ctx: click.Context, command_format: str) -> str:
    """Respect command --format first, then global --output, then table."""
    if command_format and command_format != "table":
        return command_format
    return ctx.obj.get("output_format", "table") or "table"


def _agent_client(ctx: click.Context) -> AITBCHTTPClient:
    """Build an HTTP client for the agent-coordinator endpoints."""
    config = ctx.obj["config"]
    # Hermes was deprecated and renamed to the agent-coordinator public /v1 mount.
    # The agent-coordinator app exposes /agents/... via nginx location /v1/.
    base_url = config.coordinator_api_url or config.agent_coordinator_url or "http://localhost:8107"
    api_key = ctx.obj.get("api_key") or config.api_key
    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key
    return AITBCHTTPClient(base_url=base_url, headers=headers, timeout=30)


@click.group(
    epilog="""Examples:

  aitbc agent-comm list

  aitbc agent-comm status --agent-id agent-1"""
)
def agent_comm():
    """Register, discover, and communicate with AITBC agents across chains."""
    pass


@agent_comm.command(
    epilog="""Examples:

  aitbc agent-comm register --agent-id agent-1 --name 'Shop Agent' --chain-id ait-mainnet --endpoint http://aitbc3:8107

  aitbc agent-comm register --agent-id agent-2 --name 'Hub Agent' --chain-id ait-mainnet --endpoint http://hub.aitbc:8107 --capabilities gpu,storage"""
)
@click.option("--agent-id", "agent_id", required=True, help="The Agent id.")
@click.option("--name", "name", required=True, help="Wallet name.")
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--endpoint", "endpoint", required=True, help="The Endpoint.")
@click.option("--capabilities", help="Comma-separated list of capabilities")
@click.option("--reputation", default=0.5, help="Initial reputation score")
@click.option("--version", default="1.0.0", help="Agent version")
@click.option("--agent-type", default="worker", help="Agent type (worker, specialist, etc.)")
@click.pass_context
def register(ctx, agent_id, name, chain_id, endpoint, capabilities, reputation, version, agent_type):
    """Register a new agent in the cross-chain network with its metadata and endpoint."""
    try:
        cap_list = [c.strip() for c in capabilities.split(",")] if capabilities else []
        client = _agent_client(ctx)
        payload = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "capabilities": cap_list,
            "services": cap_list,
            "endpoints": {"http": endpoint},
            "metadata": {
                "name": name,
                "reputation": float(reputation),
                "version": version,
                "endpoint": endpoint,
            },
            "chain_id": chain_id,
            "island_id": "",
        }
        result = client.post("/v1/agents/register", json=payload)
        if result.get("status") == "success":
            success(f"Agent {agent_id} registered successfully!")
            agent_data = {
                "Agent ID": agent_id,
                "Name": name,
                "Chain ID": chain_id,
                "Status": "active",
                "Capabilities": ", ".join(cap_list),
                "Reputation": f"{float(reputation):.2f}",
                "Endpoint": endpoint,
                "Version": version,
            }
            output(agent_data, ctx.obj.get("output_format", "table"))
        else:
            abort(ctx, f"Failed to register agent {agent_id}")
    except Exception as e:
        abort(ctx, f"Error registering agent: {str(e)}", from_exception=e)


@agent_comm.command(
    name="list",
    epilog="""Examples:

  aitbc agent-comm list

  aitbc agent-comm list --status active --chain-id ait-mainnet""",
)
@click.option("--chain-id", help="Filter by chain ID")
@click.option("--status", type=click.Choice(["active", "inactive", "busy", "offline"]), help="Filter by status")
@click.option("--capabilities", help="Filter by capabilities (comma-separated)")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list_agents(ctx, chain_id, status, capabilities, output_format):
    """List agents registered in the cross-chain network with optional filters."""
    try:
        client = _agent_client(ctx)
        query: dict[str, Any] = {"status": status or "active", "limit": 100}
        if chain_id:
            query["chain_id"] = chain_id
        if capabilities:
            query["capabilities"] = [c.strip() for c in capabilities.split(",")]
        result = client.post("/v1/agents/discover", json=query)
        agents = result.get("agents", [])
        if not agents:
            output({"message": "No agents found"}, _fmt(ctx, output_format))
            return

        agent_data = []
        for agent in agents:
            metadata = agent.get("metadata", {}) or {}
            last_seen = agent.get("last_heartbeat", "")
            if isinstance(last_seen, str) and last_seen:
                try:
                    last_seen = datetime.fromisoformat(last_seen).strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
            agent_data.append(
                {
                    "Agent ID": agent.get("agent_id"),
                    "Name": metadata.get("name", agent.get("agent_id")),
                    "Chain ID": agent.get("chain_id", ""),
                    "Status": agent.get("status", ""),
                    "Reputation": f"{float(metadata.get('reputation', 0.5)):.2f}",
                    "Capabilities": ", ".join(agent.get("capabilities", [])[:3]),
                    "Last Seen": last_seen,
                }
            )

        output(agent_data, _fmt(ctx, output_format), title="Registered Agents")
    except Exception as e:
        abort(ctx, f"Error listing agents: {str(e)}", from_exception=e)


@agent_comm.command(
    epilog="""Examples:

  aitbc agent-comm discover ait-mainnet

  aitbc agent-comm discover ait-mainnet --capabilities inference"""
)
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--capabilities", help="Required capabilities (comma-separated)")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def discover(ctx, chain_id, capabilities, output_format):
    """Discover active agents on a specific chain by chain ID."""
    try:
        client = _agent_client(ctx)
        cap_list = [c.strip() for c in capabilities.split(",")] if capabilities else None
        query: dict[str, Any] = {"chain_id": chain_id, "status": "active"}
        if cap_list:
            query["capabilities"] = cap_list
        result = client.post("/v1/agents/discover", json=query)
        agents = result.get("agents", [])
        if not agents:
            output({"message": f"No agents found on chain {chain_id}"}, _fmt(ctx, output_format))
            return

        agent_data = [
            {
                "Agent ID": agent.get("agent_id"),
                "Name": agent.get("metadata", {}).get("name", agent.get("agent_id")),
                "Status": agent.get("status", ""),
                "Reputation": f"{float(agent.get('metadata', {}).get('reputation', 0.5)):.2f}",
                "Capabilities": ", ".join(agent.get("capabilities", [])),
                "Endpoint": agent.get("endpoints", {}).get("http", ""),
                "Version": agent.get("metadata", {}).get("version", "1.0.0"),
            }
            for agent in agents
        ]

        output(agent_data, _fmt(ctx, output_format), title=f"Agents on Chain {chain_id}")
    except Exception as e:
        abort(ctx, f"Error discovering agents: {str(e)}", from_exception=e)


@agent_comm.command(
    epilog="""Examples:

  aitbc agent-comm status --agent-id agent-1

  aitbc agent-comm status --agent-id agent-1 --format json"""
)
@click.option("--agent-id", "agent_id", required=True, help="The Agent id.")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def status(ctx, agent_id, output_format):
    """Get detailed status and metadata for a registered agent."""
    try:
        client = _agent_client(ctx)
        result = client.get(f"/v1/agents/{agent_id}")
        agent = result.get("agent", {})
        if not agent:
            abort(ctx, f"Agent {agent_id} not found")

        metadata = agent.get("metadata", {}) or {}
        status_data = [
            {"Metric": "Agent ID", "Value": agent.get("agent_id", "N/A")},
            {"Metric": "Name", "Value": metadata.get("name", "N/A")},
            {"Metric": "Chain ID", "Value": agent.get("chain_id", "N/A")},
            {"Metric": "Status", "Value": agent.get("status", "N/A")},
            {"Metric": "Reputation", "Value": f"{float(metadata.get('reputation', 0)):.3f}"},
            {"Metric": "Capabilities", "Value": ", ".join(agent.get("capabilities", []))},
            {"Metric": "Message Queue Size", "Value": metadata.get("message_queue_size", 0)},
            {"Metric": "Active Collaborations", "Value": metadata.get("active_collaborations", 0)},
            {"Metric": "Last Seen", "Value": agent.get("last_heartbeat", "N/A")},
            {"Metric": "Endpoint", "Value": agent.get("endpoints", {}).get("http", "N/A")},
            {"Metric": "Version", "Value": metadata.get("version", "N/A")},
        ]

        output(status_data, _fmt(ctx, output_format), title=f"Agent Status: {agent_id}")
    except Exception as e:
        abort(ctx, f"Error getting agent status: {str(e)}", from_exception=e)


@agent_comm.command(
    epilog="""Examples:

  aitbc agent-comm network

  aitbc agent-comm network --format json"""
)
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def network(ctx, output_format):
    """Get an overview of the cross-chain agent network and distribution."""
    try:
        client = _agent_client(ctx)
        result = client.post("/v1/agents/discover", json={"status": "active", "limit": 1000})
        agents = result.get("agents", [])

        total = len(agents)
        active = sum(1 for a in agents if a.get("status") == "active")
        agents_by_chain: dict[str, int] = {}
        active_by_chain: dict[str, int] = {}
        reputation_sum = 0.0
        reputation_count = 0

        for agent in agents:
            chain_id = agent.get("chain_id", "unknown") or "unknown"
            agents_by_chain[chain_id] = agents_by_chain.get(chain_id, 0) + 1
            if agent.get("status") == "active":
                active_by_chain[chain_id] = active_by_chain.get(chain_id, 0) + 1
            rep = float(agent.get("metadata", {}).get("reputation", 0))
            reputation_sum += rep
            reputation_count += 1

        overview_data = [
            {"Metric": "Total Agents", "Value": total},
            {"Metric": "Active Agents", "Value": active},
            {"Metric": "Total Collaborations", "Value": 0},
            {"Metric": "Active Collaborations", "Value": 0},
            {"Metric": "Total Messages", "Value": 0},
            {"Metric": "Queued Messages", "Value": 0},
            {"Metric": "Average Reputation", "Value": f"{reputation_sum / max(1, reputation_count):.3f}"},
            {"Metric": "Routing Table Size", "Value": total},
            {"Metric": "Discovery Cache Size", "Value": total},
        ]

        output(overview_data, _fmt(ctx, output_format), title="Network Overview")

        if agents_by_chain:
            chain_data = [
                {
                    "Chain ID": chain_id,
                    "Total Agents": count,
                    "Active Agents": active_by_chain.get(chain_id, 0),
                }
                for chain_id, count in agents_by_chain.items()
            ]
            output(chain_data, _fmt(ctx, output_format), title="Agents by Chain")
    except Exception as e:
        abort(ctx, f"Error getting network overview: {str(e)}", from_exception=e)


@agent_comm.command(
    epilog="""Examples:

  aitbc agent-comm send --sender-id agent-1 --receiver-id agent-2 --message-type ping --chain-id ait-mainnet

  aitbc agent-comm send --sender-id agent-1 --receiver-id agent-2 --message-type task --chain-id ait-mainnet --payload '{"job":"123"}'"""
)
@click.option("--sender-id", "sender_id", required=True, help="The Sender id.")
@click.option("--receiver-id", "receiver_id", required=True, help="The Receiver id.")
@click.option("--message-type", "message_type", required=True, help="The Message type.")
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--payload", default="{}", help="JSON payload string")
@click.option("--target-chain", help="Target chain for cross-chain messages")
@click.option("--priority", default=5, help="Message priority (1-10)")
@click.option("--ttl", default=3600, help="Time to live in seconds")
@click.pass_context
def send(ctx, sender_id, receiver_id, message_type, chain_id, payload, target_chain, priority, ttl):
    """Send a message from a sender to a receiver agent on a specific chain."""
    output(
        {"message": "Agent-to-agent send is not available via the coordinator API"},
        ctx.obj.get("output_format", "table"),
    )


@agent_comm.command(
    epilog="""Examples:

  aitbc agent-comm collaborate --agent-ids agent-1 --agent-ids agent-2 --collaboration-type pool

  aitbc agent-comm collaborate --agent-ids agent-1 --agent-ids agent-2 --agent-ids agent-3 --collaboration-type federation --governance '{"quorum":2}'"""
)
@click.option("--agent-ids", "agent_ids", required=True, multiple=True, help="The Agent ids.")
@click.option("--collaboration-type", "collaboration_type", required=True, help="The Collaboration type.")
@click.option("--governance", help="Governance rules (JSON string)")
@click.pass_context
def collaborate(ctx, agent_ids, collaboration_type, governance):
    """Create a multi-agent collaboration with a list of agent IDs."""
    output(
        {"message": "Agent collaboration is not available via the coordinator API"},
        ctx.obj.get("output_format", "table"),
    )


@agent_comm.command(
    epilog="""Examples:

  aitbc agent-comm reputation --agent-id agent-1 --interaction-result success --feedback 0.95

  aitbc agent-comm reputation --agent-id agent-1 --interaction-result failure"""
)
@click.option("--agent-id", "agent_id", required=True, help="The Agent id.")
@click.option(
    "--interaction-result",
    "interaction_result",
    required=True,
    type=click.Choice(["success", "failure"]),
    help="The Interaction result.",
)
@click.option("--feedback", type=float, help="Feedback score (0.0-1.0)")
@click.pass_context
def reputation(ctx, agent_id, interaction_result, feedback):
    """Update the reputation score for an agent based on an interaction result."""
    output(
        {"message": "Agent reputation update is not available via the coordinator API"},
        ctx.obj.get("output_format", "table"),
    )


@agent_comm.command(
    epilog="""Examples:

  aitbc agent-comm monitor

  aitbc agent-comm monitor --realtime --interval 5"""
)
@click.option("--realtime", is_flag=True, help="Real-time monitoring")
@click.option("--interval", default=10, help="Update interval in seconds")
@click.pass_context
def monitor(ctx, realtime, interval):
    """Monitor cross-chain agent communication in real time or at an interval."""
    output(
        {"message": "Real-time agent monitor is not available via the coordinator API"},
        ctx.obj.get("output_format", "table"),
    )


@agent_comm.command(
    name="receive",
    epilog="""Examples:

  aitbc agent-comm receive --receiver-id agent-1

  aitbc agent-comm receive --receiver-id agent-1 --limit 20 --format json""",
)
@click.option("--receiver-id", "receiver_id", required=True, help="The Receiver id.")
@click.option("--limit", default=10, help="Maximum number of messages to return")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def receive(ctx, receiver_id, limit, format):
    """Receive queued messages for a receiver agent from the coordinator."""
    try:
        client = _agent_client(ctx)
        result = client.get(f"/v1/agents/{receiver_id}/messages", params={"limit": limit})
        output(result, _fmt(ctx, format))
    except Exception as e:
        output({"message": f"Error receiving messages: {e}"}, _fmt(ctx, format))
