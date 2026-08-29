"""
Node management commands for AITBC
"""

import click

from .bridge import (
    approve_bridge_command,
    list_bridges_command,
    reject_bridge_command,
    request_bridge_command,
)
from .chain import list_chains_command, start_chain_command, stop_chain_command
from .hub import list_hubs_command, register_hub_command, unregister_hub_command
from .island import (
    create_island_command,
    health_command,
    island_info_command,
    join_island_command,
    leave_island_command,
    list_islands_command,
)
from .main import node
from .monitor import monitor_command, test_command


# Attach main commands
@node.command(
    epilog="""Examples:

  aitbc node monitor --node-id node-1

  aitbc node monitor --node-id node-1 --realtime"""
)
@click.option("--node-id", "node_id", required=True, help="The Node id.")
@click.option("--realtime", is_flag=True, help="Real-time monitoring")
@click.option("--interval", default=5, help="Update interval in seconds")
@click.pass_context
def monitor(ctx, node_id, realtime, interval):
    """Monitor activity for a specific node."""
    monitor_command(ctx, node_id, realtime, interval)


@node.command(
    epilog="""Examples:

  aitbc node test --node-id node-1

  aitbc node test --node-id node-1 --output json"""
)
@click.option("--node-id", "node_id", required=True, help="The Node id.")
@click.pass_context
def test(ctx, node_id):
    """Test connectivity to a specific node."""
    test_command(ctx, node_id)


# Island group
@node.group(
    epilog="""Examples:

  aitbc node island create --island-name hub-island

  aitbc node island list"""
)
def island():
    """Manage islands in the federated mesh."""
    pass


@island.command(
    epilog="""Examples:

  aitbc node island create --island-name hub-island

  aitbc node island create --island-id uuid --island-name hub --chain-id ait-mainnet"""
)
@click.option("--island-id", help="Island ID (UUID), generates new if not provided")
@click.option("--island-name", default="default", help="Human-readable island name")
@click.option("--chain-id", help="Chain ID for this island")
@click.pass_context
def create(ctx, island_id, island_name, chain_id):
    """Create a new island with optional ID, name, and chain."""
    create_island_command(ctx, island_id, island_name, chain_id)


@island.command(
    epilog="""Examples:

  aitbc node island join --island-id uuid --island-name hub --chain-id ait-mainnet

  aitbc node island join --island-id uuid --island-name hub --chain-id ait-mainnet --hub hub.aitbc.bubuit.net"""
)
@click.option("--island-id", "island_id", required=True, help="The Island id.")
@click.option("--island-name", "island_name", required=True, help="The Island name.")
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--hub", default="hub.aitbc.bubuit.net", help="Hub domain name to connect to")
@click.option("--is-hub", is_flag=True, help="Register this node as a hub for the island")
@click.option("--rpc-url", default=None, help="RPC base URL for the join request (defaults to config.blockchain_rpc_url)")
@click.pass_context
def join(ctx, island_id, island_name, chain_id, hub, is_hub, rpc_url):
    """Join an existing island by ID, name, and chain."""
    join_island_command(ctx, island_id, island_name, chain_id, hub, is_hub, rpc_url=rpc_url)


@island.command(
    epilog="""Examples:

  aitbc node island leave --island-id uuid"""
)
@click.option("--island-id", "island_id", required=True, help="The Island id.")
@click.pass_context
def leave(ctx, island_id):
    """Leave an island by its ID."""
    leave_island_command(ctx, island_id)


@island.command(
    name="list-islands",
    epilog="""Examples:

  aitbc node island list-islands

  aitbc node island list-islands --node-url http://127.0.0.1:8202""",
)
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.pass_context
def list_islands(ctx, node_url):
    """List all known islands from the node's island manager."""
    list_islands_command(ctx, node_url=node_url)


@island.command(
    name="list",
    epilog="""Examples:

  aitbc node island list

  aitbc node island list --node-url http://127.0.0.1:8202""",
)
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.pass_context
def list_islands_alias(ctx, node_url):
    """List all known islands (alias for list-islands)."""
    list_islands_command(ctx, node_url=node_url)


@island.command(
    epilog="""Examples:

  aitbc node island info --island-id uuid

  aitbc node island info --island-id uuid --node-url http://127.0.0.1:8202"""
)
@click.option("--island-id", "island_id", required=True, help="The Island id.")
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.pass_context
def island_info(ctx, island_id, node_url):
    """Get detailed information for an island."""
    island_info_command(ctx, island_id, node_url=node_url)


@island.command(
    epilog="""Examples:

  aitbc node island health

  aitbc node island health --all"""
)
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.option("--all", "show_all", is_flag=True, help="Show all islands including default")
@click.pass_context
def health(ctx, node_url, show_all):
    """Show health status of connected islands."""
    health_command(ctx, node_url=node_url, show_all=show_all)


# Hub group
@node.group(
    epilog="""Examples:

  aitbc node hub list-hubs

  aitbc node hub register --public-address 1.2.3.4"""
)
def hub():
    """Register, unregister, and list hub nodes in the federated mesh."""
    pass


@hub.command(
    epilog="""Examples:

  aitbc node hub register --public-address 1.2.3.4 --public-port 8202

  aitbc node hub register --public-address 1.2.3.4 --redis-url redis://localhost:6379"""
)
@click.option("--public-address", help="Public IP address")
@click.option("--public-port", type=int, help="Public port")
@click.option("--redis-url", default="redis://localhost:6379", help="Redis URL for persistence")
@click.option("--hub-discovery-url", default="hub.aitbc.bubuit.net", help="DNS hub discovery URL")
@click.pass_context
def register(ctx, public_address, public_port, redis_url, hub_discovery_url):
    """Register this node as a hub."""
    register_hub_command(ctx, public_address, public_port, redis_url, hub_discovery_url)


@hub.command(
    epilog="""Examples:

  aitbc node hub unregister

  aitbc node hub unregister --redis-url redis://localhost:6379"""
)
@click.option("--redis-url", default="redis://localhost:6379", help="Redis URL for persistence")
@click.option("--hub-discovery-url", default="hub.aitbc.bubuit.net", help="DNS hub discovery URL")
@click.pass_context
def unregister(ctx, redis_url, hub_discovery_url):
    """Unregister this node as a hub."""
    unregister_hub_command(ctx, redis_url, hub_discovery_url)


@hub.command(
    epilog="""Examples:

  aitbc node hub list-hubs

  aitbc node hub list-hubs --redis-url redis://localhost:6379"""
)
@click.option("--redis-url", default="redis://localhost:6379", help="Redis URL for persistence")
@click.pass_context
def list_hubs(ctx, redis_url):
    """List all registered hubs from Redis."""
    list_hubs_command(ctx, redis_url)


# Bridge group
@node.group(
    epilog="""Examples:

  aitbc node bridge list-bridges

  aitbc node bridge request --target-island-id island-2"""
)
def bridge():
    """Manage bridge connections between islands and approve or reject bridge requests."""
    pass


@bridge.command(
    epilog="""Examples:

  aitbc node bridge request --target-island-id island-2"""
)
@click.option("--target-island-id", "target_island_id", required=True, help="The Target island id.")
@click.pass_context
def request(ctx, target_island_id):
    """Request a bridge to another island."""
    request_bridge_command(ctx, target_island_id)


@bridge.command(
    epilog="""Examples:

  aitbc node bridge approve --request-id req-123 --approving-node-id node-1"""
)
@click.option("--request-id", "request_id", required=True, help="The Request id.")
@click.option("--approving-node-id", "approving_node_id", required=True, help="The Approving node id.")
@click.pass_context
def approve(ctx, request_id, approving_node_id):
    """Approve a bridge request from another island."""
    approve_bridge_command(ctx, request_id, approving_node_id)


@bridge.command(
    epilog="""Examples:

  aitbc node bridge reject --request-id req-123

  aitbc node bridge reject --request-id req-123 --reason 'not authorized'"""
)
@click.option("--request-id", "request_id", required=True, help="The Request id.")
@click.option("--reason", help="Rejection reason")
@click.pass_context
def reject(ctx, request_id, reason):
    """Reject a bridge request from another island."""
    reject_bridge_command(ctx, request_id, reason)


@bridge.command(
    epilog="""Examples:

  aitbc node bridge list-bridges

  aitbc node bridge list-bridges --output json"""
)
@click.pass_context
def list_bridges(ctx):
    """List all bridge connections and their current status."""
    list_bridges_command(ctx)


# Chain group
@node.group(
    epilog="""Examples:

  aitbc node chain list-chains

  aitbc node chain start --chain-id side-1"""
)
def chain():
    """Start, stop, and list parallel chain instances on the node."""
    pass


@chain.command(
    epilog="""Examples:

  aitbc node chain start --chain-id side-1

  aitbc node chain start --chain-id side-1 --chain-type micro"""
)
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.option("--chain-type", type=click.Choice(["bilateral", "micro"]), default="micro", help="Chain type")
@click.pass_context
def start(ctx, chain_id, chain_type):
    """Start a new parallel chain instance."""
    start_chain_command(ctx, chain_id, chain_type)


@chain.command(
    epilog="""Examples:

  aitbc node chain stop --chain-id side-1"""
)
@click.option("--chain-id", "chain_id", required=True, help="The Chain id.")
@click.pass_context
def stop(ctx, chain_id):
    """Stop a running parallel chain instance."""
    stop_chain_command(ctx, chain_id)


@chain.command(
    epilog="""Examples:

  aitbc node chain list-chains

  aitbc node chain list-chains --output json"""
)
@click.pass_context
def list_chains(ctx):
    """List all currently active chain instances."""
    list_chains_command(ctx)


__all__ = ["node"]
