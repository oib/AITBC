"""Derived read index for on-chain forum messages (MSG-1).

Design (docs/design/msg1-onchain-messaging.md): the index is a *query over
the existing ``transaction`` table* — no materialized table, no apply-path
hook, no migration. Proposer, follower and bulk-sync paths already persist
MESSAGE rows with payload and block_height, and fork-heal deletes the losing
block's rows, so the index inherits deterministic replay and reorg removal
for free. A materialized table populated by these same queries remains a
pure performance follow-up behind this module boundary.

Validity is one predicate — :func:`aitbc.messaging.envelope_error` — applied
in Python before paging, grouping and counting. SQLite cannot express the
byte-length/charset/normalisation checks, so reads run a *bounded* scan over
the cheap SQL prefilter (``type='MESSAGE'`` + ``aitbc_msg`` key present) and
predicate-filter each candidate. A hostile proposer's junk rows therefore
never skew topic counts or pagination; they only consume scan budget, which
is bounded per request and surfaced via ``scan_bounded``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_
from sqlmodel import col, select

from aitbc.messaging import MSG_NAMESPACE, envelope_error, extract_envelope

from .base_models import _to_ait_address
from .models import Block, Transaction

#: Read-path bounds (public routes). A page never returns more than
#: MAX_READ_LIMIT items; every request scans at most SCAN_BOUND candidate
#: rows; topic/search scans are bounded the same way.
MAX_READ_LIMIT = 100
DEFAULT_READ_LIMIT = 50
MAX_OFFSET = 500
SCAN_BOUND = 8192

_HEX64 = set("0123456789abcdef")


def admission_error(payload: Any, sender: str) -> str | None:
    """Admission-time check: a payload *claiming* ``aitbc_msg`` must be valid.

    Opaque MESSAGE payloads (bridge internals, other uses) pass unchanged —
    this only refuses a broken forum claim so the signer hears about it
    before paying the fee. Sealed junk that bypassed admission anyway is
    still filtered at read time by the same predicate.
    """
    from aitbc.messaging import claims_envelope

    if not claims_envelope(payload):
        return None
    return envelope_error(extract_envelope(payload), sender=sender)


def parse_cursor(cursor: str | None) -> tuple[int, int] | None:
    """Parse a ``<block_height>:<row_id>`` keyset cursor, or ``None``."""
    if not cursor:
        return None
    try:
        height_s, row_s = cursor.split(":", 1)
        return int(height_s), int(row_s)
    except (ValueError, AttributeError):
        raise ValueError("invalid cursor (want '<block_height>:<row_id>' from a previous next_cursor)") from None


def _like_escape(text: str) -> str:
    """Escape LIKE metacharacters for a literal substring match (escape '\\')."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _index_height(session, chain_id: str) -> int:
    head = session.exec(select(func.max(Block.height)).where(col(Block.chain_id) == chain_id)).first()
    return int(head) if head is not None else 0


def _candidate_select(
    chain_id: str,
    *,
    topic: str | None = None,
    author: str | None = None,
    body_contains: str | None = None,
):
    """SQL prefilter for message candidates. Validity is *not* decided here —
    it narrows the scan window; :func:`envelope_error` is the arbiter."""
    stmt = (
        select(Transaction)
        .where(
            col(Transaction.chain_id) == chain_id,
            col(Transaction.type) == "MESSAGE",
            col(Transaction.block_height).is_not(None),
            func.json_type(col(Transaction.payload), f"$.{MSG_NAMESPACE}") == "object",
        )
        .order_by(col(Transaction.block_height).desc(), col(Transaction.id).desc())
    )
    if topic is not None:
        stmt = stmt.where(func.json_extract(col(Transaction.payload), f"$.{MSG_NAMESPACE}.topic") == topic)
    if author is not None:
        # sender is stored verbatim (signed bytes); the two legal spellings
        # differ only in casing (EIP-55 / lowercase).
        stmt = stmt.where(func.lower(col(Transaction.sender)) == author.lower())
    if body_contains is not None:
        stmt = stmt.where(
            func.json_extract(col(Transaction.payload), f"$.{MSG_NAMESPACE}.body").like(
                f"%{_like_escape(body_contains)}%", escape="\\"
            )
        )
    return stmt


def _apply_cursor(stmt, cursor: tuple[int, int] | None):
    """Keyset filter for DESC (block_height, id) ordering."""
    if cursor is None:
        return stmt
    height, row_id = cursor
    return stmt.where(
        or_(
            col(Transaction.block_height) < height,
            and_(col(Transaction.block_height) == height, col(Transaction.id) < row_id),
        )
    )


def _scan_valid(
    session,
    stmt,
    *,
    cursor: tuple[int, int] | None,
    limit: int,
    scan_bound: int,
) -> tuple[list[Transaction], str | None, bool]:
    """Walk candidates newest-first, returning up to ``limit`` *valid* rows.

    Returns ``(rows, next_cursor, scan_bounded)``:

    - ``next_cursor`` resumes after the last returned row when the page is
      full, or after the last scanned row when the bound cut the scan short
      (junk never wedges a reader: the cursor always advances).
    - ``scan_bounded`` reports that the scan bound cut the scan — the page is
      short and more candidates may exist beyond the cursor.
    """
    rows = session.exec(_apply_cursor(stmt, cursor).limit(scan_bound + 1)).all()
    out: list[Transaction] = []
    last_scanned: Transaction | None = None
    for row in rows[:scan_bound]:
        last_scanned = row
        if envelope_error(extract_envelope(row.payload), sender=row.sender) is not None:
            continue
        out.append(row)
        if len(out) >= limit:
            return out, f"{row.block_height}:{row.id}", False
    # Page not full. More candidates may exist iff the bound+1 fetch overshot.
    if len(rows) > scan_bound and last_scanned is not None:
        return out, f"{last_scanned.block_height}:{last_scanned.id}", True
    return out, None, False


def _resolve_parents(session, chain_id: str, items: list[dict[str, Any]]) -> None:
    """Set ``parent_resolved`` on reply views (batched lookup).

    A parent resolves to a sealed transaction row that is itself a valid
    forum message (any kind). Unresolvable parents stay indexed — the flag is
    what the reader shows, not a drop.
    """
    parents = {m["parent"] for m in items if m.get("parent")}
    if not parents:
        return
    resolved: set[str] = set()
    for row in session.exec(
        select(Transaction).where(
            col(Transaction.chain_id) == chain_id,
            col(Transaction.tx_hash).in_(parents),
            col(Transaction.block_height).is_not(None),
        )
    ).all():
        if envelope_error(extract_envelope(row.payload), sender=row.sender) is None:
            resolved.add(row.tx_hash)
    for m in items:
        if m.get("parent"):
            m["parent_resolved"] = m["parent"] in resolved


def _view(tx: Transaction) -> dict[str, Any]:
    env = extract_envelope(tx.payload) or {}
    sender = _to_ait_address(tx.sender)
    view: dict[str, Any] = {
        "message_id": tx.tx_hash,
        "tx_hash": tx.tx_hash,
        "block_height": tx.block_height,
        "author": sender,
        "sender": sender,
        "topic": env.get("topic"),
        "kind": env.get("kind"),
        "body": env.get("body"),
        "parent": env.get("parent"),
        "timestamp": tx.timestamp,
        "fee": tx.fee,
    }
    return view


def list_messages(
    session,
    chain_id: str,
    *,
    topic: str | None = None,
    author: str | None = None,
    body_contains: str | None = None,
    limit: int = DEFAULT_READ_LIMIT,
    offset: int = 0,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Page forum messages newest-first. ``topic`` is the canonical slug."""
    limit = max(1, min(int(limit), MAX_READ_LIMIT))
    offset = max(0, min(int(offset), MAX_OFFSET))
    parsed = parse_cursor(cursor)
    stmt = _candidate_select(chain_id, topic=topic, author=author, body_contains=body_contains)
    rows, next_cursor, bounded = _scan_valid(session, stmt, cursor=parsed, limit=limit + offset, scan_bound=SCAN_BOUND)
    items = [_view(tx) for tx in rows[offset:]]
    _resolve_parents(session, chain_id, items)
    return {
        "success": True,
        "chain_id": chain_id,
        "index_height": _index_height(session, chain_id),
        "messages": items,
        "count": len(items),
        "next_cursor": next_cursor,
        "scan_bounded": bounded,
    }


def get_message(session, chain_id: str, tx_hash: str) -> dict[str, Any] | None:
    """One message by its tx_hash; ``None`` when absent or not a valid message."""
    tx = session.exec(
        select(Transaction).where(
            col(Transaction.chain_id) == chain_id,
            col(Transaction.tx_hash) == tx_hash,
            col(Transaction.type) == "MESSAGE",
            col(Transaction.block_height).is_not(None),
        )
    ).first()
    if tx is None or envelope_error(extract_envelope(tx.payload), sender=tx.sender) is not None:
        return None
    view = _view(tx)
    _resolve_parents(session, chain_id, [view])
    return view


def list_topics(
    session,
    chain_id: str,
    *,
    limit: int = DEFAULT_READ_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Topics ranked by last activity, aggregated over a bounded candidate scan.

    Only valid rows are aggregated (the predicate runs before GROUP BY —
    sealed junk cannot create a topic or inflate a count). When the scan
    bound truncates history, ``scan_bounded`` is set and counts may
    understate older messages.
    """
    limit = max(1, min(int(limit), MAX_READ_LIMIT))
    offset = max(0, min(int(offset), MAX_OFFSET))
    stmt = _candidate_select(chain_id)
    topics: dict[str, dict[str, Any]] = {}
    rows = session.exec(stmt.limit(SCAN_BOUND + 1)).all()
    bounded = len(rows) > SCAN_BOUND
    for row in rows[:SCAN_BOUND]:
        env = extract_envelope(row.payload)
        if env is None or envelope_error(env, sender=row.sender) is not None:
            continue
        topic = env["topic"]
        entry = topics.get(topic)
        if entry is None:
            topics[topic] = {
                "topic": topic,
                "message_count": 1,
                "last_block_height": row.block_height,
                "last_timestamp": row.timestamp,
            }
        else:
            entry["message_count"] += 1
    ranked = sorted(topics.values(), key=lambda t: (-t["last_block_height"], t["topic"]))
    page = ranked[offset : offset + limit]
    return {
        "success": True,
        "chain_id": chain_id,
        "index_height": _index_height(session, chain_id),
        "topics": page,
        "count": len(page),
        "total_topics": len(ranked),
        "scan_bounded": bounded,
    }


def state(session, chain_id: str) -> dict[str, Any]:
    """Totals for the legacy ``/messaging/state`` route, index-derived."""
    stmt = _candidate_select(chain_id)
    rows = session.exec(stmt.limit(SCAN_BOUND + 1)).all()
    topics: set[str] = set()
    authors: set[str] = set()
    messages = 0
    for row in rows[:SCAN_BOUND]:
        env = extract_envelope(row.payload)
        if env is None or envelope_error(env, sender=row.sender) is not None:
            continue
        messages += 1
        topics.add(env["topic"])
        authors.add(_to_ait_address(row.sender))
    return {
        "success": True,
        "chain_id": chain_id,
        "index_height": _index_height(session, chain_id),
        "contract_state": {
            "total_topics": len(topics),
            "total_messages": messages,
            "total_agents": len(authors),
        },
        "scan_bounded": len(rows) > SCAN_BOUND,
    }
