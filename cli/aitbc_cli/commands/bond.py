"""Performance bond commands for providers and agents."""

from __future__ import annotations

import os
from typing import Any

import click
import httpx

from aitbc.exceptions import AITBCError
from ..config import get_config
from ..utils import DECIMAL, output, resolve_output_format
from ..auth import AuthManager, ExpiredAdminToken
from ..utils.error_handling import CLIError, abort
from ..utils.http_client import AITBCHTTPClient, NetworkError
from ..utils.wallet_secret import resolve_wallet_password, wallet_password_options

from .auth import _resolve_private_key

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


def _looks_like_jwt(token: str) -> bool:
    """A JWT is three base64url segments separated by dots."""
    return token.startswith("ey") and token.count(".") == 2


def _coordinator_base_url(ctx, coordinator_url: str | None = None) -> str:
    """Return the coordinator base URL without a trailing /v1 path."""
    config = get_config()
    url = coordinator_url or ctx.obj.get("url") or config.coordinator_api_url or os.getenv("COORDINATOR_API_URL", "")
    if not url:
        return ""
    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def _api_client(ctx, coordinator_url: str | None = None, timeout: int | None = None) -> AITBCHTTPClient:
    """Return an HTTP client for the coordinator API."""
    config = get_config()
    url = _coordinator_base_url(ctx, coordinator_url)
    if not url:
        abort(ctx, "Coordinator URL not configured")

    try:
        stored = AuthManager().get_admin_token() or ""
    except ExpiredAdminToken as e:
        abort(ctx, str(e))
    # Bond routes authenticate via require_auth — a Bearer JWT is the only
    # accepted credential, so a non-JWT key (miner key resolved from env, or a
    # non-JWT stored credential) can never pass and always 401s. Prefer the
    # first candidate that actually is a JWT; otherwise keep the existing
    # precedence (flag > ambient > stored).
    candidates = [ctx.obj.get("api_key") or "", config.api_key or "", stored]
    token = next((t for t in candidates if _looks_like_jwt(t)), "") or next((t for t in candidates if t), "")

    headers: dict[str, str] | None = None
    client_kwargs: dict[str, Any] = {"base_url": url, "timeout": timeout or config.timeout or 30, "headers": headers}
    if token and _looks_like_jwt(token):
        client_kwargs["headers"] = {"Authorization": f"Bearer {token}"}
    elif token:
        client_kwargs["api_key"] = token

    return AITBCHTTPClient(**client_kwargs)


def _bond_proof_fields(
    ctx,
    client: AITBCHTTPClient,
    provider_id: str,
    wallet_name: str | None,
    private_key: str | None,
    private_key_file: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
) -> dict[str, str]:
    """Fetch a bond-wallet challenge and sign it (#1967).

    Returns ``{}`` when no key source was given — the request then goes out
    unsigned and the coordinator decides (admin JWTs pass; provider callers
    get 403 with instructions). When a key source *is* given, the challenge
    nonce + EIP-191 signature are attached to the create/top-up body.
    """
    if not (wallet_name or private_key or private_key_file):
        return {}
    if wallet_name and not private_key and not private_key_file:
        password = resolve_wallet_password(
            wallet_name,
            password=password,
            password_file=password_file,
            password_stdin=password_stdin,
            legacy_env_names=("WALLET_PASSWORD",),
            interactive_ok=False,
            allow_unencrypted=True,
            ctx=ctx,
        )
    try:
        raw_key = _resolve_private_key(wallet_name, private_key, private_key_file, password)
    except ValueError as e:
        abort(ctx, str(e), from_exception=e)
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct

        account = Account.from_key(raw_key)
    except Exception as e:  # noqa: BLE001 — eth-account raises several key-error types
        abort(ctx, f"Invalid private key: {e}", from_exception=e)

    challenge = client.post(f"/v1/market/providers/{provider_id}/bonds/challenge")
    nonce = challenge.get("nonce")
    message = challenge.get("message")
    if not nonce or not message:
        abort(ctx, f"Coordinator did not return a bond challenge: {challenge}")
    signed = account.sign_message(encode_defunct(text=message))
    return {"challenge_nonce": nonce, "wallet_signature": "0x" + signed.signature.hex()}


@click.group(
    epilog="""Examples:

  aitbc bond create --provider-id provider-1 --amount 100

  aitbc bond status --provider-id provider-1"""
)
def bond():
    """Manage provider performance bonds through their lifecycle: create, top-up, lock, release, slash, and appeal."""
    pass


@bond.command(
    epilog="""Examples:

  aitbc bond create --provider-id provider-1 --amount 100

  aitbc bond create --provider-id provider-1 --amount 100 --required-amount 200"""
)
@click.option("--provider-id", "provider_id", required=True, help="Provider ID.")
@click.option("--amount", default="0.0", help="Ignored — the server verifies the on-chain BOND_LOCK amount")
@click.option("--required-amount", default="0.0", help="Required bond amount for this provider")
@click.option("--bond-id", default=None, help="Optional on-chain/external bond identifier")
@click.option(
    "--wallet", "wallet_name", default=None, help="Wallet that owns the provider bond (signs the #1967 ownership challenge)"
)
@wallet_password_options
@click.option("--private-key", help="Raw hex private key for the bond wallet (CI/scripts)")
@click.option("--private-key-file", type=click.Path(), help="File containing the bond wallet's raw hex private key")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def create(
    ctx,
    provider_id,
    amount,
    required_amount,
    bond_id,
    wallet_name,
    password,
    password_file,
    password_stdin,
    private_key,
    private_key_file,
    coordinator_url,
    format,
):
    """Register a provider's on-chain performance bond with the coordinator.

    The coordinator row is a projection of the verified on-chain BOND_LOCK;
    ``--amount``/``--required-amount`` in the body are ignored — the chain
    amount wins (#1915, #2359). To add bond funds, lock a new BOND_LOCK
    on-chain (``aitbc bond lock-onchain``) and register its ``--bond-id``.

    Non-admin callers must prove control of the provider's registered
    wallet: pass --wallet/--private-key/--private-key-file and the CLI
    fetches a challenge and signs it automatically (#1967). Without a key
    source the request goes unsigned — admin JWTs still pass, provider
    callers get 403.
    """
    try:
        client = _api_client(ctx, coordinator_url)
        payload: dict[str, Any] = {
            "amount": amount,
            "required_amount": required_amount,
        }
        if bond_id:
            payload["bond_id"] = bond_id
        payload.update(
            _bond_proof_fields(
                ctx,
                client,
                provider_id,
                wallet_name,
                private_key,
                private_key_file,
                password,
                password_file,
                password_stdin,
            )
        )
        result = client.post(f"/v1/market/providers/{provider_id}/bonds", json=payload)
        output(result, resolve_output_format(ctx, format), title="Bond Created")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error creating bond for {provider_id}: {e}", from_exception=e)


@bond.command(
    epilog="""Examples:

  aitbc bond challenge --provider-id provider-1"""
)
@click.option("--provider-id", "provider_id", required=True, help="Provider ID.")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def challenge(ctx, provider_id, coordinator_url, format):
    """Fetch the wallet-ownership challenge for a provider bond (#1967).

    Prints the nonce and canonical message to sign with the provider's
    registered wallet; pass the resulting signature via --wallet on
    ``bond create``/``bond top-up`` (or sign manually and post
    challenge_nonce/wallet_signature to the API).
    """
    try:
        client = _api_client(ctx, coordinator_url)
        result = client.post(f"/v1/market/providers/{provider_id}/bonds/challenge")
        output(result, resolve_output_format(ctx, format), title="Bond Wallet Challenge")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:  # noqa: BLE001 — mirrors sibling bond commands
        abort(ctx, f"Error fetching bond challenge for {provider_id}: {e}", from_exception=e)


@bond.command(
    epilog="""Examples:

  aitbc bond status --provider-id provider-1

  aitbc bond status --provider-id provider-1 --output json"""
)
@click.option("--provider-id", "provider_id", required=True, help="Provider ID.")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def status(ctx, provider_id, coordinator_url, format):
    """Show a provider's bond eligibility status."""
    try:
        client = _api_client(ctx, coordinator_url)
        result = client.get(f"/v1/market/providers/{provider_id}/eligibility")
        output(result, resolve_output_format(ctx, format), title="Bond Status")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error fetching bond status for {provider_id}: {e}", from_exception=e)


@bond.command(
    epilog="""Examples:

  aitbc bond top-up --provider-id provider-1 --amount 50

  aitbc bond top-up --provider-id provider-1 --amount 50 --bond-id bond-123"""
)
@click.option("--provider-id", "provider_id", required=True, help="Provider ID.")
@click.option(
    "--amount", default="0.0", help="Ignored — bonds mirror on-chain state; the server verifies the BOND_LOCK amount"
)
@click.option("--bond-id", default=None, help="Optional on-chain/external bond identifier")
@click.option(
    "--wallet", "wallet_name", default=None, help="Wallet that owns the provider bond (signs the #1967 ownership challenge)"
)
@wallet_password_options
@click.option("--private-key", help="Raw hex private key for the bond wallet (CI/scripts)")
@click.option("--private-key-file", type=click.Path(), help="File containing the bond wallet's raw hex private key")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def top_up(
    ctx,
    provider_id,
    amount,
    bond_id,
    wallet_name,
    password,
    password_file,
    password_stdin,
    private_key,
    private_key_file,
    coordinator_url,
    format,
):
    """Re-verify/rebind a provider's on-chain performance bond.

    This does **not** add funds: the coordinator row is a projection of the
    verified on-chain BOND_LOCK, and the ``--amount`` payload is ignored —
    the chain amount wins. To genuinely add bond funds, lock a new
    BOND_LOCK on-chain (``aitbc bond lock-onchain``) and register its
    ``--bond-id`` here.

    Same wallet-ownership proof as ``create`` (#1967): pass a key source to
    sign the challenge automatically, or rely on an admin JWT.
    """
    try:
        client = _api_client(ctx, coordinator_url)
        payload: dict[str, Any] = {"amount": amount}
        if bond_id:
            payload["bond_id"] = bond_id
        payload.update(
            _bond_proof_fields(
                ctx,
                client,
                provider_id,
                wallet_name,
                private_key,
                private_key_file,
                password,
                password_file,
                password_stdin,
            )
        )
        result = client.post(f"/v1/market/providers/{provider_id}/bonds", json=payload)
        output(result, resolve_output_format(ctx, format), title="Bond Top-Up")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error topping up bond for {provider_id}: {e}", from_exception=e)


@bond.command(
    epilog="""Examples:

  aitbc bond lock --provider-id provider-1

  aitbc bond lock --provider-id provider-1 --output json"""
)
@click.option("--provider-id", "provider_id", required=True, help="Provider ID.")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def lock(ctx, provider_id, coordinator_url, format):
    """Lock a provider's bond while a high-value job is in flight."""
    try:
        client = _api_client(ctx, coordinator_url)
        result = client.post(f"/v1/market/providers/{provider_id}/bonds/lock")
        output(result, resolve_output_format(ctx, format), title="Bond Locked")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error locking bond for {provider_id}: {e}", from_exception=e)


@bond.command(
    epilog="""Examples:

  aitbc bond lock-onchain --bond-id bond-1 --escrow-address 0xEscrow... --amount 10 --wallet provider-1

  aitbc bond lock-onchain --bond-id bond-1 --escrow-address 0xEscrow... --amount 10 --wallet provider-1 --lock-days 90"""
)
@click.option("--bond-id", "bond_id", required=True, help="Bond identifier recorded in the BOND_LOCK payload")
@click.option(
    "--escrow-address",
    "escrow_address",
    required=True,
    help="Node BOND_ESCROW_ADDRESS — chain env config, not exposed via RPC",
)
@click.option("--amount", required=True, type=DECIMAL, help="AIT amount to lock into the bond escrow")
@click.option("--lock-days", type=int, default=30, show_default=True, help="Lock duration in days (1-3650)")
@click.option("--wallet", "wallet_name", required=True, help="Provider wallet — payload.provider must equal the signer")
@wallet_password_options
@click.option("--rpc-url", default=None, help="Blockchain RPC URL (default: resolved like transactions send)")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def lock_onchain(
    ctx, bond_id, escrow_address, amount, lock_days, wallet_name, password, password_file, password_stdin, rpc_url, format
):
    """Submit the on-chain BOND_LOCK escrow transaction for a provider bond.

    ``bond create``/``top-up`` record the bond coordinator-side but require a
    prior chain-verified ``BOND_LOCK``; this command is that missing leg. The
    tx pays ``--escrow-address`` (the node's ``BOND_ESCROW_ADDRESS``) with
    payload ``{bond_id, provider, lock_days}`` where ``provider`` is the
    signing wallet's own address — the chain refuses any other signer.
    """
    import json

    from aitbc.utils.units import DEFAULT_TX_FEE_AIT
    from ..utils.wallet_paths import find_wallet_file
    from .transactions import _send_transaction_impl

    wallet_file = find_wallet_file(wallet_name)
    if wallet_file is None:
        abort(ctx, f"Wallet '{wallet_name}' not found — pass a file wallet that exists on this host")
        raise click.Abort()  # unreachable — abort() raises; narrows Path | None for mypy
    try:
        provider_address = json.loads(wallet_file.read_text()).get("address")
    except (OSError, ValueError) as e:
        abort(ctx, f"Could not read wallet '{wallet_name}': {e}", from_exception=e)
    if not provider_address:
        abort(ctx, f"Wallet '{wallet_name}' has no 'address' field")

    resolved_password = resolve_wallet_password(
        wallet_name,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
        ctx=ctx,
    )
    payload = {"bond_id": bond_id, "provider": provider_address, "lock_days": lock_days}
    tx_hash = _send_transaction_impl(
        wallet_name,
        escrow_address,
        amount,
        DEFAULT_TX_FEE_AIT,
        resolved_password,
        rpc_url=rpc_url,
        tx_type="BOND_LOCK",
        payload=payload,
    )
    if not tx_hash:
        abort(ctx, "BOND_LOCK submission failed — see the error above")
    output(
        {"tx_hash": tx_hash, "bond_id": bond_id, "provider": provider_address, "amount": str(amount)},
        resolve_output_format(ctx, format),
        title="BOND_LOCK submitted",
    )


@bond.command(
    epilog="""Examples:

  aitbc bond release --provider-id provider-1

  aitbc bond release --provider-id provider-1 --output json"""
)
@click.option("--provider-id", "provider_id", required=True, help="Provider ID.")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def release(ctx, provider_id, coordinator_url, format):
    """Release a previously locked provider bond.

    The coordinator's release endpoint un-locks a LOCKED bond back to ACTIVE:
    the bond record and its amount stay posted — release is not a withdrawal,
    and there is no endpoint that frees the bonded funds. ``status: "active"``
    in the response therefore *is* the released state, not a failure.
    """
    try:
        client = _api_client(ctx, coordinator_url)
        result = client.post(f"/v1/market/providers/{provider_id}/bonds/release")
        if isinstance(result, dict):
            result.setdefault(
                "note",
                "Bond lock released; the bond stays posted (status 'active'). "
                "Release un-locks a locked bond — it does not withdraw the bonded amount.",
            )
        output(result, resolve_output_format(ctx, format), title="Bond Released")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error releasing bond for {provider_id}: {e}", from_exception=e)


@bond.command(
    epilog="""Examples:

  aitbc bond slash --provider-id provider-1 --reason 'missed deadline'

  aitbc bond slash --provider-id provider-1"""
)
@click.option("--provider-id", "provider_id", required=True, help="Provider ID.")
@click.option("--reason", default="", help="Reason for the slash")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def slash(ctx, provider_id, reason, coordinator_url, format):
    """Slash a provider's bond with an optional reason."""
    try:
        client = _api_client(ctx, coordinator_url)
        payload = {"reason": reason} if reason else {}
        result = client.post(f"/v1/market/providers/{provider_id}/bonds/slash", json=payload)
        output(result, resolve_output_format(ctx, format), title="Bond Slashed")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error slashing bond for {provider_id}: {e}", from_exception=e)


@bond.command(
    epilog="""Examples:

  aitbc bond appeal --bond-id bond-123 --reason 'false positive'

  aitbc bond appeal --bond-id bond-123 --reason 'false positive' --evidence ipfs://Qm..."""
)
@click.option("--bond-id", "bond_id", required=True, help="Bond ID.")
@click.option("--reason", default="", help="Reason for the appeal")
@click.option("--evidence", default="", help="Evidence URL or CID")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def appeal(ctx, bond_id, reason, evidence, coordinator_url, format):
    """Appeal a slashing decision for a bond with optional evidence."""
    try:
        client = _api_client(ctx, coordinator_url)
        result = client.post(
            "/v1/governance/slash-appeals",
            json={"bond_id": bond_id, "reason": reason, "evidence": [evidence] if evidence else []},
        )
        output(result, resolve_output_format(ctx, format), title="Slash Appeal")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error submitting slash appeal for {bond_id}: {e}", from_exception=e)
