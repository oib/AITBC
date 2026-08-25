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
    """Resolve the pool-hub URL.

    The pool-hub service runs on the hub (port 8210).  On shop/follower nodes
    we use the public hub path, discovered from HUB_RPC_URL/HUB_DISCOVERY_URL.
    The NODE_ROLE environment variable (set in /etc/aitbc/node.env) lets a hub
    node keep using localhost.
    """
    explicit = os.getenv("POOL_HUB_URL") or os.getenv("HUB_POOL_HUB_URL")
    if explicit:
        return explicit.rstrip("/")

    node_role = os.getenv("NODE_ROLE", "")
    if node_role == "hub" or os.path.exists("/etc/aitbc/node.env") and _is_hub_node():
        return DEFAULT_POOL_HUB_URL

    try:
        from aitbc.config.hub import hub_discovery_host

        host = hub_discovery_host()
        if host:
            return f"http://{host}/pool-hub"
    except Exception:
        pass

    return DEFAULT_POOL_HUB_URL


def _is_hub_node() -> bool:
    try:
        with open("/etc/aitbc/node.env") as f:
            for line in f:
                if line.startswith("NODE_ROLE=") and line.strip().split("=", 1)[1].lower() == "hub":
                    return True
    except Exception:
        pass
    return False


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
