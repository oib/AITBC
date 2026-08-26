"""Resolve the CLI file-wallet directory.

Service wallets on a hub node live under ``/var/lib/aitbc/wallets``, not the
invoking user's home. ``aitbc auth login`` already honoured ``AITBC_WALLET_DIR``
for that case; every other file-wallet lookup now goes through here too.
"""

from __future__ import annotations

import os
from pathlib import Path

# Common service directories used when the standard user wallet dir does not
# contain a requested wallet.  The first existing, explicit ``AITBC_WALLET_DIR``
# or the standard ``~/.aitbc/wallets`` are always tried first.
_SERVICE_WALLET_DIRS = ["/var/lib/aitbc/wallets", "/var/lib/aitbc/.aitbc/wallets"]


def wallet_dir(override: Path | str | None = None) -> Path:
    """Return the directory that holds ``<name>.json`` file wallets.

    Precedence: explicit *override*, then ``AITBC_WALLET_DIR``, then
    ``~/.aitbc/wallets``.
    """
    if override is not None:
        return Path(override)
    env = os.getenv("AITBC_WALLET_DIR")
    if env:
        return Path(env)
    return Path.home() / ".aitbc" / "wallets"


def wallet_search_dirs() -> list[Path]:
    """Return all directories that should be searched for file wallets."""
    dirs: list[Path] = [wallet_dir()]
    seen = {dirs[0]}
    for candidate in _SERVICE_WALLET_DIRS:
        p = Path(candidate)
        if p not in seen:
            seen.add(p)
            dirs.append(p)
    return dirs


def find_wallet_file(wallet_name: str) -> Path | None:
    """Find a file wallet by name across the configured and service directories."""
    for directory in wallet_search_dirs():
        path = directory / f"{wallet_name}.json"
        if path.exists():
            return path
    return None
