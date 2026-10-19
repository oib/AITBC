"""Single point for resolving this node's chain id.

Every site that needs "the local chain" resolves it here instead of
silently falling back to a hard-coded id. An unconfigured node raises
``ChainIdNotConfigured`` rather than opening or creating the wrong
chain's database under ``data/<chain_id>/``.
"""

from __future__ import annotations

from .config import settings


class ChainIdNotConfigured(RuntimeError):
    """No chain id could be resolved.

    Raised when neither an explicit ``chain_id`` argument, nor the
    test-only ``database._default_chain_id`` override, nor
    ``settings.chain_id`` (CHAIN_ID) provides one.
    """


def resolve_chain_id(chain_id: str | None = None) -> str:
    """Resolve the chain id to use.

    Order: explicit argument, then the test-only default
    (``database._default_chain_id``, only ever set by tests), then
    ``settings.chain_id``.

    Raises:
        ChainIdNotConfigured: when none of the three sources yields a
        non-empty id.
    """
    if chain_id:
        return chain_id
    from . import database  # lazy: database imports this module

    if database._default_chain_id:
        return database._default_chain_id
    if settings.chain_id:
        return settings.chain_id
    raise ChainIdNotConfigured(
        "chain id is not configured: pass chain_id explicitly or set CHAIN_ID "
        "in the node's env files; refusing to fall back to a hard-coded chain"
    )
