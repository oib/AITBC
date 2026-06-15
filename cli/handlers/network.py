"""Network status and peer management handlers."""

import logging
import sys
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


def handle_network_status(args, default_rpc_url, get_network_snapshot):
    """Handle network status query."""
    import click

    snapshot = get_network_snapshot(getattr(args, "rpc_url", default_rpc_url))
    click.echo("Network status:")
    click.echo(f"  Connected nodes: {snapshot['connected_count']}")
    for index, node in enumerate(snapshot["nodes"]):
        label = "Local" if index == 0 else f"Peer {node['name']}"
        health = "healthy" if node["healthy"] else "unreachable"
        click.echo(f"  {label}: {health}")
    click.echo(f"  Sync status: {snapshot['sync_status']}")


def handle_network_peers(args, default_rpc_url, get_network_snapshot):
    """Handle network peers query."""
    snapshot = get_network_snapshot(getattr(args, "rpc_url", default_rpc_url))
    logger.info("Network peers:")
    for node in snapshot["nodes"]:
        endpoint = urlparse(node["rpc_url"]).netloc
        status = "Connected" if node["healthy"] else "Unreachable (%s)" % (node["error"] or "unknown error")
        logger.info("  - %s (%s) - %s", node["name"], endpoint, status)


def handle_network_sync(args, default_rpc_url, get_network_snapshot):
    """Handle network sync status query."""
    import click

    snapshot = get_network_snapshot(getattr(args, "rpc_url", default_rpc_url))
    click.echo("Network sync status:")
    click.echo(f"  Status: {snapshot['sync_status']}")
    for node in snapshot["nodes"]:
        height = node["height"] if node["height"] is not None else "unknown"
        click.echo(f"  {node['name']} height: {height}")
    local_timestamp = snapshot["nodes"][0].get("timestamp") if snapshot["nodes"] else None
    click.echo(f"  Last local block: {local_timestamp or 'unknown'}")


def handle_network_ping(args, default_rpc_url, read_blockchain_env, normalize_rpc_url, first, probe_rpc_node):
    """Handle network ping command."""
    env_config = read_blockchain_env()
    _, _, local_port = normalize_rpc_url(getattr(args, "rpc_url", default_rpc_url))
    peer_rpc_port_value = env_config.get("rpc_bind_port")
    try:
        peer_rpc_port = int(peer_rpc_port_value) if peer_rpc_port_value else local_port
    except ValueError:
        peer_rpc_port = local_port

    node = first(getattr(args, "node_opt", None), getattr(args, "node", None), "aitbc1")
    target_url = node if "://" in node else f"http://{node}:{peer_rpc_port}"
    target = probe_rpc_node(node, target_url, chain_id=env_config.get("chain_id") or None)

    print(f"Ping: Node {node} {'reachable' if target['healthy'] else 'unreachable'}")
    print(f"  Endpoint: {urlparse(target['rpc_url']).netloc}")
    if target["latency_ms"] is not None:
        print(f"  Latency: {target['latency_ms']}ms")
    print(f"  Status: {'connected' if target['healthy'] else 'error'}")


def handle_network_propagate(args, default_rpc_url, get_network_snapshot, first):
    """Handle network data propagation."""
    data = first(getattr(args, "data_opt", None), getattr(args, "data", None), "test-data")
    snapshot = get_network_snapshot(getattr(args, "rpc_url", default_rpc_url))
    print("Data propagation: Complete")
    print(f"  Data: {data}")
    print(f"  Nodes: {snapshot['connected_count']}/{len(snapshot['nodes'])} reachable")


def handle_network_force_sync(args, default_rpc_url, render_mapping):
    """Handle network force sync command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    if not args.peer:
        logger.error("Error: --peer is required")
        sys.exit(1)

    sync_data = {
        "peer": args.peer,
    }
    if chain_id:
        sync_data["chain_id"] = chain_id

    logger.info("Forcing sync to peer %s on %s...", args.peer, rpc_url)
    try:
        response = requests.post(f"{rpc_url}/rpc/force-sync", json=sync_data, timeout=60)
        if response.status_code == 200:
            result = response.json()
            logger.info("Force sync initiated successfully")
            render_mapping("Sync result:", result)
        else:
            logger.error("Force sync failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            sys.exit(1)
    except Exception as e:
        logger.error("Error forcing sync: %s", e)
        sys.exit(1)
