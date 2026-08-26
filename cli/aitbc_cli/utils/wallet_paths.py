"""Resolve the CLI file-wallet directory.

Service wallets on a node live under ``/var/lib/aitbc/wallets``.  The default
for a normal user is still ``~/.aitbc/wallets``.  The service users
(``aitbc`` and ``aitbc-wallet``) resolve to ``/var/lib/aitbc/wallets`` even when
their interactive ``$HOME`` is ``/home/aitbc`` or similar, so services and
operator shells share one standard.
"""

from __future__ import annotations

import os
import pwd
from pathlib import Path

# Service directories searched in addition to the configured wallet_dir.
# The old ``/var/lib/aitbc/.aitbc/wallets`` path is no longer supported.
_SERVICE_WALLET_DIRS = ["/var/lib/aitbc/wallets"]


def _default_wallet_dir() -> Path:
    """Return the default wallet directory for the current user.

    * ``AITBC_WALLET_DIR`` always wins.
    * The ``aitbc`` and ``aitbc-wallet`` system accounts always use
      ``/var/lib/aitbc/wallets``.
    * Any other account keeps the original ``~/.aitbc/wallets`` default.
    """
    home = Path.home()
    if home == Path("/var/lib/aitbc"):
        return home / "wallets"
    try:
        user = pwd.getpwuid(os.getuid()).pw_name
    except (KeyError, OSError):
        user = ""
    if user in ("aitbc", "aitbc-wallet"):
        return Path("/var/lib/aitbc/wallets")
    return home / ".aitbc" / "wallets"


def wallet_dir(override: Path | str | None = None) -> Path:
    """Return the directory that holds ``<name>.json`` file wallets.

    Precedence: explicit *override*, then ``AITBC_WALLET_DIR``, then the
    default home-based wallet directory.
    """
    if override is not None:
        return Path(override)
    env = os.getenv("AITBC_WALLET_DIR")
    if env:
        return Path(env)
    return _default_wallet_dir()


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
