"""Service and validator commands for ``aitbc bridge`` (start/stop/health/security/register/oracle)."""

import asyncio
import json
import secrets
from datetime import UTC, datetime
from typing import Any

import click
import httpx

from ._group import _get_bridge_client, bridge
from ._helpers import _OPS_ERRORS, _SERVICE_NAME, _derive_address, _event_bridge_status, _sign_dict, _systemctl
from ...utils import output
from ...utils.error_handling import abort


@bridge.command(
    epilog="""Examples:

  aitbc bridge start"""
)
@click.pass_context
def start(ctx):
    """Start the blockchain event bridge service."""
    ok, msg = _systemctl("start")
    if not ok:
        abort(ctx, f"Failed to start bridge service: {msg}")
        return
    import time

    time.sleep(2)
    result = _event_bridge_status()
    result["action"] = "start"
    result["service"] = _SERVICE_NAME
    output(result, ctx.obj.get("output_format", "table"), title="Bridge Started")


@bridge.command(
    epilog="""Examples:

  aitbc bridge stop"""
)
@click.pass_context
def stop(ctx):
    """Stop the blockchain event bridge service."""
    ok, msg = _systemctl("stop")
    if not ok:
        abort(ctx, f"Failed to stop bridge service: {msg}")
        return
    output(
        {"status": "stopped", "bridge_status": "stopped", "action": "stop", "service": _SERVICE_NAME},
        ctx.obj.get("output_format", "table"),
        title="Bridge Stopped",
    )


@bridge.command(
    epilog="""Examples:

  aitbc bridge health

  aitbc bridge health --rpc-url http://node2.example.net:8202/rpc"""
)
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def health(ctx, rpc_url):
    """Check the bridge service health and connected node status."""

    async def _health():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.health()

    try:
        result = asyncio.run(_health())
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Health")
    except _OPS_ERRORS as e:
        abort(ctx, f"Bridge health check failed: {e}", from_exception=e)


@bridge.command(
    name="security-status",
    epilog="""Examples:

  aitbc bridge security-status

  aitbc bridge security-status --output json""",
)
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def security_status(ctx, rpc_url):
    """Get bridge security status, multi-sig configuration, and threshold."""

    async def _security_status():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.security_status()

    try:
        result = asyncio.run(_security_status())
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Security Status")
    except _OPS_ERRORS as e:
        abort(ctx, f"Failed to get bridge security status: {e}", from_exception=e)


@bridge.command(
    name="register-validator",
    epilog="""Examples:

  aitbc bridge register-validator --chain-id ait-mainnet --address 0xAbc... --public-key 0xPub... --private-key 0xPriv...

  aitbc bridge register-validator --chain-id ait-mainnet --address 0xAbc... --public-key 0xPub... --private-key 0xPriv... --admin-private-key 0xAdmin...""",
)
@click.option("--chain-id", required=True, help="Chain ID the validator serves")
@click.option("--address", required=True, help="Validator's checksum address (0x...)")
@click.option("--public-key", required=True, help="Validator's secp256k1 public key hex (0x...)")
@click.option(
    "--private-key",
    required=True,
    help="Validator's private key hex (for signing the registration request)",
)
@click.option(
    "--admin-private-key", default=None, help="Bridge admin private key hex (required when bridge_release_enabled=true)"
)
@click.option("--admin-address", default=None, help="Bridge admin address (defaults to address of admin-private-key)")
@click.option("--epoch", default=0, type=int, help="Validator set epoch number (default: 0)")
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def register_validator(ctx, chain_id, address, public_key, private_key, admin_private_key, admin_address, epoch, rpc_url):
    """Register a bridge validator for multi-sig operations on a chain."""

    # Sign the registration request
    from aitbc.crypto.crypto import sign_transaction_hash

    # Build the canonical message for signing (matches RPC endpoint's verify_request_signature)
    sign_data = {"chain_id": chain_id, "address": address, "public_key": public_key, "action": "register"}
    msg = json.dumps(sign_data, sort_keys=True, separators=(",", ":")).encode()
    from eth_utils import keccak

    signature = sign_transaction_hash("0x" + keccak(msg).hex(), private_key)

    admin_address = admin_address or (_derive_address(admin_private_key) if admin_private_key else None)

    payload: dict[str, Any] = {
        "chain_id": chain_id,
        "address": address,
        "public_key": public_key,
        "signature": signature,
        "epoch": epoch,
    }
    if admin_private_key and admin_address:
        payload["admin_address"] = admin_address
        # Freshness/target fields the node's replay guard requires in signed payloads.
        # target_chain_id binds the node SERVING the request — its own chain
        # id, not the chain being registered (Refs #679).
        payload["issued_at"] = datetime.now(UTC).isoformat()
        payload["nonce"] = secrets.token_hex(16)
        payload["target_chain_id"] = chain_id  # fallback: same-chain registrations still work unprobed
        try:
            info = httpx.get(f"{rpc_url.rstrip('/')}/network-info", timeout=5).json()
            if info.get("node_id") not in (None, "unknown"):
                payload["target_node_id"] = info["node_id"]
            if info.get("chain_id"):
                payload["target_chain_id"] = info["chain_id"]
        except _OPS_ERRORS:  # noqa: BLE001,S110 - optional metadata probe: the unsigned payload still works
            pass
        # Admin signature covers the payload excluding admin_signature itself
        sign_payload = {k: v for k, v in payload.items() if k != "admin_signature"}
        payload["admin_signature"] = _sign_dict(admin_private_key, sign_payload)

    async def _register():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.register_validator(
                chain_id=chain_id,
                address=address,
                public_key=public_key,
                signature=signature,
                epoch=epoch,
                admin_address=payload.get("admin_address"),
                admin_signature=payload.get("admin_signature"),
                issued_at=payload.get("issued_at"),
                nonce=payload.get("nonce"),
                target_chain_id=payload.get("target_chain_id"),
                target_node_id=payload.get("target_node_id"),
            )

    try:
        result = asyncio.run(_register())
        output(result, ctx.obj.get("output_format", "table"), title="Validator Registration")
    except _OPS_ERRORS as e:
        abort(ctx, f"Validator registration failed: {e}", from_exception=e)


@bridge.command(
    name="oracle-status",
    epilog="""Examples:

  aitbc bridge oracle-status

  aitbc bridge oracle-status --rpc-url http://node2.example.net:8202/rpc""",
)
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def oracle_status(ctx, rpc_url):
    """Get bridge oracle and verification status."""

    async def _oracle_status():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.oracle_status()

    try:
        result = asyncio.run(_oracle_status())
        output(result, ctx.obj.get("output_format", "table"), title="Bridge Oracle Status")
    except _OPS_ERRORS as e:
        abort(ctx, f"Failed to get bridge oracle status: {e}", from_exception=e)
