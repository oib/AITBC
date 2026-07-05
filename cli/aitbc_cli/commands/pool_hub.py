"""Pool hub commands for AITBC CLI"""

import click

from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


@click.group()
def pool_hub():
    """Pool hub management for SLA monitoring and billing"""
    pass


@pool_hub.command()
@click.option("--pool-hub-url", default="http://localhost:8203", help="Pool Hub service URL")
@click.pass_context
def status(ctx, pool_hub_url):
    """Check pool hub status"""
    try:
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=10)
        status = http_client.get("/api/pools/status")
        output(status, ctx.obj.get("output_format", "table"), title="Pool Hub Status")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        status = {
            "status": "simulated",
            "pools": 0,
            "active_pools": 0,
            "message": "RPC endpoint not available - showing simulated status",
        }
        output(status, ctx.obj.get("output_format", "table"), title="Pool Hub Status (Simulated)")
    except Exception as e:
        abort(ctx, f"Error getting pool hub status: {e}", from_exception=e)


@pool_hub.command()
@click.option("--pool-id", help="Specific pool ID")
@click.option("--pool-hub-url", default="http://localhost:8203", help="Pool Hub service URL")
@click.pass_context
def sla(ctx, pool_id, pool_hub_url):
    """Monitor SLA"""
    try:
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=10)
        params = {}
        if pool_id:
            params["pool_id"] = pool_id
        sla_data = http_client.get("/api/pools/sla", params=params)
        output(sla_data, ctx.obj.get("output_format", "table"), title="SLA Monitor")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        sla_data = {
            "status": "simulated",
            "pool_id": pool_id or "default",
            "sla_compliance": 100,
            "message": "RPC endpoint not available - showing simulated SLA",
        }
        output(sla_data, ctx.obj.get("output_format", "table"), title="SLA Monitor (Simulated)")
    except Exception as e:
        abort(ctx, f"Error monitoring SLA: {e}", from_exception=e)
