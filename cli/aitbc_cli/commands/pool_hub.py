"""Pool hub commands for AITBC CLI"""

import os

import click

from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError

# aitbc-pool-hub.service binds 8210 on the hub. Shop/follower nodes do not run
# it (V23-92), so localhost is only valid when NODE_ROLE=hub.
DEFAULT_POOL_HUB_URL = "http://localhost:8210"


def _default_pool_hub_url() -> str:
    """Local 8210 on the hub; otherwise the hub's public pool-hub URL."""
    if os.getenv("NODE_ROLE", "").strip().lower() == "hub":
        return DEFAULT_POOL_HUB_URL
    explicit = os.getenv("HUB_POOL_HUB_URL") or os.getenv("POOL_HUB_URL")
    if explicit:
        return explicit.rstrip("/")
    from aitbc.config.hub import hub_service_url

    resolved = hub_service_url("pool-hub")
    return resolved or DEFAULT_POOL_HUB_URL


@click.group()
def pool_hub():
    """Pool hub management for SLA monitoring and billing"""
    pass


@pool_hub.command()
@click.option("--pool-hub-url", default=None, help="Pool Hub service URL")
@click.pass_context
def status(ctx, pool_hub_url):
    """Check pool hub status"""
    try:
        pool_hub_url = pool_hub_url or _default_pool_hub_url()
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
@click.option("--pool-hub-url", default=None, help="Pool Hub service URL")
@click.pass_context
def sla(ctx, pool_id, pool_hub_url):
    """Monitor SLA"""
    # Pool Hub tracks miners, not pools — it has no route that filters SLA by a
    # pool ID.  Rejecting the flag beats accepting it and returning unfiltered
    # data as though it had been applied.
    if pool_id:
        abort(ctx, "Pool Hub reports SLA per miner, not per pool; --pool-id has no effect and is not supported.")
    try:
        pool_hub_url = pool_hub_url or _default_pool_hub_url()
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=10)
        sla_data = http_client.get("/v1/sla/status")
        output(sla_data, ctx.obj.get("output_format", "table"), title="SLA Monitor")
    except NetworkError as e:
        abort(ctx, f"Pool Hub at {pool_hub_url} is unreachable: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error monitoring SLA: {e}", from_exception=e)
