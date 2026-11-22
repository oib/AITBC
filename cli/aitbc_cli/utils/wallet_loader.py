"""Wallet loader that returns an address and private key for signing payments.

This is intentionally separate from the ``wallet`` command group so that
payment commands in ``market``, ``ai``, and ``ipfs`` can load a wallet without
importing the entire command package at module load time.
"""

from __future__ import annotations

import errno
import json
import os
import tempfile
from pathlib import Path
from typing import cast


from .address import to_canonical
from .error_handling import abort
from .output import info
import re

from .wallet_paths import (
    WalletSearchResult,
    find_wallet_file,
    find_wallet_file_report,
    service_dir_wallet_note,
    wallet_dir as resolve_wallet_dir,
    wallet_not_found_hint,
    wallet_not_found_message,
    wallet_search_dirs,
)

_WALLET_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def validate_wallet_name(name: object) -> str:
    """Return the wallet name if it is safe to join into the wallet dir.

    Letters, digits, ``-``, ``_`` and ``.`` only, never starting with a dot
    and never a path separator — a name that escapes ``wallet_dir`` (``..``,
    ``/``, absolute paths, ``.hidden``) is a traversal, not a wallet
    (CLI-WALLET-IMPORT-NAME-TRAVERSAL-1, #846).
    """
    if not isinstance(name, str) or not _WALLET_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid wallet name {name!r}: letters, digits, '-', '_' and '.' only, not starting with a dot")
    return name


def write_json_0600(path: Path, data: dict, *, fsync: bool = False) -> None:
    """Write JSON to *path* readable only by the owner, never via a symlink.

    The payload is serialized into a same-directory 0600 temp file that is
    fsynced and ``os.replace``d onto *path*, so a failed or interrupted
    rewrite can never leave a truncated wallet behind
    (AUDIT-WALLET-WRITE-TORN-1, #2525). A symlink at *path* is refused with
    ELOOP rather than silently replaced — the ``O_NOFOLLOW`` guarantee of
    CLI-WALLET-FILE-MODES-1 (#845) is preserved — and the published file is
    always mode 0600, tightening any pre-existing lax file.
    """
    if path.is_symlink():
        raise OSError(errno.ELOOP, "too many levels of symbolic links", str(path))
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as f:
            os.fchmod(fd, 0o600)
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        if fsync:
            dirfd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


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


def _resolve_signing_password(
    ctx,
    name: str,
    path: Path | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
) -> str:
    """Resolve the secret through the WAL-1 shared helper.

    ``allow_unencrypted`` keeps the pre-WAL-1 behaviour where a file wallet
    storing an unencrypted key needs no password (the helper returns ``""``).
    """
    from .wallet_secret import resolve_wallet_password

    return resolve_wallet_password(
        name,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
        wallet_path=path,
        ctx=ctx,
    )


def find_wallet_by_address(address: str) -> Path | None:
    """Return the first file wallet whose recorded address matches ``address``.

    ``SHOP_WALLET_ADDRESS`` names a provider account, not a wallet name — this
    resolves which local file (if any) can sign for it. Matches the wallet's
    top-level ``address`` plus ``metadata.address`` / ``metadata.original_address``
    for service-wallet shapes; the first hit in search-dir order wins.
    """
    target = to_canonical(address)
    for directory in wallet_search_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            metadata = data.get("metadata") or {}
            candidates = (data.get("address"), metadata.get("address"), metadata.get("original_address"))
            if any(isinstance(c, str) and to_canonical(c) == target for c in candidates):
                return path
    return None


def load_wallet_for_payment(
    ctx,
    wallet_name: str | None = None,
    wallet_path: str | None = None,
    password: str | None = None,
    password_file: str | None = None,
    password_stdin: bool = False,
    require_private_key: bool = True,
) -> tuple[str, str | None, str]:
    """Load a wallet and return ``(address, private_key_or_none, wallet_id)``.

    If ``require_private_key`` is False, the private key may be ``None`` (e.g.
    when only the address is needed for an offer listing).  Payment paths that
    must sign transactions should set ``require_private_key=True`` and will
    abort with a clear error if the key is not available.
    """
    name, _ = _resolve_wallet_name_and_path(wallet_name, wallet_path)

    # Search configured and service wallet directories.
    path: Path | None
    report = find_wallet_file_report(name)
    if wallet_path:
        path = Path(wallet_path)
    else:
        path = report.path
        if require_private_key:
            note = service_dir_wallet_note(report)
            if note:
                info(note)
    if path is not None:
        password = _resolve_signing_password(ctx, name, path, password, password_file, password_stdin)
    else:
        password = _resolve_password(name, password)
    if path is None:
        # If the file wallet is missing, try the wallet daemon
        return _load_wallet_from_daemon(ctx, name, report, require_private_key)

    # Load file wallet (encrypted if needed)
    from ..commands.wallet import _load_wallet

    wallet_data = _load_wallet(path, name, password=password)
    raw_address = wallet_data.get("address")
    if not raw_address:
        abort(ctx, f"Wallet '{name}' has no address")
    address = to_canonical(cast(str, raw_address))

    private_key = _extract_private_key(ctx, name, wallet_data, password)

    if require_private_key and (not isinstance(private_key, str) or not private_key):
        abort(ctx, f"Wallet '{name}' has no usable private key for signing")

    if isinstance(private_key, str) and private_key:
        derived = _address_for_private_key(private_key)
        if derived is not None and to_canonical(derived) != address:
            # The file's address field is a claim, not proof — a wallet whose
            # key derives a different address would sign for the wrong
            # account (#2598).
            abort(
                ctx,
                f"Wallet '{name}' is inconsistent: stored address {address} does not "
                f"match the address derived from its private key {to_canonical(derived)}",
            )

    return address, cast(str | None, private_key if private_key else None), name


def _address_for_private_key(private_key: str) -> str | None:
    """Derive the secp256k1 address for *private_key*; None when it is not a
    usable key (signing paths will fail on it later regardless)."""
    try:
        from eth_account import Account

        key = private_key if private_key.startswith("0x") else f"0x{private_key}"
        return cast(str, Account.from_key(key).address)
    except Exception:  # noqa: BLE001 - derivation probe: unusable keys simply yield no address
        return None


def _load_wallet_from_daemon(
    ctx,
    name: str,
    report: WalletSearchResult,
    require_private_key: bool,
) -> tuple[str, str | None, str]:
    """Resolve the wallet through the wallet daemon keystore.

    Signing still requires a file wallet — a daemon-only wallet can only
    satisfy address lookups (``require_private_key=False``).
    """
    from ..config import get_config
    from .dual_mode_wallet_adapter import DualModeWalletAdapter

    config = get_config()
    adapter = DualModeWalletAdapter(config, use_daemon=True)
    info_doc = adapter.get_wallet_info(name)
    if not info_doc:
        abort(ctx, wallet_not_found_message(report))
    info_doc = cast(dict, info_doc)
    address = to_canonical(info_doc.get("address", ""))
    if not address:
        abort(ctx, f"Wallet '{name}' has no address")
    if require_private_key:
        abort(
            ctx,
            f"Wallet '{name}' exists only in the wallet daemon keystore; signing needs a "
            f"file wallet — pass --wallet-path <file>.\n  {wallet_not_found_hint(report)}",
        )
    return address, None, name


def _extract_private_key(ctx, name: str, wallet_data: dict, password: str | None) -> object:
    """Return the wallet's private key, decrypting it when stored encrypted."""
    private_key = wallet_data.get("private_key")
    if isinstance(private_key, dict):
        # Encrypted private key but no password was provided or it did not decrypt.
        # _load_wallet already raises/abort in that case, but be defensive.
        if not password:
            abort(ctx, f"Wallet '{name}' is encrypted; provide --password-file, --password-stdin, or --password")
        password = cast(str, password)
        from ..commands.wallet import decrypt_value

        try:
            private_key = decrypt_value(private_key, password)
        except ValueError as e:
            abort(ctx, f"Failed to decrypt wallet '{name}': {e}")
    return private_key
