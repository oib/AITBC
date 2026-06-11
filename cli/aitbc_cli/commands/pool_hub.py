"""Pool hub commands for AITBC CLI"""

import click

from ..utils import error, output
from ..utils.http_client import AITBCHTTPClient, NetworkError


@click.group()
def pool_hub():
    """Pool hub management for SLA monitoring and billing"""
    pass


@pool_hub.command()
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def status(ctx, rpc_url):
    """Check pool hub status"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        status = http_client.get("/rpc/pool_hub/status")
        output(status, ctx.obj.get('output_format', 'table'), title="Pool Hub Status")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        status = {
            "status": "simulated",
            "pools": 0,
            "active_pools": 0,
            "message": "RPC endpoint not available - showing simulated status"
        }
        output(status, ctx.obj.get('output_format', 'table'), title="Pool Hub Status (Simulated)")
    except Exception as e:
        error(f"Error getting pool hub status: {e}")
        raise click.Abort()


@pool_hub.command()
@click.option('--pool-id', help='Specific pool ID')
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def sla(ctx, pool_id, rpc_url):
    """Monitor SLA"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        params = {}
        if pool_id:
            params["pool_id"] = pool_id
        sla_data = http_client.get("/rpc/pool_hub/sla", params=params)
        output(sla_data, ctx.obj.get('output_format', 'table'), title="SLA Monitor")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        sla_data = {
            "status": "simulated",
            "pool_id": pool_id or "default",
            "sla_compliance": 100,
            "message": "RPC endpoint not available - showing simulated SLA"
        }
        output(sla_data, ctx.obj.get('output_format', 'table'), title="SLA Monitor (Simulated)")
    except Exception as e:
        error(f"Error monitoring SLA: {e}")
        raise click.Abort()
