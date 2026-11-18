"""Proof and block-header commands for ``aitbc bridge`` (proof/sign-proof/store/ingest/attest)."""

import asyncio
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

import click
import httpx

from ._group import _get_bridge_client, bridge
from ._helpers import _OPS_ERRORS, _abort_ops, _derive_address, _fetch_block_header, _sign_dict, _sign_header
from ...utils import output
from ...utils.error_handling import abort


@bridge.command(
    name="proof",
    epilog="""Examples:

  aitbc bridge proof --transfer-id tx-123

  aitbc bridge proof --transfer-id tx-123 --source-chain ait-mainnet --block-height 100""",
)
@click.option("--transfer-id", "transfer_id", required=True, help="Transfer ID.")
@click.option("--source-chain", default=None, help="Source chain ID (defaults to node's chain)")
@click.option("--block-height", default=1, type=int, help="Block height to anchor the proof")
@click.option("--block-hash", default=None, help="Block hash to anchor the proof")
@click.option(
    "--output", "-o", "output_path", required=True, type=click.Path(), help="JSON file to write the unsigned proof to"
)
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def get_proof(ctx, transfer_id, source_chain, block_height, block_hash, output_path, rpc_url):
    """Build a Merkle proof for a locked bridge transfer."""

    async def _proof():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.get_proof(
                transfer_id,
                source_chain=source_chain,
                block_height=block_height,
                block_hash=block_hash,
            )

    try:
        result = asyncio.run(_proof())
        proof = result.get("proof", result)
        Path(output_path).write_text(json.dumps(proof, indent=2, sort_keys=True))
        output(
            {"success": True, "transfer_id": transfer_id, "proof_file": output_path},
            ctx.obj.get("output_format", "table"),
            title="Bridge Proof",
        )
    except _OPS_ERRORS as e:
        _abort_ops(ctx, "Failed to build bridge proof", e)


@bridge.command(
    name="sign-proof",
    epilog="""Examples:

  aitbc bridge sign-proof --proof-file /tmp/proof.json --private-key 0x...

  aitbc bridge sign-proof --proof-file /tmp/proof.json --private-key 0x... --private-key 0x... --output /tmp/signed-proof.json""",
)
@click.option("--proof-file", required=True, type=click.Path(exists=True), help="Unsigned proof JSON file")
@click.option(
    "--private-key",
    required=True,
    multiple=True,
    help="Private key hex to sign with (use multiple times for multi-sig; first becomes proposer_signature)",
)
@click.option("--output", "-o", "output_path", default=None, type=click.Path(), help="Output file (defaults to proof-file)")
@click.pass_context
def sign_proof(ctx, proof_file, private_key, output_path):
    """Sign a bridge proof with one or more validator private keys."""
    try:
        proof = json.loads(Path(proof_file).read_text())
    except _OPS_ERRORS as e:
        _abort_ops(ctx, "Failed to read proof file", e)

    if not isinstance(proof, dict):
        abort(ctx, f"Proof file must contain a JSON object, got {type(proof).__name__}")

    if not private_key:
        abort(ctx, "At least one --private-key is required")

    # Build the canonical message from the proof (excluding any signature fields)
    sign_fields = {k: v for k, v in proof.items() if k not in ("proposer_signature", "validator_signatures")}

    signatures: list[str] = []
    for pk in private_key:
        signatures.append(_sign_dict(pk, sign_fields))

    proof["proposer_signature"] = signatures[0]
    proof["validator_signatures"] = signatures

    out_file = output_path or proof_file
    try:
        Path(out_file).write_text(json.dumps(proof, indent=2, sort_keys=True))
    except _OPS_ERRORS as e:
        _abort_ops(ctx, "Failed to write signed proof", e)

    output(
        {"success": True, "proof_file": out_file, "signatures": len(signatures)},
        ctx.obj.get("output_format", "table"),
        title="Signed Bridge Proof",
    )


@bridge.command(
    name="store-header",
    epilog="""Examples:

  aitbc bridge store-header --proof-file /tmp/signed-proof.json --admin-private-key 0x...

  aitbc bridge store-header --proof-file /tmp/signed-proof.json --admin-private-key 0x... --rpc-url http://node2.example.net:8202/rpc""",
)
@click.option("--proof-file", required=True, type=click.Path(exists=True), help="Signed proof JSON file")
@click.option("--admin-private-key", required=True, help="Private key of a configured bridge admin")
@click.option("--admin-address", default=None, help="Admin address (defaults to address of admin-private-key)")
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL of the target node")
@click.pass_context
def store_header(ctx, proof_file, admin_private_key, admin_address, rpc_url):
    """Store a bridge block header on the target node from a signed proof."""
    try:
        proof = json.loads(Path(proof_file).read_text())
    except _OPS_ERRORS as e:
        _abort_ops(ctx, "Failed to read proof file", e)

    # Validate before touching fields — a minimal/hand-written fixture must
    # abort cleanly instead of raising an unhandled KeyError (#2236).
    if not isinstance(proof, dict):
        abort(ctx, f"Proof file must contain a JSON object, got {type(proof).__name__}")
    missing = [field for field in ("chain_id", "block_height", "block_hash", "state_root") if not proof.get(field)]
    if missing:
        abort(ctx, f"Proof file missing required field(s): {', '.join(missing)}")

    proposer = _derive_address(admin_private_key) if not admin_address else admin_address
    header_fields = {
        "chain_id": proof["chain_id"],
        "height": proof["block_height"],
        "hash": proof["block_hash"],
        "parent_hash": "0x" + "00" * 32,
        "proposer": proposer,
        "state_root": proof["state_root"],
    }
    # The block header signature signs the block fields (same message as verify_block_header)
    header_signature = _sign_dict(admin_private_key, header_fields)

    header_data = {
        **header_fields,
        "signature": header_signature,
        "confirmation_count": 0,
        "finality_confirmed": False,
        "admin_address": proposer,
        "issued_at": datetime.now(UTC).isoformat(),
        "nonce": secrets.token_hex(16),
    }
    # Bind to the receiving node's identity (the stored chain is the SOURCE
    # chain, which may differ from this node's own chain_id).
    try:
        info = httpx.get(f"{rpc_url.rstrip('/')}/network-info", timeout=5).json()
        if info.get("node_id") not in (None, "unknown"):
            header_data["target_node_id"] = info["node_id"]
        if info.get("chain_id"):
            header_data["target_chain_id"] = info["chain_id"]
    except _OPS_ERRORS:  # noqa: BLE001,S110 - optional metadata probe: the unsigned payload still works
        pass
    # Admin signature over the request payload, excluding admin_signature itself
    admin_signature = _sign_dict(admin_private_key, header_data)
    header_data["admin_signature"] = admin_signature

    async def _store():
        client = _get_bridge_client(rpc_url)
        async with client:
            return await client.store_block_header(header_data)

    try:
        result = asyncio.run(_store())
        output(result, ctx.obj.get("output_format", "table"), title="Stored Block Header")
    except _OPS_ERRORS as e:
        _abort_ops(ctx, "Failed to store block header", e)


@bridge.command(
    name="ingest-header",
    epilog="""Examples:

  aitbc bridge ingest-header --source-rpc http://node2.example.net:8202/rpc --height 100 --chain-id ait-mainnet

  aitbc bridge ingest-header --source-rpc http://node2.example.net:8202/rpc --target-rpc http://hub.example.net:8202/rpc --height 100""",
)
@click.option("--source-rpc", default="http://localhost:8202/rpc", help="RPC URL of the source chain node")
@click.option(
    "--target-rpc", default="http://localhost:8202/rpc", help="RPC URL to store the header on (defaults to localhost)"
)
@click.option("--height", default=None, type=int, help="Block height to ingest (default: latest)")
@click.option("--chain-id", default=None, help="Source chain ID (default: source node's default)")
@click.option("--re-sign/--no-re-sign", default=False, help="Replace the source signature with a local validator signature")
@click.option("--private-key", default=None, help="Private key hex for re-signing (requires --re-sign)")
@click.option("--proposer", default=None, help="Proposer address for the new signature (defaults to address of --private-key)")
@click.option("--output", "-o", "output_path", default=None, type=click.Path(), help="Write the stored header to a JSON file")
@click.pass_context
def ingest_header(ctx, source_rpc, target_rpc, height, chain_id, re_sign, private_key, proposer, output_path):
    """Fetch a block header from a source node and store it as a bridge header."""

    if re_sign:
        if not private_key:
            abort(ctx, "--private-key is required when --re-sign is set")
        proposer = proposer or _derive_address(private_key)

    async def _ingest():
        header = await _fetch_block_header(source_rpc, height, chain_id)

        if re_sign:
            header["proposer"] = proposer
            header["signature"] = _sign_header(private_key, header)

        if output_path:
            Path(output_path).write_text(json.dumps(header, indent=2, sort_keys=True))

        client = _get_bridge_client(target_rpc)
        async with client:
            return await client.store_block_header(header)

    try:
        result = asyncio.run(_ingest())
        output(result, ctx.obj.get("output_format", "table"), title="Ingested Block Header")
    except _OPS_ERRORS as e:
        _abort_ops(ctx, "Failed to ingest block header", e)


@bridge.command(
    name="attest",
    epilog="""Examples:

  aitbc bridge attest --header-file /tmp/header.json --private-key 0x...

  aitbc bridge attest --source-rpc http://node2.example.net:8202/rpc --height 100 --private-key 0x...""",
)
@click.option("--header-file", type=click.Path(exists=True), help="JSON file with a block header to attest")
@click.option("--source-rpc", default=None, help="RPC URL to fetch the block from (alternative to --header-file)")
@click.option("--height", default=None, type=int, help="Block height to fetch from source")
@click.option("--chain-id", default=None, help="Chain ID for the block")
@click.option("--private-key", required=True, help="Validator private key hex to sign with")
@click.option("--proposer", default=None, help="Proposer/validator address (defaults to derived address)")
@click.option("--target-rpc", default="http://localhost:8202/rpc", help="RPC URL to store the attested header on")
@click.option(
    "--output", "-o", "output_path", default=None, type=click.Path(), help="Write the attested header to a JSON file"
)
@click.pass_context
def attest(ctx, header_file, source_rpc, height, chain_id, private_key, proposer, target_rpc, output_path):
    """Sign a block header as a bridge validator and store it as a bridge header."""
    proposer = proposer or _derive_address(private_key)

    async def _attest():
        if header_file:
            header = json.loads(Path(header_file).read_text())
        elif source_rpc:
            header = await _fetch_block_header(source_rpc, height, chain_id)
        else:
            abort(ctx, "Either --header-file or --source-rpc is required")

        # Canonicalize the fields we need for signing and storage
        header_fields = {
            "chain_id": header.get("chain_id"),
            "height": header.get("height"),
            "hash": header.get("hash"),
            "parent_hash": header.get("parent_hash") or "0x" + "00" * 32,
            "proposer": proposer,
            "state_root": header.get("state_root", ""),
            "bridge_state_root": header.get("bridge_state_root", ""),
        }
        for field in ("chain_id", "height", "hash"):
            if not header_fields[field]:
                abort(ctx, f"Header missing required field: {field}")

        header_fields["signature"] = _sign_header(private_key, header_fields)

        if output_path:
            Path(output_path).write_text(json.dumps(header_fields, indent=2, sort_keys=True))

        client = _get_bridge_client(target_rpc)
        async with client:
            return await client.store_block_header(header_fields)

    try:
        result = asyncio.run(_attest())
        output(result, ctx.obj.get("output_format", "table"), title="Attested Block Header")
    except _OPS_ERRORS as e:
        _abort_ops(ctx, "Failed to attest block header", e)
