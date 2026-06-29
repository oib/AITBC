"""Bridge commands for AITBC CLI.

v0.7.0 §B3: Replaced the broken ``start``/``status``/``stop`` commands (which
called non-existent ``/rpc/bridge/start`` etc. and fell back to simulated data)
with actual bridge RPC commands using ``aitbc.bridge.BridgeClient``.
"""

import asyncio
import json
from pathlib import Path

import click

from aitbc.bridge import BridgeClient, BridgeConfig

from ..utils import error, output


def _get_bridge_client(rpc_url: str) -> BridgeClient:
    """Create a BridgeClient pointing at the given blockchain RPC URL."""
    return BridgeClient(BridgeConfig(rpc_url=rpc_url))


@click.group()
def bridge():
    """Cross-chain bridge management"""
    pass


@bridge.command()
@click.option("--target-chain", required=True, help="Target chain ID for the transfer")
@click.option("--sender", required=True, help="Sender address (source chain)")
@click.option("--recipient", required=True, help="Recipient address (target chain)")
@click.option("--amount", required=True, type=int, help="Amount to bridge (in compute-seconds)")
@click.option("--asset", default="native", help="Asset type (default: native)")
@click.option("--source-chain", default=None, help="Source chain ID (defaults to node's chain)")
@click.option("--signature", default="", help="Sender signature authorizing the lock")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def lock(ctx, target_chain, sender, recipient, amount, asset, source_chain, signature, rpc_url):
    """Lock funds for a cross-chain bridge transfer"""

    async def _lock():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.lock(
                target_chain=target_chain,
                sender=sender,
                recipient=recipient,
                amount=amount,
                asset=asset,
                signature=signature,
                source_chain=source_chain,
            )

    try:
        result = asyncio.run(_lock())
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Lock")
    except Exception as e:
        error(f"Bridge lock failed: {e}")
        raise click.Abort() from e


@bridge.command()
@click.option("--transfer-id", required=True, help="Transfer ID to confirm")
@click.option("--confirmer", required=True, help="Confirmer address")
@click.option("--signature", required=True, help="Confirmer signature")
@click.option("--proof-file", required=True, type=click.Path(exists=True), help="JSON file containing the lock proof")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def confirm(ctx, transfer_id, confirmer, signature, proof_file, rpc_url):
    """Confirm and release a cross-chain bridge transfer"""
    try:
        proof = json.loads(Path(proof_file).read_text())
    except Exception as e:
        error(f"Failed to read proof file: {e}")
        raise click.Abort() from e

    async def _confirm():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.confirm(
                transfer_id=transfer_id,
                proof=proof,
                confirmer=confirmer,
                signature=signature,
            )

    try:
        result = asyncio.run(_confirm())
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Confirm")
    except Exception as e:
        error(f"Bridge confirm failed: {e}")
        raise click.Abort() from e


@bridge.command()
@click.option("--transfer-id", required=True, help="Transfer ID to refund")
@click.option("--sender", required=True, help="Original sender address")
@click.option("--signature", required=True, help="Sender signature authorizing the unlock")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def unlock(ctx, transfer_id, sender, signature, rpc_url):
    """Refund/cancel a pending bridge transfer"""

    async def _unlock():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.unlock(
                transfer_id=transfer_id,
                sender=sender,
                signature=signature,
            )

    try:
        result = asyncio.run(_unlock())
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Unlock")
    except Exception as e:
        error(f"Bridge unlock failed: {e}")
        raise click.Abort() from e


@bridge.command()
@click.option("--transfer-id", required=True, help="Transfer ID to query")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def status(ctx, transfer_id, rpc_url):
    """Get the status of a cross-chain bridge transfer"""

    async def _status():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.get_transfer(transfer_id)

    try:
        result = asyncio.run(_status())
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Transfer Status")
    except Exception as e:
        error(f"Failed to get bridge status: {e}")
        raise click.Abort() from e


@bridge.command()
@click.option("--chain-id", default=None, help="Filter by chain ID")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def pending(ctx, chain_id, rpc_url):
    """List pending bridge transfers"""

    async def _pending():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.list_pending(chain_id=chain_id)

    try:
        result = asyncio.run(_pending())
        output(result, ctx.obj.get("output_format", "table"), title="Pending Bridge Transfers")
    except Exception as e:
        error(f"Failed to list pending transfers: {e}")
        raise click.Abort() from e


@bridge.command()
@click.option("--chain-id", required=True, help="Chain ID to query balance for")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def balance(ctx, chain_id, rpc_url):
    """Get bridge balance for a chain (total locked amount)"""

    async def _balance():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.get_balance(chain_id)

    try:
        result = asyncio.run(_balance())
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Balance")
    except Exception as e:
        error(f"Failed to get bridge balance: {e}")
        raise click.Abort() from e


@bridge.command()
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def health(ctx, rpc_url):
    """Check bridge health status"""

    async def _health():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.health()

    try:
        result = asyncio.run(_health())
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Health")
    except Exception as e:
        error(f"Bridge health check failed: {e}")
        raise click.Abort() from e
