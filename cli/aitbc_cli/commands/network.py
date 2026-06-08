"""Network commands for AITBC CLI"""

import os
import click

from ..utils.http_client import AITBCHTTPClient, NetworkError

from ..utils import error, output


def get_default_node_id() -> str | None:
    """Get default node ID from environment file"""
    # Try to read from /etc/aitbc/node.env
    env_file = "/etc/aitbc/node.env"
    if os.path.exists(env_file):
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("NODE_ID="):
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
    # Fallback to environment variable
    return os.getenv("NODE_ID")


def get_default_chain_id() -> str | None:
    """Get default chain ID from environment file"""
    # Try to read from /etc/aitbc/node.env
    env_file = "/etc/aitbc/node.env"
    if os.path.exists(env_file):
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SUPPORTED_CHAINS="):
                        # SUPPORTED_CHAINS can be comma-separated, take first
                        chains = line.split("=", 1)[1].strip()
                        return chains.split(",")[0].strip()
        except Exception:
            pass
    # Fallback to environment variable
    return os.getenv("SUPPORTED_CHAINS")


@click.group()
def network():
    """Peer connectivity and network operations"""
    pass


@network.command()
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def status(ctx, rpc_url):
    """Check network status"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        status = http_client.get("/rpc/network-info")
        output(status, ctx.obj.get('output_format', 'table'), title="Network Status")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        status = {
            "network_status": "simulated",
            "connected_peers": 0,
            "block_height": 0,
            "message": "RPC endpoint not available - showing simulated status"
        }
        output(status, ctx.obj.get('output_format', 'table'), title="Network Status (Simulated)")
    except Exception as e:
        error(f"Error getting network status: {e}")
        raise click.Abort()


@network.command()
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def peers(ctx, rpc_url):
    """List connected peers"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        peers = http_client.get("/rpc/network-info")
        output(peers, ctx.obj.get('output_format', 'table'), title="Connected Peers")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        peers = {
            "status": "simulated",
            "peers": [],
            "message": "RPC endpoint not available - showing simulated peers"
        }
        output(peers, ctx.obj.get('output_format', 'table'), title="Connected Peers (Simulated)")
    except Exception as e:
        error(f"Error listing peers: {e}")
        raise click.Abort()


@network.command()
@click.option('--peer', required=True, help='Peer address to test')
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def test(ctx, peer, rpc_url):
    """Test connectivity to a peer"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/force-sync", json={"peer": peer})
        output(result, ctx.obj.get('output_format', 'table'), title=f"Connectivity Test: {peer}")
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error testing connectivity: {e}")
        raise click.Abort()


@network.command()
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def force_sync(ctx, rpc_url):
    """Force network synchronization"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/force-sync", json={})
        output(result, ctx.obj.get('output_format', 'table'), title="Force Sync")
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error forcing sync: {e}")
        raise click.Abort()


@network.command()
@click.option('--node-id', help='Unique identifier for this follower node (default: from NODE_ID in /etc/aitbc/node.env)')
@click.option('--transport', default='websocket', type=click.Choice(['websocket', 'http', 'redis']), help='Transport method for block delivery')
@click.option('--chain-id', help='Chain ID to subscribe to (default: from SUPPORTED_CHAINS in /etc/aitbc/node.env)')
@click.option('--duration', type=int, default=300, help='Lease duration in seconds (default: 300)')
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def subscribe(ctx, node_id, transport, chain_id, duration, rpc_url):
    """Register this node as a follower for block subscription"""
    if not node_id:
        node_id = get_default_node_id()
        if not node_id:
            error("node-id is required. Set NODE_ID in /etc/aitbc/node.env or use --node-id option")
            raise click.Abort()
    
    if not chain_id:
        chain_id = get_default_chain_id()
        if not chain_id:
            error("chain-id is required. Set SUPPORTED_CHAINS in /etc/aitbc/node.env or use --chain-id option")
            raise click.Abort()
    
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        subscription_data = {
            "node_id": node_id,
            "transport": transport,
            "chain_id": chain_id,
            "duration": duration
        }
        result = http_client.post("/rpc/subscribe", json=subscription_data)
        output(result, ctx.obj.get('output_format', 'table'), title="Subscription Registered")
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error registering subscription: {e}")
        raise click.Abort()


@network.command()
@click.option('--node-id', help='Subscriber node ID (default: from NODE_ID in /etc/aitbc/node.env)')
@click.option('--duration', type=int, help='Additional lease duration in seconds')
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def heartbeat(ctx, node_id, duration, rpc_url):
    """Send heartbeat to extend subscription lease"""
    if not node_id:
        node_id = get_default_node_id()
        if not node_id:
            error("node-id is required. Set NODE_ID in /etc/aitbc/node.env or use --node-id option")
            raise click.Abort()
    
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        heartbeat_data = {
            "node_id": node_id,
            "duration": duration
        }
        result = http_client.post("/rpc/subscription/heartbeat", json=heartbeat_data)
        output(result, ctx.obj.get('output_format', 'table'), title="Lease Extended")
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error extending lease: {e}")
        raise click.Abort()


@network.command()
@click.option('--node-id', help='Subscriber node ID (default: from NODE_ID in /etc/aitbc/node.env)')
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def lease_status(ctx, node_id, rpc_url):
    """Check lease status for a subscriber"""
    if not node_id:
        node_id = get_default_node_id()
        if not node_id:
            error("node-id is required. Set NODE_ID in /etc/aitbc/node.env or use --node-id option")
            raise click.Abort()
    
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.get(f"/rpc/subscription/lease-status?node_id={node_id}")
        output(result, ctx.obj.get('output_format', 'table'), title="Lease Status")
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error checking lease status: {e}")
        raise click.Abort()


@network.command()
@click.option('--chain-id', help='Filter by chain ID')
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def subscribers(ctx, chain_id, rpc_url):
    """List all active subscribers"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        params = {"chain_id": chain_id} if chain_id else {}
        result = http_client.get("/rpc/subscription/subscribers", params=params)
        output(result, ctx.obj.get('output_format', 'table'), title="Active Subscribers")
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error listing subscribers: {e}")
        raise click.Abort()
