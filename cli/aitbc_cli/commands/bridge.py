"""Bridge commands for AITBC CLI"""

import click

from aitbc import AITBCHTTPClient, NetworkError

from ..utils import error, output


@click.group()
def bridge():
    """Blockchain event bridge management"""
    pass


@bridge.command()
@click.option('--rpc-url', default='http://localhost:8006', help='Blockchain RPC URL')
@click.pass_context
def start(ctx, rpc_url):
    """Start bridge service"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/bridge/start")
        output(result, ctx.obj.get('output_format', 'table'), title="Bridge Started")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        result = {
            "status": "simulated",
            "bridge_status": "started",
            "message": "RPC endpoint not available - showing simulated start"
        }
        output(result, ctx.obj.get('output_format', 'table'), title="Bridge Started (Simulated)")
    except Exception as e:
        error(f"Error starting bridge: {e}")
        raise click.Abort()


@bridge.command()
@click.option('--rpc-url', default='http://localhost:8006', help='Blockchain RPC URL')
@click.pass_context
def status(ctx, rpc_url):
    """Check bridge status"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        status = http_client.get("/rpc/bridge/status")
        output(status, ctx.obj.get('output_format', 'table'), title="Bridge Status")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        status = {
            "status": "simulated",
            "bridge_status": "stopped",
            "message": "RPC endpoint not available - showing simulated status"
        }
        output(status, ctx.obj.get('output_format', 'table'), title="Bridge Status (Simulated)")
    except Exception as e:
        error(f"Error getting bridge status: {e}")
        raise click.Abort()


@bridge.command()
@click.option('--rpc-url', default='http://localhost:8006', help='Blockchain RPC URL')
@click.pass_context
def stop(ctx, rpc_url):
    """Stop bridge service"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/bridge/stop")
        output(result, ctx.obj.get('output_format', 'table'), title="Bridge Stopped")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        result = {
            "status": "simulated",
            "bridge_status": "stopped",
            "message": "RPC endpoint not available - showing simulated stop"
        }
        output(result, ctx.obj.get('output_format', 'table'), title="Bridge Stopped (Simulated)")
    except Exception as e:
        error(f"Error stopping bridge: {e}")
        raise click.Abort()
