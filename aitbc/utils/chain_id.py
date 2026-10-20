"""Single point for resolving the local chain id outside the node package.

Mirrors ``aitbc_chain.chain_id.resolve_chain_id`` for the services and
tools that do not run inside ``aitbc_chain``. One shared precedence:

    explicit argument > AITBC_CHAIN_ID > CHAIN_ID > default-or-raise

``AITBC_CHAIN_ID`` wins over ``CHAIN_ID`` so a caller can pin an island id
without shadowing the fleet-wide name. With no ``default`` the resolver is
strict — a typed ``ChainIdNotConfigured`` error instead of a silently
substituted literal. Passing ``default`` (or calling ``default_chain_id``)
makes the terminal step the reset default ``bc-2``, which is the honest
answer for SDK dataclass fields and pre-settings code paths whose callers
routinely omit the argument.
"""

from __future__ import annotations

import os
from typing import Final

from ..exceptions import ConfigurationError

DEFAULT_CHAIN_ID: Final = "bc-2"


class ChainIdNotConfigured(ConfigurationError):
    """No chain id could be resolved.

    Raised when neither an explicit ``chain_id`` argument, ``AITBC_CHAIN_ID``,
    nor the ``CHAIN_ID`` environment variable provides a non-empty value and
    the caller passed no ``default``.
    """


def _env_chain_id() -> str:
    return os.environ.get("AITBC_CHAIN_ID", "").strip() or os.environ.get("CHAIN_ID", "").strip()


def resolve_chain_id(chain_id: str | None = None, *, default: str | None = None) -> str:
    """Resolve the chain id to use.

    Order: explicit argument, ``AITBC_CHAIN_ID``, ``CHAIN_ID``, then
    ``default`` when one was passed. Empty strings count as unset at every
    level.

    Raises:
        ChainIdNotConfigured: when nothing resolves and no ``default`` was
            given.
    """
    if chain_id and chain_id.strip():
        return chain_id.strip()
    env_id = _env_chain_id()
    if env_id:
        return env_id
    if default and default.strip():
        return default.strip()
    raise ChainIdNotConfigured(
        "chain id is not configured: pass chain_id explicitly or set CHAIN_ID; refusing to fall back to a hard-coded chain id"
    )


def default_chain_id() -> str:
    """No-arg factory for dataclass fields: shared env precedence, then bc-2."""
    return resolve_chain_id(default=DEFAULT_CHAIN_ID)
