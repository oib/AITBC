"""
Bridge management commands for federated mesh.

v0.7.0 §B5: Replaced simulated data stubs with actual RPC calls.
- ``request`` calls ``POST /islands/bridge`` on the blockchain node
- ``list-bridges`` calls ``GET /bridge/health`` for cross-chain bridge status
- ``approve``/``reject`` have no server-side counterpart: the islands module
  completes bridge requests in one step and has no pending-request workflow,
  so both commands abort with an explanation instead of hitting dead routes.
"""

import asyncio

import click

from aitbc.bridge import BridgeClient, BridgeConfig

from aitbc_cli.utils import error, output
from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError


def _get_rpc_url(ctx) -> str:
    """Get the blockchain RPC URL from context or default."""
    url = ctx.obj.get("rpc_url", "http://localhost:8202")
    return str(url) if url is not None else "http://localhost:8202"


def _rpc_client(rpc_url: str) -> AITBCHTTPClient:
    """Blockchain-RPC client carrying the configured X-API-Key when present."""
    from aitbc_cli.config import get_config

    return AITBCHTTPClient(base_url=rpc_url, timeout=10, api_key=get_config().blockchain_rpc_api_key)


def request_bridge_command(ctx, target_island_id):
    """Request a bridge to another island"""
    rpc_url = _get_rpc_url(ctx)
    try:
        http_client = _rpc_client(rpc_url)
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
    error(
        "Bridge approval is not implemented on the blockchain node: "
        "POST /rpc/islands/bridge completes a bridge request in one step and "
        "the islands module has no pending-request workflow to approve."
    )
    raise click.Abort()


def reject_bridge_command(ctx, request_id, reason):
    """Reject a bridge request"""
    error(
        "Bridge rejection is not implemented on the blockchain node: "
        "POST /rpc/islands/bridge completes a bridge request in one step and "
        "the islands module has no pending-request workflow to reject."
    )
    raise click.Abort()


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
