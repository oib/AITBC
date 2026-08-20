"""Pool hub commands for AITBC CLI"""

import click

from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError

# aitbc-pool-hub.service binds 8210.  Both commands defaulted to 8203, which is
# coordinator-api — so every invocation queried the wrong service (V23-96).
DEFAULT_POOL_HUB_URL = "http://localhost:8210"


@click.group()
def pool_hub():
    """Pool hub management for SLA monitoring and billing"""
    pass


@pool_hub.command()
@click.option("--pool-hub-url", default=DEFAULT_POOL_HUB_URL, help="Pool Hub service URL")
@click.pass_context
def status(ctx, pool_hub_url):
    """Check pool hub status"""
    try:
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=10)
        # /api/pools/status is not a route pool-hub serves, and never was; a 404
        # became a NetworkError and was answered with invented numbers (V23-96).
        status = http_client.get("/health")
        output(status, ctx.obj.get("output_format", "table"), title="Pool Hub Status")
    except NetworkError as e:
        abort(ctx, f"Pool Hub at {pool_hub_url} is unreachable: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting pool hub status: {e}", from_exception=e)


@pool_hub.command()
@click.option("--pool-id", help="Specific pool ID")
@click.option("--pool-hub-url", default=DEFAULT_POOL_HUB_URL, help="Pool Hub service URL")
@click.pass_context
def sla(ctx, pool_id, pool_hub_url):
    """Monitor SLA"""
    # Pool Hub tracks miners, not pools — it has no route that filters SLA by a
    # pool ID.  Rejecting the flag beats accepting it and returning unfiltered
    # data as though it had been applied.
    if pool_id:
        abort(ctx, "Pool Hub reports SLA per miner, not per pool; --pool-id has no effect and is not supported.")
    try:
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=10)
        sla_data = http_client.get("/v1/sla/status")
        output(sla_data, ctx.obj.get("output_format", "table"), title="SLA Monitor")
    except NetworkError as e:
        abort(ctx, f"Pool Hub at {pool_hub_url} is unreachable: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error monitoring SLA: {e}", from_exception=e)
