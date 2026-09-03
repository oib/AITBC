"""Wallet loader that returns an address and private key for signing payments.

This is intentionally separate from the ``wallet`` command group so that
payment commands in ``market``, ``ai``, and ``ipfs`` can load a wallet without
importing the entire command package at module load time.
"""

from __future__ import annotations

import os
from pathlib import Path


from .address import to_canonical
from .error_handling import abort
from .wallet_paths import find_wallet_file, wallet_dir as resolve_wallet_dir


def _resolve_wallet_name_and_path(
    wallet_name: str | None = None,
    wallet_path: str | None = None,
) -> tuple[str, Path]:
    """Return the wallet name and file path from explicit args or environment/config."""
    if wallet_path:
        wp = Path(wallet_path)
        return wp.stem, wp

    if wallet_name:
        return wallet_name, find_wallet_file(wallet_name) or resolve_wallet_dir() / f"{wallet_name}.json"

    # Try environment and config in priority order
    wallet_name = os.environ.get("AITBC_MARKET_WALLET") or os.environ.get("AITBC_DEFAULT_WALLET")
    if not wallet_name:
        config_file = Path.home() / ".aitbc" / "config.yaml"
        if config_file.exists():
            import yaml

            with open(config_file) as f:
                config = yaml.safe_load(f) or {}
            wallet_name = config.get("active_wallet")
    if not wallet_name:
        wallet_name = "default"

    return wallet_name, resolve_wallet_dir() / f"{wallet_name}.json"


def _resolve_password(wallet_name: str, password: str | None = None) -> str | None:
    """Return the wallet encryption password from explicit arg or environment."""
    if password:
        return password
    env_password = os.environ.get(f"AITBC_WALLET_PASSWORD_{wallet_name.upper()}") or os.environ.get("AITBC_WALLET_PASSWORD")
    if env_password:
        return env_password
    return None


def load_wallet_for_payment(
    ctx,
    wallet_name: str | None = None,
    wallet_path: str | None = None,
    password: str | None = None,
    require_private_key: bool = True,
) -> tuple[str, str | None, str]:
    """Load a wallet and return ``(address, private_key_or_none, wallet_id)``.

    If ``require_private_key`` is False, the private key may be ``None`` (e.g.
    when only the address is needed for an offer listing).  Payment paths that
    must sign transactions should set ``require_private_key=True`` and will
    abort with a clear error if the key is not available.
    """
    name, _ = _resolve_wallet_name_and_path(wallet_name, wallet_path)
    password = _resolve_password(name, password)

    # Search configured and service wallet directories.
    if wallet_path:
        path = Path(wallet_path)
    else:
        path = find_wallet_file(name)
    if path is None:
        # If the file wallet is missing, try the wallet daemon
        from ..config import get_config
        from .dual_mode_wallet_adapter import DualModeWalletAdapter

        config = get_config()
        adapter = DualModeWalletAdapter(config, use_daemon=True)
        info = adapter.get_wallet_info(name)
        if not info:
            abort(ctx, f"Wallet '{name}' not found")
        address = to_canonical(info.get("address", ""))
        if not address:
            abort(ctx, f"Wallet '{name}' has no address")
        if require_private_key:
            abort(ctx, f"Wallet '{name}' is loaded from the daemon; file wallet or explicit private key required for signing")
        return address, None, name

    # Load file wallet (encrypted if needed)
    from ..commands.wallet import _load_wallet

    wallet_data = _load_wallet(path, name)
    address = wallet_data.get("address")
    if not address:
        abort(ctx, f"Wallet '{name}' has no address")
    address = to_canonical(address)

    private_key = wallet_data.get("private_key")
    if isinstance(private_key, dict):
        # Encrypted private key but no password was provided or it did not decrypt.
        # _load_wallet already raises/abort in that case, but be defensive.
        if not password:
            abort(ctx, f"Wallet '{name}' is encrypted; provide --password or set AITBC_WALLET_PASSWORD")
        from ..commands.wallet import decrypt_value

        try:
            private_key = decrypt_value(private_key, password)
        except Exception as e:
            abort(ctx, f"Failed to decrypt wallet '{name}': {e}")
    if require_private_key and (not isinstance(private_key, str) or not private_key):
        abort(ctx, f"Wallet '{name}' has no usable private key for signing")

    return address, private_key if private_key else None, name
