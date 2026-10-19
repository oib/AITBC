"""Single point for resolving the local chain id outside the node package.

Mirrors ``aitbc_chain.chain_id.resolve_chain_id`` for the services and
tools that do not run inside ``aitbc_chain``: an explicit argument wins,
then the ``CHAIN_ID`` environment variable, then a typed
``ChainIdNotConfigured`` error. No string literal is ever substituted —
an unconfigured caller fails loudly instead of silently operating on the
wrong chain.
"""

from __future__ import annotations

import os

from ..exceptions import ConfigurationError


class ChainIdNotConfigured(ConfigurationError):
    """No chain id could be resolved.

    Raised when neither an explicit ``chain_id`` argument nor the
    ``CHAIN_ID`` environment variable provides a non-empty value.
    """


def resolve_chain_id(chain_id: str | None = None) -> str:
    """Resolve the chain id to use.

    Order: explicit argument, then the ``CHAIN_ID`` environment variable.

    Raises:
        ChainIdNotConfigured: when neither source yields a non-empty id.
    """
    if chain_id and chain_id.strip():
        return chain_id.strip()
    env_id = os.environ.get("CHAIN_ID", "").strip()
    if env_id:
        return env_id
    raise ChainIdNotConfigured(
        "chain id is not configured: pass chain_id explicitly or set CHAIN_ID; refusing to fall back to a hard-coded chain id"
    )
