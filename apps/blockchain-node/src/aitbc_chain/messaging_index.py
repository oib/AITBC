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

import re
from types import SimpleNamespace
from typing import Any

from sqlalchemy import LargeBinary, and_, cast, column, desc, func, not_, or_
from sqlalchemy import select as sa_select
from sqlmodel import col, select

from aitbc.messaging import (
    ACTION_KINDS,
    MAX_MESSAGE_BODY_BYTES,
    MAX_TOPIC_CHARS,
    MSG_KINDS,
    MSG_NAMESPACE,
    MSG_VERSION,
    POST_KINDS,
    VOTE_VALUES,
    envelope_error,
    extract_envelope,
)
from aitbc.crypto.signature_recovery import canonical_address

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
    to running it on the original payload. MSG-2 action fields are included
    when present.
    """
    env: dict[str, Any] = {
        "v": MSG_VERSION,
        "kind": _decode_env_bytes(row.env_kind),
        "topic": _decode_env_bytes(row.env_topic),
        "agent_address": _decode_env_bytes(row.env_agent_address),
    }
    body = _decode_env_bytes(row.env_body)
    if body is not None:
        env["body"] = body
    parent = _decode_env_bytes(row.env_parent)
    if parent is not None:
        env["parent"] = parent
    target = _decode_env_bytes(row.env_target)
    if target is not None:
        env["target"] = target
    if getattr(row, "env_value", None) is not None:
        env["value"] = row.env_value
    grantee = _decode_env_bytes(row.env_grantee)
    if grantee is not None:
        env["grantee"] = grantee
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


_CURSOR_HASH_RE = re.compile(r"[0-9a-fA-F]{64}")


def parse_cursor(cursor: str | None) -> tuple[int, str] | None:
    """Parse a ``<block_height>:<tx_hash>`` keyset cursor, or ``None``.

    The tx_hash half is the deterministic in-block tiebreaker (F3):
    ``Transaction.id`` was a node-local autoincrement, so cursors and
    same-block ordering differed between nodes. Stored tx_hash values are
    lowercase hex (``_validate_hex``); a cursor echoes one back and is
    normalised the same way for the comparison.
    """
    if not cursor:
        return None
    try:
        height_s, hash_s = cursor.split(":", 1)
        height = int(height_s)
    except (ValueError, AttributeError):
        height = -1
        hash_s = ""
    if height < 0 or not _CURSOR_HASH_RE.fullmatch(hash_s or ""):
        raise ValueError("invalid cursor (want '<block_height>:<tx_hash>' from a previous next_cursor)")
    return height, hash_s.lower()


def _like_escape(text: str) -> str:
    """Escape LIKE metacharacters for a literal substring match (escape '\\')."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _index_height(session, chain_id: str) -> int:
    head = session.exec(select(func.max(Block.height)).where(col(Block.chain_id) == chain_id)).first()
    return int(head) if head is not None else 0


def _target_where():
    """``target`` is a 64-hex text — the predicate's shape rule in SQL."""
    payload = col(Transaction.payload)
    ns = f"$.{MSG_NAMESPACE}"
    return and_(
        func.json_type(payload, f"{ns}.target") == "text",
        func.length(_env_json("target")) == 64,
        not_(_env_json("target").op("GLOB")("*[^0-9a-fA-F]*")),
    )


def _candidate_where(chain_id: str):
    """The shared SQL narrowing — every condition exactly mirrors a rule
    ``envelope_error`` also enforces, so a valid row can never be narrowed
    out. Python-only checks stay out of here by design. MSG-2: the kind
    set is per-kind — post/reply carry the body+parent rules, action kinds
    carry their own required fields, and the branches are OR'd."""
    payload = col(Transaction.payload)
    ns = f"$.{MSG_NAMESPACE}"
    common = and_(
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
        # length(), GLOB, substr and instr all stop reading at an embedded
        # NUL: "a\x00<junk>" would pass every check below while the Python
        # canonicality predicate rejects it — and pure-SQL aggregates fetch
        # no rows, so the junk would be minted as a topic name. Byte length
        # equals char length exactly when the text is NUL-free ASCII; any
        # non-ASCII char is rejected by the charset glob anyway.
        func.length(_env_json("topic")) == func.length(_env_text("topic")),
        not_(_env_json("topic").op("GLOB")("*[^a-z0-9._-]*")),
        func.substr(_env_json("topic"), 1, 1).op("GLOB")("[a-z0-9]"),
        func.substr(_env_json("topic"), -1, 1).op("GLOB")("[a-z0-9]"),
        func.instr(_env_json("topic"), "--") == 0,
        func.json_type(payload, f"{ns}.agent_address") == "text",
    )
    post_branch = and_(
        _env_json("kind").in_(sorted(POST_KINDS)),
        func.json_type(payload, f"{ns}.body") == "text",
        func.length(_env_text("body")).between(1, MAX_MESSAGE_BODY_BYTES),
        # `parent` shape, exactly as the predicate decides it: a post has no
        # parent at all (absent or JSON null), a reply has a 64-hex text.
        or_(
            and_(_env_json("kind") == "post", _env_json("parent").is_(None)),
            and_(
                _env_json("kind") == "reply",
                func.json_type(payload, f"{ns}.parent") == "text",
                func.length(_env_json("parent")) == 64,
                not_(_env_json("parent").op("GLOB")("*[^0-9a-fA-F]*")),
            ),
        ),
    )
    vote_branch = and_(
        _env_json("kind") == "vote",
        _target_where(),
        func.json_type(payload, f"{ns}.value") == "integer",
        _env_json("value").in_(sorted(VOTE_VALUES)),
    )
    targeted_branch = and_(
        _env_json("kind").in_(["hide", "unhide", "pin", "unpin"]),
        _target_where(),
    )
    lock_branch = and_(
        _env_json("kind").in_(["lock", "unlock"]),
        # absent target = whole topic; a present one must be a tx hash.
        or_(_env_json("target").is_(None), _target_where()),
    )
    grant_branch = and_(
        _env_json("kind").in_(["mod_grant", "mod_revoke"]),
        func.json_type(payload, f"{ns}.grantee") == "text",
        func.length(_env_json("grantee")) >= 1,
    )
    return (common, or_(post_branch, vote_branch, targeted_branch, lock_branch, grant_branch))


def _candidate_columns():
    """Columns every message read needs — never the payload blob itself."""
    return [
        col(Transaction.tx_hash),
        col(Transaction.block_height),
        col(Transaction.sender),
        col(Transaction.fee),
        _env_text("kind").label("env_kind"),
        _env_text("topic").label("env_topic"),
        _env_text("parent").label("env_parent"),
        _env_text("agent_address").label("env_agent_address"),
        _env_text("body").label("env_body"),
        _env_text("target").label("env_target"),
        _env_json("value").label("env_value"),
        _env_text("grantee").label("env_grantee"),
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
        .order_by(col(Transaction.block_height).desc(), col(Transaction.tx_hash).desc())
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


def _apply_cursor(stmt, cursor: tuple[int, str] | None):
    """Keyset filter for DESC (block_height, tx_hash) ordering."""
    if cursor is None:
        return stmt
    height, tx_hash = cursor
    return stmt.where(
        or_(
            col(Transaction.block_height) < height,
            and_(col(Transaction.block_height) == height, col(Transaction.tx_hash) < tx_hash),
        )
    )


def _scan_valid(
    session,
    stmt,
    *,
    cursor: tuple[int, str] | None,
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
            return out, f"{row.block_height}:{row.tx_hash}", False
    # Page not full. More candidates may exist iff the bound+1 fetch overshot.
    if len(rows) > scan_bound and last_scanned is not None:
        return out, f"{last_scanned.block_height}:{last_scanned.tx_hash}", True
    return out, None, False


def _resolve_parents(session, chain_id: str, items: list[dict[str, Any]]) -> None:
    """Set ``parent_resolved`` on reply views (batched lookup).

    A parent resolves to a sealed transaction row that is itself a valid
    forum message (any kind). Unresolvable parents stay indexed — the flag is
    what the reader shows, not a drop.
    """
    parents = {m["parent"].lower() for m in items if m.get("parent")}
    if not parents:
        return
    resolved: set[str] = set()
    stmt = _candidate_select(chain_id).where(
        func.lower(col(Transaction.tx_hash)).in_(parents), _env_json("kind").in_(sorted(POST_KINDS))
    )
    for row in session.exec(stmt).all():
        if _row_error(row) is None:
            resolved.add(row.tx_hash.lower())
    for m in items:
        if m.get("parent"):
            m["parent_resolved"] = m["parent"].lower() in resolved


def _view(row: Any, block_times: dict[int, Any]) -> dict[str, Any]:
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
        # F5: the block's timestamp, not Transaction.timestamp — the only
        # clock value all nodes agree on (the row's is nullable and may be
        # submitter-set).
        "timestamp": block_times.get(row.block_height),
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
    include_hidden: bool = False,
) -> dict[str, Any]:
    """Page forum messages newest-first. ``topic`` is the canonical slug.

    Only ``post``/``reply`` rows surface — MSG-2 action kinds are filtered
    here even though the shared narrowing admits them. Hidden and
    after-lock rows drop out of the default view (``include_hidden``
    returns them flagged, body withheld); pinned rows are returned in a
    separate ``pinned`` list so canonical order — and cursors — stay
    monotone (director amendment).
    """
    limit = max(1, min(int(limit), MAX_READ_LIMIT))
    offset = max(0, min(int(offset), MAX_OFFSET))
    parsed = parse_cursor(cursor)
    stmt = _candidate_select(chain_id, topic=topic, author=author, body_contains=body_contains).where(
        _env_json("kind").in_(sorted(POST_KINDS))
    )
    rows, next_cursor, bounded = _scan_valid(session, stmt, cursor=parsed, limit=limit + offset, scan_bound=SCAN_BOUND)
    times = _block_timestamps(session, chain_id, (r.block_height for r in rows[offset:]))
    items = [_view(row, times) for row in rows[offset:]]
    _resolve_parents(session, chain_id, items)
    _score_fields(session, chain_id, items)
    # Moderation is topic-scoped: group the page by topic and derive once
    # per topic.
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for m in items:
        by_topic.setdefault(str(m.get("topic") or ""), []).append(m)
    visible: list[dict[str, Any]] = []
    pinned: list[dict[str, Any]] = []
    for t, group in by_topic.items():
        msgs, pins = _moderation_fields(session, chain_id, t, group, include_hidden=include_hidden)
        visible.extend(msgs)
        pinned.extend(pins)
    visible.sort(key=lambda m: (int(m["block_height"]), str(m["tx_hash"]).lower()), reverse=True)
    pinned.sort(key=lambda m: (int(m["block_height"]), str(m["tx_hash"]).lower()), reverse=True)
    return {
        "success": True,
        "chain_id": chain_id,
        "index_height": _index_height(session, chain_id),
        "messages": visible,
        "pinned": pinned,
        "count": len(visible),
        "next_cursor": next_cursor,
        "scan_bounded": bounded,
    }


def get_message(session, chain_id: str, tx_hash: str, *, include_hidden: bool = False) -> dict[str, Any] | None:
    """One message by its tx_hash; ``None`` when absent or not a valid message.

    Stored tx_hash values are lowercase hex; a caller-supplied uppercase or
    mixed-case hash names the same row. A hidden message still resolves (the
    row exists) — it returns with ``hidden: true``, ``hidden_by`` and
    ``body: null``; the body stays fetchable as the raw transaction, per §3
    of the design note.
    """
    stmt = _candidate_select(chain_id).where(
        col(Transaction.tx_hash) == tx_hash.lower(), _env_json("kind").in_(sorted(POST_KINDS))
    )
    row = session.exec(stmt).first()
    if row is None or _row_error(row) is not None:
        return None
    view = _view(row, _block_timestamps(session, chain_id, [row.block_height]))
    _resolve_parents(session, chain_id, [view])
    _score_fields(session, chain_id, [view])
    msgs, pins = _moderation_fields(session, chain_id, str(view.get("topic") or ""), [view], include_hidden=True)
    if not msgs and not pins:
        return None  # unreachable: include_hidden always returns the row
    for out in (*msgs, *pins):
        if out.get("tx_hash") == view["tx_hash"]:
            return out
    return view


def _block_timestamps(session, chain_id: str, heights: Any) -> dict[int, Any]:
    """``height -> Block.timestamp`` for the given heights (one IN query)."""
    uniq = {int(h) for h in heights if h is not None}
    if not uniq:
        return {}
    rows = session.exec(
        select(Block.height, Block.timestamp).where(
            col(Block.chain_id) == chain_id,
            col(Block.height).in_(uniq),
        )
    ).all()
    return {h: (ts.isoformat() if hasattr(ts, "isoformat") else ts) for h, ts in rows}


def list_topics(
    session,
    chain_id: str,
    *,
    limit: int = DEFAULT_READ_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Topics ranked by last activity — SQL ``GROUP BY`` over the prefiltered
    set (F2). Counts are exact for every rule SQL expresses; the documented
    residual is a row that passes the narrowing but fails a Python-only rule
    (canonical author comparison, body control characters, malformed UTF-8
    bytes) — it is *counted* until a materialized index exists, though it can
    never appear as a listed message. ``scan_bounded`` stays ``False``: no
    scan bound applies to aggregate queries any more.

    ``last_timestamp`` is the timestamp of the block at ``last_block_height``
    — the only clock value every node agrees on (``Transaction.timestamp`` is
    nullable and may be submitter-set).
    """
    limit = max(1, min(int(limit), MAX_READ_LIMIT))
    offset = max(0, min(int(offset), MAX_OFFSET))
    topic_expr = _env_json("topic").label("topic")
    stmt = (
        select(
            topic_expr,
            func.count().label("message_count"),
            func.max(col(Transaction.block_height)).label("last_block_height"),
        )
        .where(*_candidate_where(chain_id), _env_json("kind").in_(sorted(POST_KINDS)))
        .group_by(topic_expr)
        .order_by(desc("last_block_height"), column("topic"))
    )
    rows = session.exec(stmt).all()
    page_rows = rows[offset : offset + limit]
    times = _block_timestamps(session, chain_id, (r.last_block_height for r in page_rows))
    topics = []
    for r in page_rows:
        st = moderation_state(session, chain_id, r.topic)
        hidden = _hidden_map(st)
        pinned = _pinned_map(st)
        locked = st.topic_lock is not None and st.topic_lock[0] == "lock"
        topics.append(
            {
                "topic": r.topic,
                "message_count": r.message_count,
                "last_block_height": r.last_block_height,
                "last_timestamp": times.get(r.last_block_height),
                "founder": st.founder,
                "moderators": sorted(st.moderators),
                "authority_unresolved": st.authority_unresolved,
                "hidden_count": len(hidden),
                "pinned_count": len(pinned),
                "locked": locked,
            }
        )
    return {
        "success": True,
        "chain_id": chain_id,
        "index_height": _index_height(session, chain_id),
        "topics": topics,
        "count": len(topics),
        "total_topics": len(rows),
        "scan_bounded": False,
    }


def state(session, chain_id: str) -> dict[str, Any]:
    """Totals for the legacy ``/messaging/state`` route — SQL aggregates over
    the prefiltered set (F2; same residual rules as :func:`list_topics`).
    ``total_agents`` counts distinct senders (case-collapsed); ``sender`` is
    the verified identity — ``agent_address`` equality is a Python-only rule
    and therefore part of the documented residual for counts."""
    row = session.exec(
        select(
            func.count().label("total_messages"),
            func.count(func.distinct(_env_json("topic"))).label("total_topics"),
            func.count(func.distinct(func.lower(col(Transaction.sender)))).label("total_agents"),
        ).where(*_candidate_where(chain_id), _env_json("kind").in_(sorted(POST_KINDS)))
    ).first()
    actions = session.exec(
        select(func.count()).where(*_candidate_where(chain_id), _env_json("kind").in_(sorted(ACTION_KINDS)))
    ).first()
    totals = {
        "total_messages": row.total_messages if row else 0,
        "total_topics": row.total_topics if row else 0,
        "total_agents": row.total_agents if row else 0,
        "total_actions": int(actions) if actions else 0,
    }
    return {
        "success": True,
        "chain_id": chain_id,
        "index_height": _index_height(session, chain_id),
        "contract_state": totals,
        "scan_bounded": False,
    }


# -- MSG-2: votes, moderation, reputation ------------------------------------
# Everything below derives from the same sealed `transaction` rows, in the
# canonical (block_height, tx_hash) order — the F3 order. Authority is a
# fixpoint over moderator-signed grant/revoke rows; standing votes are an
# exact SQL window aggregate; nothing truncates silently. See
# docs/design/msg2-votes-moderation.md.

#: Reputation clamp per message (§5 of the design note). Display-only.
VOTE_CAP = 20

#: Bound on the descendant walk for a subtree lock; replies beyond it are
#: treated as outside the locked subtree (fail-open, stated in the note).
LOCK_WALK_LIMIT = 512

#: Defensive cap on the authority fixpoint passes; each changing pass adds
#: at least one member, so convergence is way below this in practice. A hit
#: raises rather than truncating.
AUTHORITY_PASSES_CAP = 64

_MOD_EFFECT_KINDS = frozenset({"hide", "unhide", "pin", "unpin", "lock", "unlock"})
_GRANT_KINDS = frozenset({"mod_grant", "mod_revoke"})


def _pos(row: Any) -> tuple[int, str]:
    return (int(row.block_height), str(row.tx_hash).lower())


def _asc_after(stmt, pos: tuple[int, str] | None):
    """Keyset filter for ASC (block_height, tx_hash) ordering."""
    if pos is None:
        return stmt
    height, tx_hash = pos
    return stmt.where(
        or_(
            col(Transaction.block_height) > height,
            and_(col(Transaction.block_height) == height, col(Transaction.tx_hash) > tx_hash),
        )
    )


def _asc_select(chain_id: str, topic: str | None = None):
    """Candidate select in canonical ASCENDING order (no pre-set ordering)."""
    stmt = select(*_candidate_columns()).where(*_candidate_where(chain_id))
    if topic is not None:
        stmt = stmt.where(_env_json("topic") == topic)
    return stmt.order_by(col(Transaction.block_height).asc(), col(Transaction.tx_hash).asc())


def _iter_valid_asc(session, stmt, *, before: tuple[int, str] | None = None, page: int = 512):
    """Yield predicate-valid rows in canonical ascending order, keyset-paged.

    ``before`` is an exclusive (height, tx_hash) position bound — an action
    never sees its own effects. No silent truncation: the generator pages
    until the query is exhausted. ``stmt`` must come from ``_asc_select``.
    """
    cursor: tuple[int, str] | None = None
    while True:
        rows = session.exec(_asc_after(stmt, cursor).limit(page)).all()
        if not rows:
            return
        for row in rows:
            cursor = _pos(row)
            if before is not None and cursor >= before:
                return
            if _row_error(row) is not None:
                continue
            yield row
        if len(rows) < page:
            return


def _canonical(sender: str | None) -> str:
    try:
        return canonical_address(sender or "")
    except Exception:
        return (sender or "").lower()


def topic_founder(session, chain_id: str, topic: str) -> str | None:
    """Signer (canonical) of the topic's first valid post/reply, or None."""
    stmt = _asc_select(chain_id, topic).where(_env_json("kind").in_(sorted(POST_KINDS)))
    for row in _iter_valid_asc(session, stmt):
        return _canonical(row.sender)
    return None


class _ModState:
    """Derived moderation state for one topic (see the design note §2/§3)."""

    def __init__(self) -> None:
        self.founder: str | None = None
        self.moderators: set[str] = set()
        self.ever_moderators: set[str] = set()
        # Effective grant/revoke events in canonical order:
        # (pos, signer, kind, grantee).
        self.grant_events: list[tuple[tuple[int, str], str, str, str]] = []
        # Latest effective action wins *per category* — a pin must not
        # overwrite a hide on the same target:
        #   hidden:       target -> (action_tx_hash, moderator, pos)
        #   pinned:       target -> (action_tx_hash, moderator, pos)
        #   thread_locks: target -> (action_tx_hash, moderator, pos)
        self.hidden: dict[str, tuple[str, str, tuple[int, str]]] = {}
        self.pinned: dict[str, tuple[str, str, tuple[int, str]]] = {}
        self.thread_locks: dict[str, tuple[str, str, tuple[int, str]]] = {}
        # Latest effective topic lock/unlock: (kind, action_tx_hash, moderator, pos)
        self.topic_lock: tuple[str, str, str, tuple[int, str]] | None = None
        # True when the authority fixpoint hit AUTHORITY_PASSES_CAP without
        # converging. The route reports it and answers best-effort — it must
        # never 500, or a long grant chain could break reads on a topic.
        self.authority_unresolved = False
        # All evaluated actions, canonical order, for the audit route.
        self.actions: list[dict[str, Any]] = []


def _moderators_at_pos(st: _ModState, pos: tuple[int, str]) -> set[str]:
    """Moderator set strictly before ``pos`` — replay the grant timeline."""
    mods = {st.founder} if st.founder else set()
    for epos, _signer, kind, grantee in st.grant_events:
        if epos >= pos:
            break
        if kind == "mod_grant":
            mods.add(grantee)
        elif len(mods) > 1:  # a revoke that would empty the set is ineffective
            mods.discard(grantee)
    return mods


def _member_signed_stmt(chain_id: str, topic: str, kinds: frozenset[str], signers: set[str]):
    """Action rows of ``kinds`` signed by anyone in ``signers`` (ever- or
    current-moderators), in canonical order. ``["\x00"]`` keeps the IN
    clause non-empty when the set is empty."""
    return (
        _asc_select(chain_id, topic)
        .where(_env_json("kind").in_(sorted(kinds)))
        .where(func.lower(col(Transaction.sender)).in_([m.lower() for m in signers] or ["\x00"]))
    )


def _grant_pass(session, stmt, founder: str | None):
    """One authority pass: apply member-signed grant/revoke rows in
    canonical order. Returns ``(final_moderator_set, effective_events)``."""
    mods: set[str] = {founder} if founder else set()
    events: list[tuple[tuple[int, str], str, str, str]] = []
    for row in _iter_valid_asc(session, stmt):
        signer = _canonical(row.sender)
        if signer not in mods:
            continue
        env = _env_from_row(row)
        kind = env.get("kind")
        try:
            grantee = canonical_address(env.get("grantee") or "", strict=True)
        except Exception:
            continue
        if kind == "mod_grant" and grantee not in mods:
            mods.add(grantee)
            events.append((_pos(row), signer, kind, grantee))
        elif kind == "mod_revoke" and grantee in mods and len(mods) > 1:
            mods.discard(grantee)
            events.append((_pos(row), signer, kind, grantee))
    return mods, events


def _advance_moderators(
    mods_now: set[str], grant_events: list[tuple[tuple[int, str], str, str, str]], grant_idx: int, pos: tuple[int, str]
) -> int:
    """Replay the grant timeline up to ``pos`` (exclusive); returns the new
    index into ``grant_events``."""
    while grant_idx < len(grant_events) and grant_events[grant_idx][0] < pos:
        _epos, _signer, gkind, grantee = grant_events[grant_idx]
        if gkind == "mod_grant":
            mods_now.add(grantee)
        elif len(mods_now) > 1:
            mods_now.discard(grantee)
        grant_idx += 1
    return grant_idx


def _apply_mod_effect(st: _ModState, kind: Any, target: Any, entry: tuple[str, str, tuple[int, str]]) -> None:
    """Apply one effective action: hide/pin/lock are independent
    latest-per-category state — a pin must not erase a hide (§3)."""
    if kind in {"lock", "unlock"}:
        if target is None:
            st.topic_lock = (kind, *entry)
        elif kind == "lock":
            st.thread_locks[str(target).lower()] = entry
        else:
            st.thread_locks.pop(str(target).lower(), None)
        return
    state = {"hide": st.hidden, "unhide": st.hidden, "pin": st.pinned, "unpin": st.pinned}[kind]
    if kind in {"unhide", "unpin"}:
        state.pop(str(target).lower(), None)
    else:
        state[str(target).lower()] = entry


def moderation_state(session, chain_id: str, topic: str) -> _ModState:
    """Full derived moderation state for a topic.

    Phase A (authority): the moderator set is a fixpoint — fetch
    grant/revoke rows signed by *current* members, apply them in canonical
    order, repeat until the set stops changing. Non-member spam never
    enters the scan.
    Phase B (effects): hide/pin/lock rows signed by ever-moderators are
    applied in canonical order, each judged by the moderator set at its
    own position (replaying the grant timeline).
    """
    st = _ModState()
    st.founder = topic_founder(session, chain_id, topic)
    if st.founder:
        st.ever_moderators = {st.founder}

    # Phase A — fixpoint over ever-moderator-signed grant/revoke rows. The
    # fetch set is everyone who has EVER held moderation (founder + effective
    # grantees): it grows monotonically, so it converges, and it still
    # excludes never-member spam entirely. (Fetching by the *current* set
    # instead would oscillate when a grantee later revokes the founder —
    # the founder's grant row would drop out of the scan.)
    for _pass in range(AUTHORITY_PASSES_CAP):
        stmt = _member_signed_stmt(chain_id, topic, _GRANT_KINDS, st.ever_moderators)
        st.moderators, st.grant_events = _grant_pass(session, stmt, st.founder)
        new_ever = st.ever_moderators | {g for _p, _s, k, g in st.grant_events if k == "mod_grant"}
        if new_ever == st.ever_moderators:
            break
        st.ever_moderators = new_ever
    else:
        # Cap tripped: report it and answer best-effort from the last pass
        # rather than failing the whole read path.
        st.authority_unresolved = True

    # Phase B — moderation effects by ever-moderators, judged at position.
    stmt = _member_signed_stmt(chain_id, topic, _MOD_EFFECT_KINDS, st.ever_moderators)
    grant_idx = 0
    mods_now: set[str] = {st.founder} if st.founder else set()
    for row in _iter_valid_asc(session, stmt):
        pos = _pos(row)
        grant_idx = _advance_moderators(mods_now, st.grant_events, grant_idx, pos)
        signer = _canonical(row.sender)
        env = _env_from_row(row)
        kind = env.get("kind")
        target = env.get("target")
        effective = signer in mods_now
        if effective:
            _apply_mod_effect(st, kind, target, (row.tx_hash, signer, pos))
        st.actions.append(
            {
                "tx_hash": row.tx_hash,
                "block_height": row.block_height,
                "kind": kind,
                "signer": signer,
                "target": target,
                "effective": effective,
            }
        )
    return st


def _locked_roots(st: _ModState) -> dict[str, tuple[int, str]]:
    """Locked thread roots -> lock position (latest effective wins)."""
    return {t: (h, m, pos)[2] for t, (h, m, pos) in st.thread_locks.items()}


def _hidden_map(st: _ModState) -> dict[str, tuple[str, str, tuple[int, str]]]:
    """target -> (action_tx_hash, moderator, pos) for currently-hidden rows."""
    return dict(st.hidden)


def _pinned_map(st: _ModState) -> dict[str, tuple[str, str, tuple[int, str]]]:
    return dict(st.pinned)


def _locked_descendants(
    session, chain_id: str, topic: str, locked_roots: dict[str, tuple[int, str]]
) -> dict[str, tuple[int, str]]:
    """tx_hash -> lock pos for replies inside a locked subtree.

    BFS from each locked root over the topic's reply graph, bounded at
    LOCK_WALK_LIMIT descendants per root (fail-open per the design note).
    """
    if not locked_roots:
        return {}
    children: dict[str, list[str]] = {}
    stmt = _asc_select(chain_id, topic).where(_env_json("kind") == "reply", _env_json("parent").is_not(None))
    for row in _iter_valid_asc(session, stmt):
        parent = _decode_env_bytes(row.env_parent)
        if isinstance(parent, str):
            children.setdefault(parent.lower(), []).append(str(row.tx_hash).lower())
    out: dict[str, tuple[int, str]] = {}
    for root, lock_pos in locked_roots.items():
        _walk_locked_subtree(children, root.lower(), lock_pos, out)
    return out


def _walk_locked_subtree(
    children: dict[str, list[str]], root: str, lock_pos: tuple[int, str], out: dict[str, tuple[int, str]]
) -> None:
    """BFS one locked root; replies beyond LOCK_WALK_LIMIT are treated as
    outside the lock (fail-open)."""
    frontier = [root]
    seen = {root}
    walked = 0
    while frontier and walked < LOCK_WALK_LIMIT:
        nxt: list[str] = []
        for node in frontier:
            for child in children.get(node, []):
                if child in seen or walked >= LOCK_WALK_LIMIT:
                    continue
                seen.add(child)
                out[child] = lock_pos
                nxt.append(child)
                walked += 1
        frontier = nxt


def _standing_votes(session, chain_id: str, *, targets: list[str] | None = None, topic: str | None = None):
    """Exact standing votes — SQL window, last-in-canonical-order wins.

    Returns ``{(signer_lower, target_lower): value}`` over predicate-valid
    ``vote`` rows (value != 0 retracts are excluded). Computed with
    ``ROW_NUMBER() OVER (PARTITION BY signer, target ORDER BY height DESC,
    tx_hash DESC)`` — exact, no scan bound, per the director's amendment.
    """
    voter = func.lower(col(Transaction.sender)).label("voter")
    v_target = func.lower(_env_json("target")).label("v_target")
    v_value = _env_json("value").label("v_value")
    rn = func.row_number().over(
        partition_by=(voter, v_target),
        order_by=(col(Transaction.block_height).desc(), col(Transaction.tx_hash).desc()),
    )
    inner = (
        sa_select(
            col(Transaction.tx_hash),
            col(Transaction.block_height),
            col(Transaction.sender),
            voter,
            v_target,
            v_value,
            _env_text("kind").label("env_kind"),
            _env_text("topic").label("env_topic"),
            _env_text("parent").label("env_parent"),
            _env_text("agent_address").label("env_agent_address"),
            _env_text("body").label("env_body"),
            _env_text("target").label("env_target"),
            _env_text("grantee").label("env_grantee"),
            _env_json("value").label("env_value"),
            rn.label("rn"),
        )
        .where(*_candidate_where(chain_id), _env_json("kind") == "vote")
        .subquery()
    )
    stmt = sa_select(inner).where(inner.c.rn == 1, inner.c.v_value != 0)
    if targets:
        stmt = stmt.where(inner.c.v_target.in_([t.lower() for t in targets]))
    if topic is not None:
        stmt = stmt.where(inner.c.env_topic == cast(topic.encode(), LargeBinary))
    out: list[tuple[str, str, int, str]] = []
    for mapping in session.execute(stmt).mappings().all():
        row = SimpleNamespace(**dict(mapping))
        if _row_error(row) is not None:
            continue
        vtopic = _decode_env_bytes(row.env_topic)
        out.append((str(row.voter).lower(), str(row.v_target).lower(), int(row.v_value), str(vtopic)))
    return out


def _score_fields(session, chain_id: str, items: list[dict[str, Any]]) -> None:
    """Attach score/upvotes/downvotes/voter_count to message views.

    A vote only counts when its claimed ``topic`` equals the target's real
    topic — a vote naming a different topic is a sealed no-op (§4).
    """
    targets = [m["tx_hash"] for m in items]
    votes = _standing_votes(session, chain_id, targets=targets)
    per: dict[str, list[int]] = {}
    topic_of = {str(m["tx_hash"]).lower(): str(m.get("topic")) for m in items}
    for _signer, target, v, vtopic in votes:
        if vtopic == topic_of.get(target):
            per.setdefault(target, []).append(v)
    for m in items:
        vals = per.get(str(m["tx_hash"]).lower(), [])
        up = sum(1 for v in vals if v > 0)
        down = sum(1 for v in vals if v < 0)
        m["score"] = up - down
        m["upvotes"] = up
        m["downvotes"] = down
        m["voter_count"] = len(vals)


def _moderation_fields(
    session,
    chain_id: str,
    topic: str,
    items: list[dict[str, Any]],
    *,
    include_hidden: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply hide/pin/lock derivation to a topic's message views.

    Returns ``(messages, pinned)`` — pinned rows are a separate list so the
    main list keeps canonical order and cursors stay monotone. Hidden and
    after-lock rows drop out of the default view; with ``include_hidden``
    they are returned flagged, body withheld.
    """
    st = moderation_state(session, chain_id, topic)
    hidden = _hidden_map(st)
    pinned = _pinned_map(st)
    locked_roots = _locked_roots(st)
    descendants = _locked_descendants(session, chain_id, topic, locked_roots)
    msgs: list[dict[str, Any]] = []
    pins: list[dict[str, Any]] = []
    for m in items:
        pos = (int(m["block_height"]), str(m["tx_hash"]).lower())
        h = hidden.get(str(m["tx_hash"]).lower())
        m["hidden"] = h is not None
        m["hidden_by"] = {"action_tx_hash": h[0], "moderator": h[1], "block_height": h[2][0]} if h else None
        after_lock = (st.topic_lock is not None and st.topic_lock[0] == "lock" and pos > st.topic_lock[3]) or (
            str(m["tx_hash"]).lower() in descendants and pos > descendants[str(m["tx_hash"]).lower()]
        )
        m["after_lock"] = bool(after_lock)
        p = pinned.get(str(m["tx_hash"]).lower())
        m["pinned"] = p is not None
        m["pinned_by"] = {"action_tx_hash": p[0], "moderator": p[1], "block_height": p[2][0]} if p else None
        if m.get("parent"):
            m["parent_hidden"] = str(m["parent"]).lower() in hidden
        suppress = m["hidden"] or m["after_lock"]
        if suppress and not include_hidden:
            continue
        if suppress:
            m["body"] = None
        (pins if m["pinned"] else msgs).append(m)
    return msgs, pins


def message_votes(session, chain_id: str, tx_hash: str) -> dict[str, Any]:
    """Standing votes for one message — exact SQL aggregate."""
    view = get_message(session, chain_id, tx_hash, include_hidden=True)
    author = (view or {}).get("author")
    real_topic = (view or {}).get("topic")
    votes = [
        (s, v)
        for s, _t, v, vtopic in _standing_votes(session, chain_id, targets=[tx_hash])
        if real_topic is not None and vtopic == real_topic
    ]
    rows = [
        {"voter": signer, "value": v, "self_vote": bool(author) and signer == str(author).lower()}
        for signer, v in sorted(votes)
    ]
    return {
        "success": True,
        "chain_id": chain_id,
        "index_height": _index_height(session, chain_id),
        "tx_hash": tx_hash,
        "votes": rows,
        "count": len(rows),
        "scan_bounded": False,
    }


def topic_moderation(session, chain_id: str, topic: str) -> dict[str, Any] | None:
    """Moderator set + locks + recent actions for one topic. None if no topic."""
    canonical = topic
    st = moderation_state(session, chain_id, canonical)
    if st.founder is None:
        return None
    hidden = _hidden_map(st)
    pinned = _pinned_map(st)
    locked = st.topic_lock is not None and st.topic_lock[0] == "lock"
    return {
        "success": True,
        "chain_id": chain_id,
        "index_height": _index_height(session, chain_id),
        "topic": canonical,
        "founder": st.founder,
        "moderators": sorted(st.moderators),
        "authority_unresolved": st.authority_unresolved,
        "locked": locked,
        "locked_by": (
            {"action_tx_hash": st.topic_lock[1], "moderator": st.topic_lock[2], "block_height": st.topic_lock[3][0]}
            if locked and st.topic_lock
            else None
        ),
        "hidden_count": len(hidden),
        "pinned": sorted(pinned.keys()),
        "actions": st.actions[-100:],
    }


def reputation(session, chain_id: str, address: str) -> dict[str, Any]:
    """Integer reputation for an address — pure function of chain data.

    ``rep(a) = Σ_m clamp(up(m) − down(m), ±VOTE_CAP)`` over the author's
    valid messages, standing votes only, self-votes excluded (§5).
    Display-only; feeds no authority.
    """
    stmt = _asc_select(chain_id).where(func.lower(col(Transaction.sender)) == address.lower())
    authored = [r for r in _iter_valid_asc(session, stmt) if _decode_env_bytes(r.env_kind) in POST_KINDS]
    targets = [str(r.tx_hash) for r in authored]
    votes = _standing_votes(session, chain_id, targets=targets or ["\x00"])
    topic_of = {str(r.tx_hash).lower(): _decode_env_bytes(r.env_topic) for r in authored}
    per: dict[str, list[tuple[str, int]]] = {}
    for signer, target, v, vtopic in votes:
        if vtopic == topic_of.get(target):
            per.setdefault(target, []).append((signer, v))
    total = 0
    counted = 0
    for r in authored:
        vals = [(s, v) for s, v in per.get(str(r.tx_hash).lower(), []) if s != address.lower()]
        if not vals:
            continue
        counted += 1
        up = sum(1 for _s, v in vals if v > 0)
        down = sum(1 for _s, v in vals if v < 0)
        total += max(-VOTE_CAP, min(VOTE_CAP, up - down))
    return {
        "success": True,
        "chain_id": chain_id,
        "index_height": _index_height(session, chain_id),
        "address": address,
        "reputation": total,
        "messages_authored": len(authored),
        "messages_counted": counted,
        "vote_cap": VOTE_CAP,
    }
