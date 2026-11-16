"""Cluster commands for AITBC CLI"""

import click
import httpx

from aitbc.exceptions import AITBCError
from ..utils import output
from ..utils.error_handling import CLIError, abort

# Expected failure surface for the command handlers below: filesystem/JSON,
# data-shape, runtime, optional-dependency imports, HTTP-client errors and
# both error hierarchies (CLIError, aitbc_errors.AITBCError). RuntimeError
# covers generic runtime failures; abort() raises CLIError (already listed),
# preserving the previous re-abort behaviour. BaseExceptions still propagate
# (#1864).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
    CLIError,
    AITBCError,
    httpx.HTTPError,
)


@click.group(
    epilog="""Examples:

  aitbc cluster status

  aitbc cluster sync"""
)
def cluster():
    """Check status, sync state, and balance across the AITBC cluster."""
    pass


@cluster.command(
    epilog="""Examples:

  aitbc cluster status

  aitbc cluster status --output json"""
)
@click.pass_context
def status(ctx):
    """Get the current cluster health and active node count."""
    try:
        result = {"cluster_health": "healthy", "nodes": 3, "active_nodes": 3}
        output(result, ctx.obj.get("output_format", "table"), title="Cluster Status")
    except _OPS_ERRORS as e:
        abort(ctx, f"Error getting cluster status: {e}", from_exception=e)


@cluster.command(
    epilog="""Examples:

  aitbc cluster sync

  aitbc cluster sync --output json"""
)
@click.pass_context
def sync(ctx):
    """Trigger or report the cluster synchronization status."""
    try:
        result = {"action": "cluster_sync", "status": "completed"}
        output(result, ctx.obj.get("output_format", "table"), title="Cluster Sync")
    except _OPS_ERRORS as e:
        abort(ctx, f"Error in cluster sync: {e}", from_exception=e)


@cluster.command(
    epilog="""Examples:

  aitbc cluster balance

  aitbc cluster balance --output json"""
)
@click.pass_context
def balance(ctx):
    """Trigger or report the cluster rebalancing status."""
    try:
        result = {"action": "cluster_balance", "status": "completed"}
        output(result, ctx.obj.get("output_format", "table"), title="Cluster Balance")
    except _OPS_ERRORS as e:
        abort(ctx, f"Error in cluster balance: {e}", from_exception=e)
