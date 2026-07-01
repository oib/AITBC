"""
Bridge management commands for federated mesh.

v0.7.0 §B5: Replaced simulated data stubs with actual RPC calls.
- ``request`` calls ``POST /islands/bridge`` on the blockchain node
- ``approve``/``reject`` call the bridge manager via RPC (islands module)
- ``list-bridges`` calls ``GET /bridge/health`` for cross-chain bridge status
"""

import asyncio

import click

from aitbc.bridge import BridgeClient, BridgeConfig

from aitbc_cli.utils import error, output
from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError


def _get_rpc_url(ctx) -> str:
    """Get the blockchain RPC URL from context or default."""
    return ctx.obj.get("rpc_url", "http://localhost:8202")


def request_bridge_command(ctx, target_island_id):
    """Request a bridge to another island"""
    rpc_url = _get_rpc_url(ctx)
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/islands/bridge", json={"target_island_id": target_island_id})
        output(result, ctx.obj.get("output", "table"), title="Bridge Request")
    except NetworkError as e:
        error(f"Cannot connect to blockchain node at {rpc_url}: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error requesting bridge: {e}")
        raise click.Abort() from e


def approve_bridge_command(ctx, request_id, approving_node_id):
    """Approve a bridge request"""
    rpc_url = _get_rpc_url(ctx)
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post(
            "/rpc/islands/bridge/approve",
            json={"bridge_id": request_id, "approving_node_id": approving_node_id},
        )
        output(result, ctx.obj.get("output", "table"), title="Bridge Approved")
    except NetworkError as e:
        error(f"Cannot connect to blockchain node at {rpc_url}: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error approving bridge request: {e}")
        raise click.Abort() from e


def reject_bridge_command(ctx, request_id, reason):
    """Reject a bridge request"""
    rpc_url = _get_rpc_url(ctx)
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post(
            "/rpc/islands/bridge/reject",
            json={"bridge_id": request_id, "reason": reason or ""},
        )
        output(result, ctx.obj.get("output", "table"), title="Bridge Rejected")
    except NetworkError as e:
        error(f"Cannot connect to blockchain node at {rpc_url}: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error rejecting bridge request: {e}")
        raise click.Abort() from e


def list_bridges_command(ctx):
    """List bridge connections — shows cross-chain bridge health status"""
    rpc_url = _get_rpc_url(ctx)

    async def _health():
        client = BridgeClient(BridgeConfig(rpc_url=rpc_url))
        async with client:
            return await client.health()

    try:
        result = asyncio.run(_health())
        # Extract bridge-specific info from health response
        bridges = []
        if result.get("success"):
            bridges.append(
                {
                    "Status": result.get("status", "unknown"),
                    "Pending Transfers": result.get("pending_transfer_count", 0),
                    "Total Locked": result.get("total_locked_amount", 0),
                    "Release Enabled": result.get("release_enabled", False),
                }
            )
        output(bridges, ctx.obj.get("output", "table"), title="Bridge Connections")
    except Exception as e:
        error(f"Error listing bridges: {e}")
        raise click.Abort() from e
