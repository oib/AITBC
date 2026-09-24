"""Environment-variable compatibility for the marketplace → market rename.

The rename renamed the service's settings along with its routes:
``MARKETPLACE_SERVICE_URL`` became ``MARKET_SERVICE_URL``, and so on. Reading
only the new name means a host still carrying the old one falls back to the
code default — a localhost URL or an on-disk path that usually exists, so the
service starts clean and points at the wrong thing instead of failing.

``market_getenv`` reads the canonical name first and accepts the legacy one as
a fallback, warning once per variable so the remaining hosts can be found.
"""

from __future__ import annotations

import os
from typing import overload

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

CANONICAL_PREFIX = "MARKET_"
LEGACY_PREFIX = "MARKETPLACE_"

_warned: set[str] = set()


def legacy_market_name(name: str) -> str | None:
    """Return the pre-rename spelling of ``name``, or None if it has none."""
    if not name.startswith(CANONICAL_PREFIX):
        return None
    return LEGACY_PREFIX + name[len(CANONICAL_PREFIX) :]


@overload
def market_getenv(name: str) -> str | None: ...


@overload
def market_getenv(name: str, default: str) -> str: ...


@overload
def market_getenv(name: str, default: None) -> str | None: ...


def market_getenv(name: str, default: str | None = None) -> str | None:
    """``os.getenv(name)`` with a fallback to the pre-rename ``MARKETPLACE_*`` name.

    The canonical name always wins when both are set, so a host part-way
    through the migration behaves like a migrated one.
    """
    value = os.environ.get(name)
    if value is not None:
        return value

    legacy = legacy_market_name(name)
    if legacy is None:
        return default

    value = os.environ.get(legacy)
    if value is None:
        return default

    if legacy not in _warned:
        _warned.add(legacy)
        logger.warning("%s is deprecated; rename it to %s", legacy, name)
    return value
