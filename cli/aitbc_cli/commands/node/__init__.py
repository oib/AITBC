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
@node.command()
@click.argument("node_id")
@click.option("--realtime", is_flag=True, help="Real-time monitoring")
@click.option("--interval", default=5, help="Update interval in seconds")
@click.pass_context
def monitor(ctx, node_id, realtime, interval):
    """Monitor node activity"""
    monitor_command(ctx, node_id, realtime, interval)


@node.command()
@click.argument("node_id")
@click.pass_context
def test(ctx, node_id):
    """Test node connectivity"""
    test_command(ctx, node_id)


# Island group
@node.group()
def island():
    """Island management commands for federated mesh"""
    pass


@island.command()
@click.option("--island-id", help="Island ID (UUID), generates new if not provided")
@click.option("--island-name", default="default", help="Human-readable island name")
@click.option("--chain-id", help="Chain ID for this island")
@click.pass_context
def create(ctx, island_id, island_name, chain_id):
    """Create a new island"""
    create_island_command(ctx, island_id, island_name, chain_id)


@island.command()
@click.argument("island_id")
@click.argument("island_name")
@click.argument("chain_id")
@click.option("--hub", default="hub.aitbc.bubuit.net", help="Hub domain name to connect to")
@click.option("--is-hub", is_flag=True, help="Register this node as a hub for the island")
@click.pass_context
def join(ctx, island_id, island_name, chain_id, hub, is_hub):
    """Join an existing island"""
    join_island_command(ctx, island_id, island_name, chain_id, hub, is_hub)


@island.command()
@click.argument("island_id")
@click.pass_context
def leave(ctx, island_id):
    """Leave an island"""
    leave_island_command(ctx, island_id)


@island.command()
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.pass_context
def list_islands(ctx, node_url):
    """List all known islands (queries the node's island manager via RPC)"""
    list_islands_command(ctx, node_url=node_url)


@island.command(name="list")
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.pass_context
def list_islands_alias(ctx, node_url):
    """List all known islands (alias for list-islands)"""
    list_islands_command(ctx, node_url=node_url)


@island.command()
@click.argument("island_id")
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.pass_context
def island_info(ctx, island_id, node_url):
    """Get island information (queries the node's island manager via RPC)"""
    island_info_command(ctx, island_id, node_url=node_url)


@island.command()
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.option("--all", "show_all", is_flag=True, help="Show all islands including default")
@click.pass_context
def health(ctx, node_url, show_all):
    """Show health status of connected islands (status, peer count, activity)"""
    health_command(ctx, node_url=node_url, show_all=show_all)


# Hub group
@node.group()
def hub():
    """Hub management commands for federated mesh"""
    pass


@hub.command()
@click.option("--public-address", help="Public IP address")
@click.option("--public-port", type=int, help="Public port")
@click.option("--redis-url", default="redis://localhost:6379", help="Redis URL for persistence")
@click.option("--hub-discovery-url", default="hub.aitbc.bubuit.net", help="DNS hub discovery URL")
@click.pass_context
def register(ctx, public_address, public_port, redis_url, hub_discovery_url):
    """Register this node as a hub"""
    register_hub_command(ctx, public_address, public_port, redis_url, hub_discovery_url)


@hub.command()
@click.option("--redis-url", default="redis://localhost:6379", help="Redis URL for persistence")
@click.option("--hub-discovery-url", default="hub.aitbc.bubuit.net", help="DNS hub discovery URL")
@click.pass_context
def unregister(ctx, redis_url, hub_discovery_url):
    """Unregister this node as a hub"""
    unregister_hub_command(ctx, redis_url, hub_discovery_url)


@hub.command()
@click.option("--redis-url", default="redis://localhost:6379", help="Redis URL for persistence")
@click.pass_context
def list_hubs(ctx, redis_url):
    """List registered hubs from Redis"""
    list_hubs_command(ctx, redis_url)


# Bridge group
@node.group()
def bridge():
    """Bridge management commands for federated mesh"""
    pass


@bridge.command()
@click.argument("target_island_id")
@click.pass_context
def request(ctx, target_island_id):
    """Request a bridge to another island"""
    request_bridge_command(ctx, target_island_id)


@bridge.command()
@click.argument("request_id")
@click.argument("approving_node_id")
@click.pass_context
def approve(ctx, request_id, approving_node_id):
    """Approve a bridge request"""
    approve_bridge_command(ctx, request_id, approving_node_id)


@bridge.command()
@click.argument("request_id")
@click.option("--reason", help="Rejection reason")
@click.pass_context
def reject(ctx, request_id, reason):
    """Reject a bridge request"""
    reject_bridge_command(ctx, request_id, reason)


@bridge.command()
@click.pass_context
def list_bridges(ctx):
    """List bridge connections"""
    list_bridges_command(ctx)


# Chain group
@node.group()
def chain():
    """Multi-chain management commands for parallel chains"""
    pass


@chain.command()
@click.argument("chain_id")
@click.option("--chain-type", type=click.Choice(["bilateral", "micro"]), default="micro", help="Chain type")
@click.pass_context
def start(ctx, chain_id, chain_type):
    """Start a new parallel chain instance"""
    start_chain_command(ctx, chain_id, chain_type)


@chain.command()
@click.argument("chain_id")
@click.pass_context
def stop(ctx, chain_id):
    """Stop a parallel chain instance"""
    stop_chain_command(ctx, chain_id)


@chain.command()
@click.pass_context
def list_chains(ctx):
    """List all active chain instances"""
    list_chains_command(ctx)


__all__ = ["node"]
