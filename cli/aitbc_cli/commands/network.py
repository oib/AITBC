"""Network commands for AITBC CLI"""

import click

from aitbc import AITBCHTTPClient, NetworkError

from ..utils import error, output


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
