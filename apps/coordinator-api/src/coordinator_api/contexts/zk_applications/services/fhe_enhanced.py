"""
Enhanced FHE Service - disabled

The BFV implementation in this module is not cryptographically secure. It is
intentionally disabled pending integration with a vetted FHE library such as
TenSEAL or Microsoft SEAL.
"""

from __future__ import annotations

from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class _DisabledFHE:
    """Disabled FHE provider that raises on any operation."""

    def _disabled(self, *_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError("Insecure BFV implementation is disabled; use a vetted FHE library")

    def __getattr__(self, name: str) -> Any:
        return self._disabled


class BFVProvider(_DisabledFHE):
    """BFV FHE provider — intentionally disabled for security."""

    def __init__(self, session: Any = None) -> None:
        self.available = False
        self.session = session
        logger.info("BFV FHE provider initialized in disabled state")


_fhe_provider: BFVProvider | None = None


def get_fhe_provider() -> BFVProvider:
    """Get or create the disabled FHE provider."""
    global _fhe_provider
    if _fhe_provider is None:
        _fhe_provider = BFVProvider()
    return _fhe_provider
