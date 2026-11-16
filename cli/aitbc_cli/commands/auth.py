"""Authentication commands for AITBC CLI."""

from __future__ import annotations

import json
from pathlib import Path

import click
import httpx

from aitbc.exceptions import AITBCError
from ..auth import AuthManager
from ..config import get_config
from ..utils import info, output, success, warning
from ..utils.error_handling import CLIError, abort
from ..utils.wallet_secret import resolve_wallet_password, wallet_password_options
from ..utils.http_client import AITBCHTTPClient, NetworkError
from ..utils.wallet import decrypt_private_key
from ..utils.wallet_paths import find_wallet_file, is_service_wallet_path

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

  aitbc auth login --wallet genesis

  aitbc auth status"""
)
def auth():
    """Log in, log out, and view stored AITBC coordinator session credentials."""
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
        # Search configured and service wallet directories (including /var/lib/aitbc/wallets).
        wallet_path = find_wallet_file(wallet_name)
        if wallet_path is None:
            raise ValueError(f"Wallet not found: {wallet_name}")
        if is_service_wallet_path(wallet_path):
            info(f"Using wallet file: {wallet_path}")
        wallet_data = json.loads(wallet_path.read_text())
        private_key_field = wallet_data.get("private_key")
        if isinstance(private_key_field, str):
            return private_key_field.removeprefix("0x").strip()
        if not password:
            raise ValueError("Password required to decrypt wallet")
        return decrypt_private_key(wallet_path, password)
    raise ValueError("Provide --wallet, --private-key, or --private-key-file")


@auth.command(
    epilog="""Examples:

  aitbc auth login --wallet genesis

  aitbc auth login --wallet genesis --coordinator-url http://hub.example.net:8201"""
)
@click.option("--wallet", default="default", show_default=True, help="Wallet name in AITBC_WALLET_DIR or ~/.aitbc/wallets/")
@wallet_password_options
@click.option("--private-key", help="Raw hex private key (use only in CI/scripts)")
@click.option("--private-key-file", type=click.Path(), help="File containing a raw hex private key")
@click.option("--wallet-address", help="Wallet address (defaults to address derived from private key)")
@click.option("--coordinator-url", help="Coordinator API URL")
@click.option("--environment", default="default", help="Credential environment name")
@click.option(
    "--credential-name",
    default="client",
    help="Name the credential is stored under (e.g. 'admin' for aitbc monitor sweepers)",
)
@click.pass_context
def login(
    ctx,
    wallet: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    private_key: str | None,
    private_key_file: str | None,
    wallet_address: str | None,
    coordinator_url: str | None,
    environment: str,
    credential_name: str,
):
    """Log in with a wallet-signed nonce and store a coordinator JWT."""
    config = get_config()
    coord_url = _login_coord_url(ctx, coordinator_url, config)

    # A password is only needed when the key comes from an encrypted wallet
    # file — --private-key/--private-key-file paths must not require one.
    if wallet and not private_key and not private_key_file:
        password = resolve_wallet_password(
            wallet,
            password=password,
            password_file=password_file,
            password_stdin=password_stdin,
            legacy_env_names=("WALLET_PASSWORD",),
            interactive_ok=False,
            allow_unencrypted=True,
            ctx=ctx,
        )

    try:
        raw_key = _resolve_private_key(wallet, private_key, private_key_file, password)
    except ValueError as e:
        abort(ctx, str(e), from_exception=e)
        return

    account = _account_from_key(ctx, raw_key)
    address = wallet_address.lower().strip() if wallet_address else account.address.lower()

    client = AITBCHTTPClient(base_url=coord_url, timeout=10)
    nonce = _fetch_login_nonce(ctx, client, address)
    signature = _sign_login_message(ctx, account, address, nonce)
    token = _post_login(ctx, client, address, nonce, signature)
    _store_login_token(ctx, token, address, environment, credential_name)


def _login_coord_url(ctx, coordinator_url: str | None, config) -> str:
    coord_url = coordinator_url or config.coordinator_api_url
    if not coord_url:
        abort(ctx, "Coordinator URL not configured")

    # The configured URL may already contain the /v1 prefix that the
    # coordinator application mounts.  Strip it so the login endpoints below
    # use the canonical /v1/... paths without doubling.
    coord_url = coord_url.rstrip("/")
    if coord_url.endswith("/v1"):
        coord_url = coord_url[:-3]
    return coord_url


def _account_from_key(ctx, raw_key: str):
    try:
        # Function-local: the CLI's auth path is exercised only on login;
        # eth_account no longer taxes every `aitbc` invocation.
        from eth_account import Account

        return Account.from_key(raw_key)
    except _OPS_ERRORS as e:
        abort(ctx, f"Invalid private key: {e}", from_exception=e)
        return None


def _fetch_login_nonce(ctx, client: AITBCHTTPClient, address: str) -> str:
    try:
        nonce_resp = client.post("/v1/auth/nonce", json={"wallet_address": address})
        nonce: str | None = nonce_resp.get("nonce")
        if not nonce:
            abort(ctx, f"Coordinator did not return a nonce: {nonce_resp}")
            raise AssertionError("unreachable: abort always raises")
        return nonce
    except NetworkError as e:
        abort(ctx, f"Cannot reach coordinator auth endpoint: {e}", from_exception=e)
        raise AssertionError("unreachable: abort always raises") from e


def _sign_login_message(ctx, account, address: str, nonce: str) -> str:
    message = _build_sign_message(address, nonce)
    from eth_account.messages import encode_defunct

    signable = encode_defunct(text=message)
    try:
        signed = account.sign_message(signable)
    except _OPS_ERRORS as e:
        abort(ctx, f"Failed to sign login message: {e}", from_exception=e)
        raise AssertionError("unreachable: abort always raises") from e
    signature_hex: str = signed.signature.hex()
    return "0x" + signature_hex


def _post_login(ctx, client: AITBCHTTPClient, address: str, nonce: str, signature: str) -> str:
    try:
        login_resp = client.post(
            "/v1/login",
            json={"wallet_address": address, "nonce": nonce, "signature": signature},
        )
    except NetworkError as e:
        abort(ctx, f"Login request failed: {e}", from_exception=e)
        raise AssertionError("unreachable: abort always raises") from e

    token: str | None = login_resp.get("session_token")
    if not token:
        detail = login_resp.get("detail") or login_resp
        abort(ctx, f"Login failed: {detail}")
        raise AssertionError("unreachable: abort always raises")
    return token


def _store_login_token(ctx, token: str, address: str, environment: str, credential_name: str) -> None:
    manager = AuthManager()
    if manager.store_credential(credential_name, token, environment=environment):
        success(f"Logged in as {address}")
        masked = token[:8] + "..." + token[-4:] if len(token) > 12 else "******"
        output(
            {
                "wallet": address,
                "token": masked,
                "backend": manager.backend_name,
                "environment": environment,
                "credential": credential_name,
            },
            ctx.obj.get("output_format", "table"),
        )
    else:
        abort(None, "Login succeeded but token could not be stored")


@auth.command(
    epilog="""Examples:

  aitbc auth status

  aitbc auth status --environment staging"""
)
@click.option("--environment", default="default", help="Credential environment name")
@click.pass_context
def status(ctx, environment: str):
    """Show the stored authentication credentials for an environment."""
    manager = AuthManager()
    creds = manager.list_credentials(environment=environment)
    if not creds:
        warning(f"No stored credentials for environment '{environment}'")
        return
    output(creds, ctx.obj.get("output_format", "table"), title="Stored Credentials")


@auth.command(
    epilog="""Examples:

  aitbc auth logout

  aitbc auth logout --environment staging"""
)
@click.option("--environment", default="default", help="Credential environment name")
@click.option("--credential-name", default="client", help="Credential name to delete")
@click.pass_context
def logout(ctx, environment: str, credential_name: str):
    """Delete the stored coordinator credential for an environment."""
    manager = AuthManager()
    if manager.delete_credential(credential_name, environment=environment):
        success(f"Logged out of environment '{environment}'")
    else:
        warning(f"No stored credential for '{credential_name}' in environment '{environment}'")
