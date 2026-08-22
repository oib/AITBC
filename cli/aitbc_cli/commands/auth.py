"""Authentication commands for AITBC CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click
from eth_account import Account
from eth_account.messages import encode_defunct

from ..auth import AuthManager
from ..config import get_config
from ..utils import error, output, success, warning
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError
from ..utils.wallet import decrypt_private_key


@click.group()
def auth():
    """Authentication and session management."""
    pass


def _build_sign_message(wallet_address: str, nonce: str) -> str:
    """Canonical message the coordinator expects for /v1/login."""
    return f"Sign this message to log in to AITBC.\nWallet: {wallet_address.lower()}\nNonce: {nonce}"


def _resolve_private_key(
    wallet_name: str | None,
    private_key: str | None,
    private_key_file: str | None,
    password: str | None,
) -> str:
    """Return a raw hex private key from the supplied source."""
    if private_key:
        return private_key.removeprefix("0x").strip()
    if private_key_file:
        path = Path(private_key_file)
        if not path.exists():
            raise ValueError(f"Private key file not found: {private_key_file}")
        raw = path.read_text().strip()
        return raw.removeprefix("0x").strip()
    if wallet_name:
        # Service wallets do not always live under the invoking user's home: on a hub
        # node they sit in /var/lib/aitbc/wallets. Allow AITBC_WALLET_DIR to point at
        # them, keeping ~/.aitbc/wallets as the default.
        wallet_dir = Path(os.getenv("AITBC_WALLET_DIR") or (Path.home() / ".aitbc" / "wallets"))
        wallet_path = wallet_dir / f"{wallet_name}.json"
        if not wallet_path.exists():
            raise ValueError(f"Wallet not found: {wallet_path}")
        wallet_data = json.loads(wallet_path.read_text())
        private_key_field = wallet_data.get("private_key")
        if isinstance(private_key_field, str):
            return private_key_field.removeprefix("0x").strip()
        if not password:
            raise ValueError("Password required to decrypt wallet")
        return decrypt_private_key(wallet_path, password)
    raise ValueError("Provide --wallet, --private-key, or --private-key-file")


@auth.command()
@click.option("--wallet", help="Wallet name in AITBC_WALLET_DIR or ~/.aitbc/wallets/")
@click.option("--password", help="Wallet password (or WALLET_PASSWORD env var)")
@click.option("--private-key", help="Raw hex private key (use only in CI/scripts)")
@click.option("--private-key-file", type=click.Path(), help="File containing a raw hex private key")
@click.option("--wallet-address", help="Wallet address (defaults to address derived from private key)")
@click.option("--coordinator-url", help="Coordinator API URL")
@click.option("--environment", default="default", help="Credential environment name")
@click.pass_context
def login(
    ctx,
    wallet: str | None,
    password: str | None,
    private_key: str | None,
    private_key_file: str | None,
    wallet_address: str | None,
    coordinator_url: str | None,
    environment: str,
):
    """Log in with a wallet-signed nonce and store a coordinator JWT."""
    config = get_config()
    coord_url = coordinator_url or config.coordinator_api_url
    if not coord_url:
        abort(ctx, "Coordinator URL not configured")

    # The configured URL may already contain the /v1 prefix that the
    # coordinator application mounts.  Strip it so the login endpoints below
    # use the canonical /v1/... paths without doubling.
    coord_url = coord_url.rstrip("/")
    if coord_url.endswith("/v1"):
        coord_url = coord_url[:-3]

    # Password priority: CLI arg > env var
    password = password or os.environ.get("WALLET_PASSWORD")

    try:
        raw_key = _resolve_private_key(wallet, private_key, private_key_file, password)
    except ValueError as e:
        abort(ctx, str(e), from_exception=e)
        return

    try:
        account = Account.from_key(raw_key)
    except Exception as e:
        abort(ctx, f"Invalid private key: {e}", from_exception=e)
        return

    if wallet_address:
        address = wallet_address.lower().strip()
    else:
        address = account.address.lower()

    client = AITBCHTTPClient(base_url=coord_url, timeout=10)
    try:
        nonce_resp = client.post("/v1/auth/nonce", json={"wallet_address": address})
        nonce = nonce_resp.get("nonce")
        if not nonce:
            abort(ctx, f"Coordinator did not return a nonce: {nonce_resp}")
            return
    except NetworkError as e:
        abort(ctx, f"Cannot reach coordinator auth endpoint: {e}", from_exception=e)
        return

    message = _build_sign_message(address, nonce)
    signable = encode_defunct(text=message)
    try:
        signed = account.sign_message(signable)
    except Exception as e:
        abort(ctx, f"Failed to sign login message: {e}", from_exception=e)
        return

    signature = "0x" + signed.signature.hex()

    try:
        login_resp = client.post(
            "/v1/login",
            json={"wallet_address": address, "nonce": nonce, "signature": signature},
        )
    except NetworkError as e:
        abort(ctx, f"Login request failed: {e}", from_exception=e)
        return

    token = login_resp.get("session_token")
    if not token:
        detail = login_resp.get("detail") or login_resp
        abort(ctx, f"Login failed: {detail}")
        return

    manager = AuthManager()
    if manager.store_credential("client", token, environment=environment):
        success(f"Logged in as {address}")
        masked = token[:8] + "..." + token[-4:] if len(token) > 12 else "******"
        output(
            {
                "wallet": address,
                "token": masked,
                "backend": manager.backend_name,
                "environment": environment,
            },
            ctx.obj.get("output_format", "table"),
        )
    else:
        error("Login succeeded but token could not be stored")


@auth.command()
@click.option("--environment", default="default", help="Credential environment name")
@click.pass_context
def status(ctx, environment: str):
    """Show stored authentication credentials (values are masked)."""
    manager = AuthManager()
    creds = manager.list_credentials(environment=environment)
    if not creds:
        warning(f"No stored credentials for environment '{environment}'")
        return
    output(creds, ctx.obj.get("output_format", "table"), title="Stored Credentials")


@auth.command()
@click.option("--environment", default="default", help="Credential environment name")
@click.pass_context
def logout(ctx, environment: str):
    """Delete the stored coordinator credential."""
    manager = AuthManager()
    if manager.delete_credential("client", environment=environment):
        success(f"Logged out of environment '{environment}'")
    else:
        warning(f"No stored credential for 'client' in environment '{environment}'")
