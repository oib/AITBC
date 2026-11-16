"""Query/scan + moderation-derivation helpers for ``messaging_index``.

Extracted verbatim from ``messaging_index.py``: envelope column decoding,
the SQL candidate narrowing, keyset scans, message/topic/state reads, the
canonical-order iteration helpers, the per-topic moderation-state derivation
and the locked-descendant walk. ``messaging_index.py`` re-exports every name
here so ``aitbc_chain.messaging_index.<name>`` keeps resolving exactly as it
did when the package was a single module.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import LargeBinary, and_, cast, column, desc, func, not_, or_
from sqlmodel import col, select

from aitbc.messaging import (
    ACTION_KINDS,
    DM_TOPIC,
    MAX_DM_CT_B64_BYTES,
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
from .messaging_index import (
    DEFAULT_READ_LIMIT,
    MAX_OFFSET,
    MAX_READ_LIMIT,
    SCAN_BOUND,
    _cached_moderation_state,
    _moderation_fields,
    _score_fields,
    _walk_locked_subtree,
)
from .models import Block, Transaction


def _env_json(path: str):
    """``json_extract(payload, '$.aitbc_msg.<path>')``."""
    return func.json_extract(col(Transaction.payload), f"$.{MSG_NAMESPACE}.{path}")


def _env_text(path: str):
    """Envelope field as raw bytes (BLOB) — never decoded by the driver."""
    return cast(_env_json(path), LargeBinary)


def _bare_hash(value: str | None) -> str:
    """Lowercase hash text with any ``0x`` prefix stripped.

    Envelope ``target``/``parent`` fields are bare 64-hex (the codec
    requires exactly 64 chars) while the stored ``tx_hash`` column is
    ``0x``-prefixed. Every join between the two normalizes through here.
    """
    v = (value or "").lower()
    return v[2:] if v.startswith("0x") else v


def _tx_hash_bare():
    """``tx_hash`` normalized to bare lowercase hex, for joins against
    bare-hex envelope fields."""
    return func.lower(func.substr(col(Transaction.tx_hash), -64))


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
    for f in ("to", "ct", "enc_pubkey"):
        v = _decode_env_bytes(getattr(row, f"env_{f}", None))
        if v is not None:
            env[f] = v
    return env


def _row_error(row: Any) -> str | None:
    """Predicate call on a column row, with a last-resort guard: anything that
    makes the predicate *raise* is invalid, never an exception. One hostile
    sealed row must not be able to break a read for everyone."""
    try:
        return envelope_error(_env_from_row(row), sender=row.sender or "")
    except Exception as e:  # noqa: BLE001 - a malformed sealed row must not break reads for everyone
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
    except Exception as e:  # noqa: BLE001 - malformed payload reports invalid, never raises into admission
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
    # MSG-8: the `dm` slug is reserved for the DM kinds and vice versa. Every
    # non-DM branch excludes it so a legacy/squatted `dm`-topic row (sealed
    # before the bidirectional rule existed) can never surface or count; the
    # DM branches require it.
    not_dm_slug = _env_json("topic") != DM_TOPIC
    dm_branch = and_(
        _env_json("kind") == "dm",
        _env_json("topic") == DM_TOPIC,
        func.json_type(payload, f"{ns}.to") == "text",
        func.json_type(payload, f"{ns}.ct") == "text",
        func.length(_env_text("ct")).between(1, MAX_DM_CT_B64_BYTES),
    )
    dm_key_branch = and_(
        _env_json("kind") == "dm_key",
        _env_json("topic") == DM_TOPIC,
        func.json_type(payload, f"{ns}.enc_pubkey") == "text",
    )
    return (
        common,
        or_(
            and_(post_branch, not_dm_slug),
            and_(vote_branch, not_dm_slug),
            and_(targeted_branch, not_dm_slug),
            and_(lock_branch, not_dm_slug),
            and_(grant_branch, not_dm_slug),
            dm_branch,
            dm_key_branch,
        ),
    )


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
        _env_text("to").label("env_to"),
        _env_text("ct").label("env_ct"),
        _env_text("enc_pubkey").label("env_enc_pubkey"),
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
    parents = {_bare_hash(m["parent"]) for m in items if m.get("parent")}
    if not parents:
        return
    resolved: set[str] = set()
    stmt = _candidate_select(chain_id).where(_tx_hash_bare().in_(parents), _env_json("kind").in_(sorted(POST_KINDS)))
    for row in session.exec(stmt).all():
        if _row_error(row) is None:
            resolved.add(_bare_hash(row.tx_hash))
    for m in items:
        if m.get("parent"):
            m["parent_resolved"] = _bare_hash(m["parent"]) in resolved


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
    stmt = _candidate_select(chain_id).where(_tx_hash_bare() == _bare_hash(tx_hash), _env_json("kind").in_(sorted(POST_KINDS)))
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
        st = _cached_moderation_state(session, chain_id, r.topic)
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
    except (AttributeError, TypeError, ValueError):
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
        # Lock intervals (rule (b), MSG-2e): a row sealed while its topic or
        # an ancestor thread was locked keeps ``after_lock`` forever — an
        # unlock only clears rows sealed *after* it. ``[start_pos,
        # end_pos|None]``; open-ended while locked. Ineffective actions
        # (non-moderator at their height) never reach this list.
        self.topic_intervals: list[list] = []
        self.thread_intervals: dict[str, list[list]] = {}
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
        except (AttributeError, TypeError, ValueError):
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


def _record_lock_interval(ivs: list[list], kind: Any, pos: tuple[int, str]) -> None:
    """``lock`` opens ``[pos, None]`` only when no interval is open (a second
    lock while locked must not move the start); ``unlock`` closes the open
    interval and is a no-op when none is."""
    if kind == "lock":
        if not ivs or ivs[-1][1] is not None:
            ivs.append([pos, None])
    elif ivs and ivs[-1][1] is None:
        ivs[-1][1] = pos


def _in_interval(pos: tuple[int, str], ivs: list[list]) -> bool:
    """True when ``pos`` falls inside any ``[start, end|None]`` interval —
    sealed after the lock and, if an unlock closed it, before the unlock."""
    return any(s < pos and (e is None or pos < e) for s, e in ivs)


def _apply_mod_effect(st: _ModState, kind: Any, target: Any, entry: tuple[str, str, tuple[int, str]]) -> None:
    """Apply one effective action: hide/pin/lock are independent
    latest-per-category state — a pin must not erase a hide (§3)."""
    if kind in {"lock", "unlock"}:
        if target is None:
            st.topic_lock = (kind, *entry)
            _record_lock_interval(st.topic_intervals, kind, entry[2])
        else:
            root = str(target).lower()
            if kind == "lock":
                st.thread_locks[root] = entry
            else:
                st.thread_locks.pop(root, None)
            _record_lock_interval(st.thread_intervals.setdefault(root, []), kind, entry[2])
        return
    state = {"hide": st.hidden, "unhide": st.hidden, "pin": st.pinned, "unpin": st.pinned}[kind]
    if kind in {"unhide", "unpin"}:
        state.pop(str(target).lower(), None)
    else:
        state[str(target).lower()] = entry


def _root_lock_intervals(st: _ModState) -> dict[str, list[list]]:
    """Thread roots -> all of their lock intervals (open or closed)."""
    return {t: ivs for t, ivs in st.thread_intervals.items() if ivs}


def _hidden_map(st: _ModState) -> dict[str, tuple[str, str, tuple[int, str]]]:
    """target -> (action_tx_hash, moderator, pos) for currently-hidden rows."""
    return dict(st.hidden)


def _pinned_map(st: _ModState) -> dict[str, tuple[str, str, tuple[int, str]]]:
    return dict(st.pinned)


def _locked_descendants(session, chain_id: str, topic: str, root_intervals: dict[str, list[list]]) -> dict[str, list[list]]:
    """tx_hash -> its root's lock intervals, for replies under a locked root.

    BFS from each root over the topic's reply graph. ``LOCK_WALK_LIMIT``
    bounds descendants walked per root across all of that root's intervals
    (fail-open per the design note) — interval count does not grow the walk.
    """
    if not root_intervals:
        return {}
    children: dict[str, list[str]] = {}
    stmt = _asc_select(chain_id, topic).where(_env_json("kind") == "reply", _env_json("parent").is_not(None))
    for row in _iter_valid_asc(session, stmt):
        parent = _decode_env_bytes(row.env_parent)
        if isinstance(parent, str):
            children.setdefault(_bare_hash(parent), []).append(_bare_hash(row.tx_hash))
    out: dict[str, list[list]] = {}
    for root, intervals in root_intervals.items():
        _walk_locked_subtree(children, _bare_hash(root), intervals, out)
    return out
