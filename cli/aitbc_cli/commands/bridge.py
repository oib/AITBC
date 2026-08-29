"""Bridge commands for AITBC CLI.

v0.7.0 §B3: Replaced the broken ``start``/``status``/``stop`` commands (which
called non-existent ``/rpc/bridge/start`` etc. and fell back to simulated data)
with actual bridge RPC commands using ``aitbc.bridge.BridgeClient``.

v0.7.1 §B7: Added ``security-status`` and ``register-validator`` subcommands
for bridge multi-sig management.
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import click
import httpx

from aitbc.bridge import BridgeClient, BridgeConfig

from ..utils import output
from ..utils.error_handling import abort


def _canonical_hash(data: dict[str, Any]) -> bytes:
    """keccak256 of canonical JSON encoding (matches verify_request_signature)."""
    from eth_utils import keccak

    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return keccak(message)


def _sign_hash(private_key_hex: str, msg_hash: bytes) -> str:
    """Sign a keccak message hash with a private key, returning a hex signature."""
    from eth_keys import keys

    pk = keys.PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x")))
    sig = pk.sign_msg_hash(msg_hash)
    return sig.to_hex()


def _sign_dict(private_key_hex: str, data: dict[str, Any]) -> str:
    """Sign a canonical dict and return the hex signature."""
    return _sign_hash(private_key_hex, _canonical_hash(data))


def _derive_address(private_key_hex: str) -> str:
    """Derive the Ethereum address from a private key hex."""
    from eth_keys import keys

    pk = keys.PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x")))
    return str(pk.public_key.to_checksum_address())


def _sign_header(private_key_hex: str, header_fields: dict[str, Any]) -> str:
    """Sign a block header with the canonical verification message."""
    sign_fields = {
        "chain_id": header_fields["chain_id"],
        "height": header_fields["height"],
        "hash": header_fields["hash"],
        "parent_hash": header_fields.get("parent_hash") or "0x" + "00" * 32,
        "proposer": header_fields["proposer"],
        "state_root": header_fields["state_root"],
        "bridge_state_root": header_fields.get("bridge_state_root") or "",
    }
    return _sign_dict(private_key_hex, sign_fields)


async def _fetch_block_header(rpc_url: str, height: int | None, chain_id: str | None) -> dict[str, Any]:
    """Fetch a block header from the source RPC.

    If height is None, the current head height is resolved first.
    If chain_id is None, the source node's default chain is used.
    Returns only the header fields (no transactions).
    """
    async with httpx.AsyncClient(base_url=rpc_url, timeout=30.0) as client:
        if height is None:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            resp = await client.get("/height", params=params)
            resp.raise_for_status()
            height = resp.json().get("height", 0)

        params = {}
        if chain_id:
            params["chain_id"] = chain_id
        resp = await client.get(f"/blocks/{height}", params=params)
        resp.raise_for_status()
        block = resp.json()

    return {
        "chain_id": block["chain_id"],
        "height": block["height"],
        "hash": block["hash"],
        "parent_hash": block.get("parent_hash") or "0x" + "00" * 32,
        "proposer": block["proposer"],
        "state_root": block["state_root"],
        "bridge_state_root": block.get("bridge_state_root", ""),
        "signature": block.get("signature", ""),
    }


_EVENT_BRIDGE_URL = os.getenv("EVENT_BRIDGE_URL", "http://127.0.0.1:8205")
_SERVICE_NAME = "aitbc-blockchain-event-bridge"


def _event_bridge_status() -> dict[str, str]:
    """Read the event bridge service status over HTTP."""
    try:
        resp = httpx.get(f"{_EVENT_BRIDGE_URL}/", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        return {"status": data.get("status", "unknown"), "bridge_status": "active"}
    except Exception as e:
        return {"status": f"unreachable ({e})", "bridge_status": "inactive"}


def _systemctl(action: str) -> tuple[bool, str]:
    """Run systemctl action on the event bridge service."""
    try:
        result = subprocess.run(
            ["systemctl", action, _SERVICE_NAME],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except Exception as e:
        return False, str(e)


def _get_bridge_client(rpc_url: str) -> BridgeClient:
    """Create a BridgeClient pointing at the given blockchain RPC URL."""
    return BridgeClient(BridgeConfig(rpc_url=rpc_url))


@click.group(
    epilog="""Examples:

  aitbc bridge status

  aitbc bridge lock --target-chain ait-side --sender 0x... --recipient 0x... --amount 100"""
)
def bridge():
    """Manage cross-chain bridge transfers, validators, proofs, and block headers."""
    pass


def _get_wallet_dir() -> Path:
    """Resolve the wallet directory from env or default."""
    from pathlib import Path

    from ..utils.wallet_paths import wallet_dir as get_wallet_dir

    return Path(get_wallet_dir())


def _load_private_key(wallet_name: str, password: str = "") -> str:
    """Load a wallet's private key (plaintext or encrypted)."""
    wallet_path = _get_wallet_dir() / f"{wallet_name}.json"
    if not wallet_path.exists():
        raise click.ClickException(f"Wallet not found: {wallet_path}")
    with open(wallet_path) as f:
        wallet = json.load(f)
    private_key = wallet.get("private_key")
    if isinstance(private_key, dict):
        from ..utils.wallet import decrypt_private_key

        if not password:
            raise click.ClickException("Wallet is encrypted; --wallet-password is required")
        return decrypt_private_key(wallet_path, password)
    if not isinstance(private_key, str) or not private_key:
        raise click.ClickException("Wallet does not contain a usable private_key")
    return private_key


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
@click.option("--source-chain", default=None, help="Source chain ID (defaults to node's chain)")
@click.option("--signature", default="", help="Sender signature authorizing the lock (hex)")
@click.option("--wallet-name", default=None, help="Wallet to sign the lock with")
@click.option("--wallet-password", default="", help="Password if the wallet is encrypted")
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def lock(ctx, target_chain, sender, recipient, amount, asset, source_chain, signature, wallet_name, wallet_password, rpc_url):
    """Lock funds for a cross-chain bridge transfer."""

    if wallet_name:
        private_key = _load_private_key(wallet_name, wallet_password)
        sign_data = {
            "source_chain": source_chain or "",
            "target_chain": target_chain,
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "asset": asset,
        }
        signature = _sign_dict(private_key, sign_data)

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
    except Exception as e:
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
    except Exception as e:
        abort(ctx, f"Bridge confirm failed: {e}", from_exception=e)


@bridge.command(
    epilog="""Examples:

  aitbc bridge unlock --transfer-id tx-123 --sender 0xAbc... --signature 0x...

  aitbc bridge unlock --transfer-id tx-123 --sender 0xAbc... --signature 0x... --rpc-url http://aitbc3:8202/rpc"""
)
@click.option("--transfer-id", required=True, help="Transfer ID to refund")
@click.option("--sender", required=True, help="Original sender address")
@click.option("--signature", required=True, help="Sender signature authorizing the unlock")
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def unlock(ctx, transfer_id, sender, signature, rpc_url):
    """Refund or cancel a pending bridge transfer."""

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
    except Exception as e:
        abort(ctx, f"Failed to get bridge status: {e}", from_exception=e)


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
    except Exception as e:
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
    except Exception as e:
        abort(ctx, f"Failed to get bridge balance: {e}", from_exception=e)


@bridge.command(
    epilog="""Examples:

  aitbc bridge health

  aitbc bridge health --rpc-url http://aitbc3:8202/rpc"""
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
    except Exception as e:
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
    except Exception as e:
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
                **{"admin_address": payload.get("admin_address"), "admin_signature": payload.get("admin_signature")},
            )

    try:
        result = asyncio.run(_register())
        output(result, ctx.obj.get("output_format", "table"), title="Validator Registration")
    except Exception as e:
        abort(ctx, f"Validator registration failed: {e}", from_exception=e)


@bridge.command(
    name="oracle-status",
    epilog="""Examples:

  aitbc bridge oracle-status

  aitbc bridge oracle-status --rpc-url http://aitbc3:8202/rpc""",
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
    except Exception as e:
        abort(ctx, f"Failed to get bridge oracle status: {e}", from_exception=e)


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
@click.option("--output", "-o", required=True, type=click.Path(), help="JSON file to write the unsigned proof to")
@click.option("--rpc-url", default="http://localhost:8202/rpc", help="Blockchain RPC URL")
@click.pass_context
def get_proof(ctx, transfer_id, source_chain, block_height, block_hash, output, rpc_url):
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
        Path(output).write_text(json.dumps(proof, indent=2, sort_keys=True))
        output(
            {"success": True, "transfer_id": transfer_id, "proof_file": output},
            ctx.obj.get("output_format", "table"),
            title="Bridge Proof",
        )
    except Exception as e:
        abort(ctx, f"Failed to build bridge proof: {e}", from_exception=e)


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
@click.option("--output", "-o", default=None, type=click.Path(), help="Output file (defaults to proof-file)")
@click.pass_context
def sign_proof(ctx, proof_file, private_key, output):
    """Sign a bridge proof with one or more validator private keys."""
    try:
        proof = json.loads(Path(proof_file).read_text())
    except Exception as e:
        abort(ctx, f"Failed to read proof file: {e}", from_exception=e)

    if not private_key:
        abort(ctx, "At least one --private-key is required")

    # Build the canonical message from the proof (excluding any signature fields)
    sign_fields = {k: v for k, v in proof.items() if k not in ("proposer_signature", "validator_signatures")}

    signatures: list[str] = []
    for pk in private_key:
        signatures.append(_sign_dict(pk, sign_fields))

    proof["proposer_signature"] = signatures[0]
    proof["validator_signatures"] = signatures

    out_file = output or proof_file
    try:
        Path(out_file).write_text(json.dumps(proof, indent=2, sort_keys=True))
    except Exception as e:
        abort(ctx, f"Failed to write signed proof: {e}", from_exception=e)

    output(
        {"success": True, "proof_file": out_file, "signatures": len(signatures)},
        ctx.obj.get("output_format", "table"),
        title="Signed Bridge Proof",
    )


@bridge.command(
    name="store-header",
    epilog="""Examples:

  aitbc bridge store-header --proof-file /tmp/signed-proof.json --admin-private-key 0x...

  aitbc bridge store-header --proof-file /tmp/signed-proof.json --admin-private-key 0x... --rpc-url http://aitbc3:8202/rpc""",
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
    except Exception as e:
        abort(ctx, f"Failed to read proof file: {e}", from_exception=e)

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
    }
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
    except Exception as e:
        abort(ctx, f"Failed to store block header: {e}", from_exception=e)


@bridge.command(
    name="ingest-header",
    epilog="""Examples:

  aitbc bridge ingest-header --source-rpc http://aitbc3:8202/rpc --height 100 --chain-id ait-mainnet

  aitbc bridge ingest-header --source-rpc http://aitbc3:8202/rpc --target-rpc http://hub.aitbc:8202/rpc --height 100""",
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
@click.option("--output", "-o", default=None, type=click.Path(), help="Write the stored header to a JSON file")
@click.pass_context
def ingest_header(ctx, source_rpc, target_rpc, height, chain_id, re_sign, private_key, proposer, output):
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

        if output:
            Path(output).write_text(json.dumps(header, indent=2, sort_keys=True))

        client = _get_bridge_client(target_rpc)
        async with client:
            return await client.store_block_header(header)

    try:
        result = asyncio.run(_ingest())
        output(result, ctx.obj.get("output_format", "table"), title="Ingested Block Header")
    except Exception as e:
        abort(ctx, f"Failed to ingest block header: {e}", from_exception=e)


@bridge.command(
    name="attest",
    epilog="""Examples:

  aitbc bridge attest --header-file /tmp/header.json --private-key 0x...

  aitbc bridge attest --source-rpc http://aitbc3:8202/rpc --height 100 --private-key 0x...""",
)
@click.option("--header-file", type=click.Path(exists=True), help="JSON file with a block header to attest")
@click.option("--source-rpc", default=None, help="RPC URL to fetch the block from (alternative to --header-file)")
@click.option("--height", default=None, type=int, help="Block height to fetch from source")
@click.option("--chain-id", default=None, help="Chain ID for the block")
@click.option("--private-key", required=True, help="Validator private key hex to sign with")
@click.option("--proposer", default=None, help="Proposer/validator address (defaults to derived address)")
@click.option("--target-rpc", default="http://localhost:8202/rpc", help="RPC URL to store the attested header on")
@click.option("--output", "-o", default=None, type=click.Path(), help="Write the attested header to a JSON file")
@click.pass_context
def attest(ctx, header_file, source_rpc, height, chain_id, private_key, proposer, target_rpc, output):
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

        if output:
            Path(output).write_text(json.dumps(header_fields, indent=2, sort_keys=True))

        client = _get_bridge_client(target_rpc)
        async with client:
            return await client.store_block_header(header_fields)

    try:
        result = asyncio.run(_attest())
        output(result, ctx.obj.get("output_format", "table"), title="Attested Block Header")
    except Exception as e:
        abort(ctx, f"Failed to attest block header: {e}", from_exception=e)
