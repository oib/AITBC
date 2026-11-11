"""Keyset (cursor) pagination helpers for RPC list endpoints (#1717).

OFFSET pages skip/dup rows when the underlying table mutates between
fetches; a keyset cursor resumes strictly after the last returned row's
sort key, so inserts and deletes elsewhere in the table cannot shift the
page window. Cursors are plain ``<part>|<part>`` strings echoing stored
values — the messaging ``<block_height>:<tx_hash>`` precedent — not
opaque tokens: the key columns are already public read data.

Datetime parts travel as ``datetime.isoformat()``; stored values are
naive UTC, so a tz-aware echo is normalised back to naive UTC before it
is bound again (SQLite DATETIME storage drops the offset either way).
"""

from __future__ import annotations

from datetime import UTC, datetime

_MAX_PART_LEN = 256


def cursor_dt(text: str) -> datetime:
    """Parse an ISO-8601 cursor timestamp into naive UTC."""
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def split_cursor(cursor: str | None, arity: int, *, what: str) -> list[str] | None:
    """Split a ``|``-joined cursor into ``arity`` parts, or ``None``.

    Raises ``ValueError`` on malformed input — callers translate to a 400.
    Parts are length-capped; the values are echoed back into SQL binds, so
    an absurd blob is rejected before it reaches a query.
    """
    if cursor is None or cursor == "":
        return None
    parts = cursor.split("|")
    if len(parts) != arity or any(not p or len(p) > _MAX_PART_LEN for p in parts):
        raise ValueError(f"invalid cursor (want {what} from a previous next_cursor)")
    return parts


def parse_or_400(cursor: str | None, arity: int, *, what: str, detail: str) -> list[str] | None:
    """``split_cursor`` with the ValueError translated to HTTP 400."""
    from fastapi import HTTPException

    try:
        return split_cursor(cursor, arity, what=what)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=detail) from e
