"""UTC time helpers for wallet persistence stamps (#1575).

Wallet ledger/metadata rows store ISO-8601 strings in SQLite. Stamps must be
UTC: ``datetime.now()`` is host-local, which silently shifts every expiry and
ordering window on a non-UTC host, and mixing naive and aware ``datetime``
values raises ``TypeError`` on compare. The bridge tables are shared with
``aitbc-bridge-monitor``, which already stamps aware UTC (``+00:00``), so
writers here use :func:`utc_now_iso`.

Readers normalize stored values with :func:`parse_stored`. Naive values are
interpreted as **host-local** — that is exactly what pre-#1575 rows contain
(``datetime.now().isoformat()`` on the node that wrote them), so legacy rows
keep their previous meaning. Aware values (new rows, bridge-monitor rows) are
converted to UTC. Fleet bridge DBs are node-local, so the writer's zone is
this host's zone.
"""

from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    """Current time as an aware UTC datetime."""
    return datetime.now(UTC)


def utc_now_iso() -> str:
    """Current time as an ISO-8601 string with UTC offset (``+00:00``)."""
    return datetime.now(UTC).isoformat()


def parse_stored(value: Any) -> datetime:
    """Parse a stored ISO timestamp to an aware datetime.

    Accepts ``datetime`` objects and ISO strings. Naive values are assumed to
    be host-local (the pre-#1575 stamp format); aware values are converted to
    UTC. Raises ``ValueError``/``TypeError`` on unparseable input, same as
    ``datetime.fromisoformat``.
    """
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        # Naive stamps predate the UTC convention and were written with
        # datetime.now() — host-local wall time on this node.
        return dt.astimezone()
    return dt.astimezone(UTC)
