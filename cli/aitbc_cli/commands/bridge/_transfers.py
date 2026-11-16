"""Transfer-lifecycle commands for ``aitbc bridge`` (lock/confirm/unlock/status/pending/balance)."""

import asyncio
import json
import secrets
import time
from pathlib import Path

import click

from ._group import _get_bridge_client, _resolve_node_chain_id, bridge
from ._helpers import _OPS_ERRORS, _derive_address, _event_bridge_status, _load_private_key, _sign_dict
from ...utils import output, warning
from ...utils.error_handling import abort


@bridge.command(
    epilog="""Examples:

  aitbc bridge lock --target-chain ait-side --sender 0xAbc... --recipient 0xC10... --amount 100

  aitbc bridge lock --target-chain ait-side --amount 50 --wallet-name genesis"""
)
@click.option("--target-chain", required=True, help="Target chain ID for the transfer")
@click.option("--sender", required=True, help="Sender address (source chain)")
@click.option("--recipient", required=True, help="Recipient address (target chain)")
@click.option("--amount", required=True, type=int, help="Amount to bridge (in compute-units)")
@click.option("--asset", default="native", help="Asset type (default: native)")
@click.option(
    "--source-chain",
    default=None,
    help="Source chain ID (defaults to the node's own chain, resolved from --rpc-url before signing)",
)
@click.option(
    "--signature",
    default="",
    help="Sender signature authorizing the lock (hex). Sign the dict documented under --issued-at.",
)
@click.option(
    "--issued-at",
    default=None,
    type=int,
    help=(
        "Epoch seconds the external signer stamped into the signed dict. With --signature, "
        "--issued-at and --nonce must be given together; omit both for the legacy six-field form "
        "(refused by nodes with BRIDGE_LOCK_REQUIRE_REPLAY_GUARD=true). The signed dict is "
        '{"source_chain","target_chain","sender","recipient","amount","asset","issued_at","nonce"} '
        "— canonical JSON (sort_keys, separators=(',',':')), keccak256, secp256k1. "
        "amount is integer compute-units; source_chain must equal what the server verifies: "
        "the body's source_chain when --source-chain is given, else the node's own chain ID "
        "(see GET /rpc/proposer)."
    ),
)
@click.option(
    "--nonce",
    default=None,
    help="Replay nonce the external signer included in the signed dict (non-empty string). Give together with --issued-at.",
)
@click.option("--wallet-name", default=None, help="Wallet to sign the lock with (generates issued_at/nonce itself)")
@click.option("--wallet-password", default="", help="Password if the wallet is encrypted")
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def lock(
    ctx,
    target_chain,
    sender,
    recipient,
    amount,
    asset,
    source_chain,
    signature,
    issued_at,
    nonce,
    wallet_name,
    wallet_password,
    rpc_url,
):
    """Lock funds for a cross-chain bridge transfer."""

    if wallet_name:
        if issued_at is not None or nonce is not None:
            raise click.ClickException("--issued-at/--nonce are generated automatically with --wallet-name; drop them")
        private_key = _load_private_key(wallet_name, wallet_password)
        if not source_chain:
            source_chain = _resolve_node_chain_id(rpc_url)
        # SEC-REPLAY-1: the replay guard fields ride inside the signed dict —
        # a captured signed body can no longer be re-posted.
        issued_at = int(time.time())
        nonce = secrets.token_hex(16)
        sign_data = {
            "source_chain": source_chain,
            "target_chain": target_chain,
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "asset": asset,
            "issued_at": issued_at,
            "nonce": nonce,
        }
        signature = _sign_dict(private_key, sign_data)
    elif (issued_at is None) != (nonce is None):
        raise click.ClickException("--issued-at and --nonce must be given together")
    elif signature and issued_at is None:
        warning(
            "submitting an old-form (six-field) signed body — nodes with "
            "BRIDGE_LOCK_REQUIRE_REPLAY_GUARD=true refuse it with 400; pass --issued-at/--nonce "
            "matching the dict the external signer signed"
        )

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
                issued_at=issued_at,
                nonce=nonce,
            )

    try:
        result = asyncio.run(_lock())
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Lock")
    except _OPS_ERRORS as e:
        abort(ctx, f"Bridge lock failed: {e}", from_exception=e)


@bridge.command(
    epilog="""Examples:

  aitbc bridge confirm --transfer-id tx-123 --confirmer 0xAbc... --proof-file /tmp/proof.json

  aitbc bridge confirm --transfer-id tx-123 --confirmer-private-key 0x... --proof-file /tmp/proof.json"""
)
@click.option("--transfer-id", required=True, help="Transfer ID to confirm")
@click.option("--confirmer", required=True, help="Confirmer address")
@click.option("--signature", default="", help="Confirmer signature (hex)")
@click.option("--confirmer-private-key", default=None, help="Private key to sign the confirm request")
@click.option("--proof-file", required=True, type=click.Path(exists=True), help="JSON file containing the lock proof")
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def confirm(ctx, transfer_id, confirmer, signature, confirmer_private_key, proof_file, rpc_url):
    """Confirm and release a cross-chain bridge transfer using a proof file."""
    try:
        proof = json.loads(Path(proof_file).read_text())
    except _OPS_ERRORS as e:
        abort(ctx, f"Failed to read proof file: {e}", from_exception=e)

    if confirmer_private_key:
        sign_data = {"transfer_id": transfer_id, "confirmer": confirmer}
        signature = _sign_dict(confirmer_private_key, sign_data)

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
    except _OPS_ERRORS as e:
        abort(ctx, f"Bridge confirm failed: {e}", from_exception=e)


@bridge.command(
    epilog="""Examples:

  aitbc bridge unlock --transfer-id tx-123 --sender 0xAbc... --signature 0x...

  aitbc bridge unlock --transfer-id tx-123 --sender 0xAbc... --wallet-name ipfsbuyer

  aitbc bridge unlock --transfer-id tx-123 --sender 0xAbc... --signature 0x... --rpc-url http://node2.example.net:8202/rpc"""
)
@click.option("--transfer-id", required=True, help="Transfer ID to refund")
@click.option("--sender", required=True, help="Original sender address")
@click.option("--signature", default="", help="Sender signature authorizing the unlock (hex); or use --wallet-name")
@click.option("--wallet-name", default=None, help="Wallet to sign the unlock with")
@click.option("--wallet-password", default="", help="Password if the wallet is encrypted")
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def unlock(ctx, transfer_id, sender, signature, wallet_name, wallet_password, rpc_url):
    """Refund or cancel a pending bridge transfer."""

    if wallet_name and signature:
        raise click.ClickException("Pass either --signature or --wallet-name, not both")
    if wallet_name:
        private_key = _load_private_key(wallet_name, wallet_password)
        if _derive_address(private_key).lower() != sender.lower():
            raise click.ClickException("--sender does not match the wallet's address")
        signature = _sign_dict(private_key, {"transfer_id": transfer_id, "sender": sender, "action": "unlock"})
    if not signature:
        raise click.ClickException("Either --signature or --wallet-name is required")

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
    except _OPS_ERRORS as e:
        abort(ctx, f"Bridge unlock failed: {e}", from_exception=e)


@bridge.command(
    epilog="""Examples:

  aitbc bridge status

  aitbc bridge status --transfer-id tx-123"""
)
@click.option("--transfer-id", "transfer_id", required=False, help="Transfer ID.")
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def status(ctx, transfer_id, rpc_url):
    """Get bridge service status or a specific transfer status."""
    if not transfer_id:
        result = _event_bridge_status()
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Status")
        return

    async def _status():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.get_transfer(transfer_id)

    try:
        result = asyncio.run(_status())
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Transfer Status")
    except _OPS_ERRORS as e:
        abort(ctx, f"Failed to get bridge status: {e}", from_exception=e)


@bridge.command(
    epilog="""Examples:

  aitbc bridge pending

  aitbc bridge pending --chain-id ait-mainnet"""
)
@click.option("--chain-id", default=None, help="Filter by chain ID")
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def pending(ctx, chain_id, rpc_url):
    """List pending bridge transfers, optionally filtered by chain."""

    async def _pending():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.list_pending(chain_id=chain_id)

    try:
        result = asyncio.run(_pending())
        output(result, ctx.obj.get("output_format", "table"), title="Pending Bridge Transfers")
    except _OPS_ERRORS as e:
        abort(ctx, f"Failed to list pending transfers: {e}", from_exception=e)


@bridge.command(
    epilog="""Examples:

  aitbc bridge balance --chain-id ait-mainnet

  aitbc bridge balance --chain-id ait-mainnet --output json"""
)
@click.option("--chain-id", required=True, help="Chain ID to query balance for")
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def balance(ctx, chain_id, rpc_url):
    """Get the total locked bridge balance for a chain."""

    async def _balance():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.get_balance(chain_id)

    try:
        result = asyncio.run(_balance())
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Balance")
    except _OPS_ERRORS as e:
        abort(ctx, f"Failed to get bridge balance: {e}", from_exception=e)
