"""Cluster commands for AITBC CLI"""

import click
import httpx

from aitbc.exceptions import AITBCError
from ..utils import output, warning
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
    """Report cluster status scope — static placeholder; no live cluster backend exists."""
    try:
        # #2222: there is no cluster/swarm backend — the coordinator's
        # /v1/swarm/* mock routes were deliberately removed. The old
        # hardcoded {"healthy", nodes: 3} read as live fleet truth.
        # Report the honest scope instead of fabricated counts.
        warning("No cluster service is deployed — this is a static placeholder, not live fleet state")
        result = {
            "cluster_health": "unknown",
            "scope": "static-placeholder",
            "live_fleet_membership": False,
            "detail": (
                "aitbc cluster has no live backend. For this node's real peer "
                "view use 'aitbc network status' / 'aitbc network peers'."
            ),
        }
        output(result, ctx.obj.get("output_format", "table"), title="Cluster Status (Static — No Live Backend)")
    except _OPS_ERRORS as e:
        abort(ctx, f"Error getting cluster status: {e}", from_exception=e)


@cluster.command(
    epilog="""Examples:

  aitbc cluster sync

  aitbc cluster sync --output json"""
)
@click.pass_context
def sync(ctx):
    """Not implemented — no cluster service is deployed."""
    # #2222: no cluster backend exists — reporting a fabricated
    # "completed" for an action that never ran is worse than failing.
    abort(ctx, "Cluster sync is not implemented: no cluster service is deployed")


@cluster.command(
    epilog="""Examples:

  aitbc cluster balance

  aitbc cluster balance --output json"""
)
@click.pass_context
def balance(ctx):
    """Not implemented — no cluster service is deployed."""
    # #2222: no cluster backend exists — reporting a fabricated
    # "completed" for an action that never ran is worse than failing.
    abort(ctx, "Cluster balance is not implemented: no cluster service is deployed")
