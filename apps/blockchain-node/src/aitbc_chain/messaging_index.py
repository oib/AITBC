"""Derived read index for on-chain forum messages (MSG-1).

Design (docs/design/msg1-onchain-messaging.md): the index is a *query over
the existing ``transaction`` table* — no materialized table, no apply-path
hook, no migration. Proposer, follower and bulk-sync paths already persist
MESSAGE rows with payload and block_height, and fork-heal deletes the losing
block's rows, so the index inherits deterministic replay and reorg removal
for free. A materialized table populated by these same queries remains a
pure performance follow-up behind this module boundary.

Reads select **columns, not rows** (F1): the full ``payload`` JSON — up to
the 128 KiB mempool cap — never leaves the database. The SQL prefilter
carries every invariant that is exactly expressible there, so a paid junk
payload (a valid ``aitbc_msg`` object beside a giant sibling key, or an
obviously-broken envelope) never reaches Python at all:

- ``aitbc_msg`` is a JSON object
- ``v`` is the JSON *integer* 1 (``json_type='integer'`` rejects ``1.0``,
  ``"1"`` and ``true`` exactly as ``envelope_error`` does)
- ``kind`` is text in {post, reply}
- ``topic`` is a *canonical* slug: text, 1–64 chars of ``[a-z0-9._-]``,
  alnum first/last, no ``--`` run — exactly what
  ``t == normalize_topic(t)`` accepts
- ``body`` is text of 1–4096 UTF-8 bytes (``length(CAST(x AS BLOB))``)
- ``agent_address`` is text (the canonical-address *comparison* stays in
  Python — ``canonical_address`` is case-lenient and must not be tightened
  by a SQL string compare)

Text envelope fields are fetched as ``CAST(json_extract(...) AS BLOB)`` and
strict-UTF-8-decoded in Python — ``json_extract`` alone would hand the
driver undecodable text for a lone-surrogate value (``"a\\ud800"``) and turn
every read into a 500; the byte form defers the verdict to the predicate,
where it belongs.

The SQL prefilter only *narrows*; it is never stricter than the predicate.
``envelope_error`` remains the final arbiter on the survivors — charset,
control characters, parent shape and the canonical author comparison live
in Python only. ``SCAN_BOUND`` stays as a second safety net.

Aggregates (``list_topics``, ``state``) are computed by SQL ``GROUP BY`` /
``count`` over the prefiltered set (F2) — exact for the rules SQL expresses
above. The documented residual: a row that passes the narrowing but fails a
Python-only rule (author canonicality, control characters, lone-surrogate
bytes, parent shape) is counted until a materialized index exists. It can
still never *surface* as a listed message.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import LargeBinary, and_, cast, func, not_, or_
from sqlmodel import col, select

from aitbc.messaging import (
    MAX_MESSAGE_BODY_BYTES,
    MAX_TOPIC_CHARS,
    MSG_KINDS,
    MSG_NAMESPACE,
    MSG_VERSION,
    envelope_error,
    extract_envelope,
)

from .base_models import _to_ait_address
from .models import Block, Transaction

#: Read-path bounds (public routes). A page never returns more than
#: MAX_READ_LIMIT items; every message-list request scans at most
#: SCAN_BOUND candidate rows; aggregates are SQL-side and unbounded.
MAX_READ_LIMIT = 100
DEFAULT_READ_LIMIT = 50
MAX_OFFSET = 500
SCAN_BOUND = 8192

_HEX64 = set("0123456789abcdef")


def _env_json(path: str):
    """``json_extract(payload, '$.aitbc_msg.<path>')``."""
    return func.json_extract(col(Transaction.payload), f"$.{MSG_NAMESPACE}.{path}")


def _env_text(path: str):
    """Envelope field as raw bytes (BLOB) — never decoded by the driver."""
    return cast(_env_json(path), LargeBinary)


def _decode_env_bytes(raw: Any) -> Any:
    """Strict UTF-8 decode of a BLOB-selected envelope field.

    Bytes that fail to decode (a lone surrogate stored as WTF-8, other
    malformed sequences) return the raw ``bytes`` — the predicate sees a
    non-str field and rejects the row, which is the same verdict the
    whole-payload path produced.
    """
    if raw is None or isinstance(raw, str):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            return bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            return bytes(raw)
    return raw


def _env_from_row(row: Any) -> dict[str, Any]:
    """Rebuild the envelope dict from the selected columns.

    ``v`` is pinned by the SQL narrowing to JSON integer ``MSG_VERSION``;
    the other fields arrive verbatim (BLOB-decoded). ``envelope_error``
    reads exactly these keys and ignores extras, so the verdict is identical
    to running it on the original payload.
    """
    env: dict[str, Any] = {
        "v": MSG_VERSION,
        "kind": _decode_env_bytes(row.env_kind),
        "topic": _decode_env_bytes(row.env_topic),
        "body": _decode_env_bytes(row.env_body),
        "agent_address": _decode_env_bytes(row.env_agent_address),
    }
    parent = _decode_env_bytes(row.env_parent)
    if parent is not None:
        env["parent"] = parent
    return env


def _row_error(row: Any) -> str | None:
    """Predicate call on a column row, with a last-resort guard: anything that
    makes the predicate *raise* is invalid, never an exception. One hostile
    sealed row must not be able to break a read for everyone."""
    try:
        return envelope_error(_env_from_row(row), sender=row.sender or "")
    except Exception as e:
        return f"invalid aitbc_msg envelope ({type(e).__name__})"


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
    try:
        return envelope_error(extract_envelope(payload), sender=sender or "")
    except Exception as e:
        return f"invalid aitbc_msg envelope ({type(e).__name__})"


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


def _candidate_where(chain_id: str):
    """The shared SQL narrowing — every condition exactly mirrors a rule
    ``envelope_error`` also enforces, so a valid row can never be narrowed
    out. Python-only checks stay out of here by design."""
    payload = col(Transaction.payload)
    ns = f"$.{MSG_NAMESPACE}"
    return (
        col(Transaction.chain_id) == chain_id,
        col(Transaction.type) == "MESSAGE",
        col(Transaction.block_height).is_not(None),
        func.json_type(payload, ns) == "object",
        # v must be the JSON integer 1 — json_type alone rejects
        # 1.0 (real), "1" (text) and true/false (true/false) exactly as
        # the predicate's isinstance-int check does.
        func.json_type(payload, f"{ns}.v") == "integer",
        _env_json("v") == MSG_VERSION,
        func.json_type(payload, f"{ns}.kind") == "text",
        _env_json("kind").in_(sorted(MSG_KINDS)),
        func.json_type(payload, f"{ns}.topic") == "text",
        # Canonical slug, exactly: 1-64 chars of [a-z0-9._-], alnum first
        # and last, no "--" run (normalize_topic collapses doubles). This
        # is `topic == normalize_topic(topic)` expressed in SQL.
        func.length(_env_json("topic")).between(1, MAX_TOPIC_CHARS),
        not_(_env_json("topic").op("GLOB")("*[^a-z0-9._-]*")),
        func.substr(_env_json("topic"), 1, 1).op("GLOB")("[a-z0-9]"),
        func.substr(_env_json("topic"), -1, 1).op("GLOB")("[a-z0-9]"),
        func.instr(_env_json("topic"), "--") == 0,
        func.json_type(payload, f"{ns}.body") == "text",
        func.length(_env_text("body")).between(1, MAX_MESSAGE_BODY_BYTES),
        func.json_type(payload, f"{ns}.agent_address") == "text",
        # `parent` is deliberately not narrowed: for `post` it must be
        # absent/null and for `reply` a 64-hex string — the predicate's
        # shape check stays in Python either way.
    )


def _candidate_columns():
    """Columns every message read needs — never the payload blob itself."""
    return [
        col(Transaction.id),
        col(Transaction.tx_hash),
        col(Transaction.block_height),
        col(Transaction.sender),
        col(Transaction.timestamp),
        col(Transaction.fee),
        _env_text("kind").label("env_kind"),
        _env_text("topic").label("env_topic"),
        _env_text("parent").label("env_parent"),
        _env_text("agent_address").label("env_agent_address"),
        _env_text("body").label("env_body"),
    ]


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
        select(*_candidate_columns())
        .where(*_candidate_where(chain_id))
        .order_by(col(Transaction.block_height).desc(), col(Transaction.id).desc())
    )
    if topic is not None:
        stmt = stmt.where(_env_json("topic") == topic)
    if author is not None:
        # sender is stored verbatim (signed bytes); the two legal spellings
        # differ only in casing (EIP-55 / lowercase).
        stmt = stmt.where(func.lower(col(Transaction.sender)) == author.lower())
    if body_contains is not None:
        stmt = stmt.where(_env_json("body").like(f"%{_like_escape(body_contains)}%", escape="\\"))
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
) -> tuple[list[Any], str | None, bool]:
    """Walk candidates newest-first, returning up to ``limit`` *valid* rows.

    Returns ``(rows, next_cursor, scan_bounded)``:

    - ``next_cursor`` resumes after the last returned row when the page is
      full, or after the last scanned row when the bound cut the scan short
      (junk never wedges a reader: the cursor always advances).
    - ``scan_bounded`` reports that the scan bound cut the scan — the page is
      short and more candidates may exist beyond the cursor.
    """
    rows = session.exec(_apply_cursor(stmt, cursor).limit(scan_bound + 1)).all()
    out: list[Any] = []
    last_scanned: Any | None = None
    for row in rows[:scan_bound]:
        last_scanned = row
        if _row_error(row) is not None:
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
    stmt = _candidate_select(chain_id).where(col(Transaction.tx_hash).in_(parents))
    for row in session.exec(stmt).all():
        if _row_error(row) is None:
            resolved.add(row.tx_hash)
    for m in items:
        if m.get("parent"):
            m["parent_resolved"] = m["parent"] in resolved


def _view(row: Any) -> dict[str, Any]:
    env = _env_from_row(row)
    sender = _to_ait_address(row.sender)
    view: dict[str, Any] = {
        "message_id": row.tx_hash,
        "tx_hash": row.tx_hash,
        "block_height": row.block_height,
        "author": sender,
        "sender": sender,
        "topic": env.get("topic"),
        "kind": env.get("kind"),
        "body": env.get("body"),
        "parent": env.get("parent"),
        "timestamp": row.timestamp,
        "fee": row.fee,
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
    items = [_view(row) for row in rows[offset:]]
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
    stmt = _candidate_select(chain_id).where(col(Transaction.tx_hash) == tx_hash)
    row = session.exec(stmt).first()
    if row is None or _row_error(row) is not None:
        return None
    view = _view(row)
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
        if _row_error(row) is not None:
            continue
        topic = _decode_env_bytes(row.env_topic)
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
        if _row_error(row) is not None:
            continue
        messages += 1
        topics.add(_decode_env_bytes(row.env_topic))
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
