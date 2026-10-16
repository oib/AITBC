"""Wallet commands for AITBC CLI"""

import json
import os
from pathlib import Path
from typing import Any

import click
import yaml

from ...config import get_config
from ...utils import error, info, output, success, warning

# Import shared modules
from ...utils.http_client import AITBCHTTPClient, get_logger
from ...utils.wallet_paths import (
    ambiguous_wallet_note,
    find_wallet_file_report,
    is_service_wallet_path,
    wallet_dir as resolve_wallet_dir,
)

# Initialize logger
logger = get_logger(__name__)


def get_wallet_client() -> AITBCHTTPClient:
    """Get HTTP client for wallet service"""
    config = get_config()
    return AITBCHTTPClient(base_url=config.wallet_daemon_url, timeout=30, max_retries=0, api_key=config.wallet_api_key)


def encrypt_value(value: str, password: str) -> dict[str, Any]:
    """Encrypt wallet data using PBKDF2 + Fernet (delegates to aitbc.security.encryption).

    Returns a dict with encrypted_data, salt, algorithm, iterations, version.
    The daemon handles encryption server-side, but direct wallet file access needs real encryption.
    """
    from aitbc.security.encryption import encrypt_value as _encrypt

    return _encrypt(value, password)


def decrypt_value(encrypted: dict[str, Any] | str, password: str) -> str:
    """Decrypt wallet data (delegates to aitbc.security.encryption).

    A bare str means a legacy wallet that was "encrypted" with the old no-op placeholder
    (plaintext stored with encrypted=True). We surface that loudly rather than silently lying.
    """
    if isinstance(encrypted, str):
        raise ValueError(
            "Legacy wallet stored private key as plaintext despite encrypted=True (old no-op encryption). "
            "The key is readable; load it once to re-save with real encryption, or recreate the wallet."
        )
    from aitbc.security.encryption import decrypt_value as _decrypt

    return _decrypt(encrypted, password)


def _save_wallet(wallet_path: Path, wallet_data: dict[str, Any], password: str | None = None):
    """Save wallet with encrypted private key"""
    # Encrypt private key if provided
    if password and "private_key" in wallet_data:
        wallet_data["private_key"] = encrypt_value(wallet_data["private_key"], password)
        wallet_data["encrypted"] = True

    # Save wallet
    with open(wallet_path, "w") as f:
        json.dump(wallet_data, f, indent=2)


def _resave_wallet(ctx: click.Context, wallet_path: Path, wallet_data: dict[str, Any], resolved_password: str | None) -> None:
    """Re-save a wallet after a liquidity mutation, preserving its on-disk
    encryption state. A wallet that was encrypted can never be written back
    without the password that decrypts it: ``_save_wallet`` with a None
    password would dump the in-memory plaintext private key under the
    ``encrypted`` flag. The loader may resolve a password internally that
    the caller never sees, so a missing ``resolved_password`` here is an
    abort, not a plaintext write."""
    if wallet_data.get("encrypted") and not resolved_password:
        error("Wallet is encrypted but no password is resolved — refusing to re-save it as plaintext")
        ctx.exit(1)
    _save_wallet(wallet_path, wallet_data, resolved_password if wallet_data.get("encrypted") else None)


def _emit_wallet_path_note(ctx: click.Context) -> None:
    """Print which file the wallet name resolved to when the shared search
    picked it — a multi-directory match warns which entry won, a
    service-dir hit names the path before the key is loaded for signing so a
    bare ``--wallet-name`` cannot silently select a root-only service file.
    An explicit ``--wallet-path`` never prints."""
    if ctx.obj.get("wallet_path_explicit"):
        return
    report = ctx.obj.get("wallet_path_report")
    if report is not None:
        note = ambiguous_wallet_note(report)
        if note:
            warning(note)
    path = ctx.obj.get("wallet_sign_path")
    if path and is_service_wallet_path(Path(path)):
        info(f"Using wallet file: {path}")


def _load_wallet(
    wallet_path: Path,
    wallet_name: str,
    password: str | None = None,
    password_file: str | None = None,
    password_stdin: bool = False,
) -> dict[str, Any]:
    """Load wallet and decrypt private key if needed.

    The secret is resolved lazily — only when the wallet is actually
    encrypted — through :func:`resolve_wallet_password` (WAL-1), so an
    unencrypted wallet never demands a password source. Callers may pass an
    already-resolved ``password`` plus the standard ``--password-file`` /
    ``--password-stdin`` values; when none applies the interactive/keyring
    fallbacks run as before.
    """
    with open(wallet_path) as f:
        wallet_data: dict[str, Any] = json.load(f)

    # Decrypt private key if encrypted
    if wallet_data.get("encrypted") and "private_key" in wallet_data:
        from ...utils.wallet_secret import resolve_wallet_password

        priv = wallet_data["private_key"]
        if isinstance(priv, str):
            # Legacy no-op "encryption": key was stored as plaintext with encrypted=True.
            # Re-encrypt with a real password and save back to disk before returning.
            if password is None:
                password = resolve_wallet_password(
                    wallet_name, password=password, password_file=password_file, password_stdin=password_stdin
                )
            wallet_data["private_key"] = encrypt_value(priv, password)
            if is_service_wallet_path(wallet_path):
                # A service-managed wallet file must never receive a CLI
                # write (CLI-6c ASK answer) — decrypt in memory, leave the
                # on-disk legacy form untouched.
                warning(f"Not re-encrypting service wallet file in place: {wallet_path}")
            else:
                try:
                    with open(wallet_path, "w") as f:
                        json.dump(wallet_data, f, indent=2)
                except OSError as e:
                    error(f"Failed to re-save wallet with encryption: {e}")
                    raise click.Abort() from e
                click.echo("Re-encrypted legacy wallet with PBKDF2+Fernet.")
            wallet_data["private_key"] = priv  # return plaintext for in-memory use
        else:
            if password is None:
                password = resolve_wallet_password(
                    wallet_name, password=password, password_file=password_file, password_stdin=password_stdin
                )
            try:
                wallet_data["private_key"] = decrypt_value(priv, password)
            except Exception:
                error("Invalid password for wallet")
                raise click.Abort() from None

    return wallet_data


def _load_signing_key(ctx, wallet_name: str | None, wallet_path: Path | None, password, password_file, password_stdin) -> str:
    """Decrypt the wallet file through the standard resolver and return the
    private key — the shared leg every EVM-signing command runs
    (``wallet bridge deposit``, ``exchange prepay deposit``, ``eth-send``)."""
    from ...utils.error_handling import abort
    from ...utils.wallet_secret import resolve_wallet_password

    if wallet_path is None:
        abort(ctx, f"Wallet '{wallet_name}' resolved via the daemon, not a wallet file — cannot sign with it here")
        raise AssertionError("unreachable: abort always raises")
    pw = resolve_wallet_password(
        wallet_name,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
        wallet_path=wallet_path,
        ctx=ctx,
    )
    private_key = _load_wallet(wallet_path, wallet_name or wallet_path.stem, password=pw).get("private_key")
    if not isinstance(private_key, str) or not private_key:
        abort(ctx, "Wallet does not contain a private key")
    assert isinstance(private_key, str)
    return private_key


@click.group(
    epilog="""Examples:

  aitbc wallet --wallet-name genesis balance

  aitbc wallet send --to-address 0xAbc... --amount 1.5"""
)
@click.option("--wallet-name", help="Name of the wallet to use")
@click.option("--wallet-path", help="Direct path to wallet file (overrides --wallet-name)")
@click.option(
    "--use-daemon",
    is_flag=True,
    default=True,
    help="Use wallet daemon for read operations (list/balance/address lookup); signing always uses a file wallet",
)
@click.option("--chain-id", help="Chain ID for multichain operations (e.g., ait-mainnet, ait-devnet)")
@click.pass_context
def wallet(ctx, wallet_name: str | None, wallet_path: str | None, use_daemon: bool, chain_id: str | None):
    """Create, manage, and transact with AITBC wallets on the active chain."""
    # Ensure wallet object exists
    ctx.ensure_object(dict)

    # Set daemon mode
    ctx.obj["use_daemon"] = use_daemon

    # Handle chain_id with auto-detection
    from ...utils.chain_id import get_chain_id

    config = get_config()
    default_rpc_url = config.blockchain_rpc_url if hasattr(config, "blockchain_rpc_url") else "http://localhost:8202"
    # A --chain-id passed to the parent group still wins when the wallet
    # group was invoked without one of its own.
    chain_id = chain_id or ctx.obj.get("chain_id_explicit")
    ctx.obj["chain_id"] = get_chain_id(default_rpc_url, override=chain_id)
    # Keep the raw flag value so signing paths can distinguish an explicit
    # --chain-id/CHAIN_ID choice from an auto-detected or absent one.
    ctx.obj["chain_id_explicit"] = chain_id
    # And the URL the resolution ran against: a detected chain id is only
    # valid for transactions submitted to that same RPC.
    ctx.obj["chain_id_rpc_url"] = default_rpc_url

    # Initialize dual-mode adapter
    from aitbc_cli.utils.dual_mode_wallet_adapter import DualModeWalletAdapter

    config = get_config()
    adapter = DualModeWalletAdapter(config, use_daemon=use_daemon)
    ctx.obj["wallet_adapter"] = adapter

    # If direct wallet path is provided, use it
    if wallet_path:
        wp = Path(wallet_path)
        wp.parent.mkdir(parents=True, exist_ok=True)
        ctx.obj["wallet_name"] = wp.stem
        ctx.obj["wallet_dir"] = wp.parent
        ctx.obj["wallet_path"] = wp
        ctx.obj["wallet_sign_path"] = wp
        ctx.obj["wallet_path_explicit"] = True
        return

    # Set wallet directory
    wallet_dir = resolve_wallet_dir()
    wallet_dir.mkdir(parents=True, exist_ok=True)

    # Set active wallet (priority: CLI arg > env var > config.yaml > 'default')
    if not wallet_name:
        # 1. Check AITBC_DEFAULT_WALLET env var
        wallet_name = os.environ.get("AITBC_DEFAULT_WALLET")
        # 2. Check config.yaml for active_wallet
        if not wallet_name:
            config_file = Path.home() / ".aitbc" / "config.yaml"
            if config_file.exists():
                with open(config_file) as f:
                    config = yaml.safe_load(f)
                    if config:
                        wallet_name = config.get("active_wallet")
        # 3. Fall back to 'default'
        if not wallet_name:
            wallet_name = "default"

    ctx.obj["wallet_name"] = wallet_name
    ctx.obj["wallet_dir"] = wallet_dir
    # Two views of the same name (CLI-6c ASK answer): ``wallet_path`` is the
    # configured-dir file — the only file a command that writes the wallet
    # (export, earn/spend/liquidity bookkeeping re-saves, delete/restore…)
    # may touch. ``wallet_sign_path`` is the shared-search result for
    # load/sign/read commands and may land in the service wallet dir.
    wallet_report = find_wallet_file_report(wallet_name)
    ctx.obj["wallet_path"] = wallet_dir / f"{wallet_name}.json"
    ctx.obj["wallet_sign_path"] = wallet_report.path or ctx.obj["wallet_path"]
    ctx.obj["wallet_path_report"] = wallet_report
    ctx.obj["wallet_path_explicit"] = False


# Register all subcommands
from . import basic, bridge, eth_balance, eth_send, misc, multisig, staking  # noqa: E402
