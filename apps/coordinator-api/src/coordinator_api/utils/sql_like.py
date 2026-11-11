"""LIKE-pattern helpers for user-supplied search strings (#1524).

``%`` and ``_`` are LIKE metacharacters: a search for ``model=%`` would
otherwise match every row. Values stay parameter-bound (no injection),
but the metacharacters must be escaped for the match to stay literal.
Pair ``like_contains``/``escape_like`` output with ``escape="\\\\"`` on the
SQLAlchemy ``like``/``ilike`` call — same convention as
``aitbc_chain.messaging_index._like_escape`` and the explorer's
``like_pattern``.
"""

from __future__ import annotations

LIKE_ESCAPE = "\\"


def escape_like(text: str) -> str:
    """Escape LIKE metacharacters (``\\``, ``%``, ``_``) for ``ESCAPE '\\'``."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_contains(text: str) -> str:
    """``%<text>%`` pattern with LIKE metacharacters escaped."""
    return f"%{escape_like(text)}%"
