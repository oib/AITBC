"""Resolve the CLI file-wallet directory.

Service wallets on a hub node live under ``/var/lib/aitbc/wallets``, not the
invoking user's home. ``aitbc auth login`` already honoured ``AITBC_WALLET_DIR``
for that case; every other file-wallet lookup now goes through here too.
"""

from __future__ import annotations

import os
from pathlib import Path


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
