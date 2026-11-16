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

import copy
import threading
from collections import OrderedDict
from types import SimpleNamespace
from typing import Any
import typing

from sqlalchemy import LargeBinary, cast, func
from sqlalchemy import select as sa_select
from sqlmodel import col, select

from aitbc.messaging import (
    DM_KINDS,
    DM_TOPIC,
    POST_KINDS,
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

#: Max literals per ``IN (...)`` in ``_standing_votes`` — far inside
#: SQLite's variable limit (999 on old builds, 32766 on new).
_VOTE_TARGET_CHUNK = 500

#: Defensive cap on the authority fixpoint passes; each changing pass adds
#: at least one member, so convergence is way below this in practice. A hit
#: raises rather than truncating.
AUTHORITY_PASSES_CAP = 64

_MOD_EFFECT_KINDS = frozenset({"hide", "unhide", "pin", "unpin", "lock", "unlock"})
_GRANT_KINDS = frozenset({"mod_grant", "mod_revoke"})


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


def _walk_locked_subtree(children: dict[str, list[str]], root: str, intervals: list[list], out: dict[str, list[list]]) -> None:
    """BFS one root, accumulating its intervals onto each descendant —
    a descendant of several locked roots carries all their intervals.
    Replies beyond LOCK_WALK_LIMIT are treated as outside the lock
    (fail-open)."""
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
                out.setdefault(child, []).extend(list(iv) for iv in intervals)
                nxt.append(child)
                walked += 1
        frontier = nxt


# -- Read-cost cache (MSG-2b) -------------------------------------------------
# Moderation state and locked-descendant maps are pure derivations of the
# sealed rows, so they can be cached per (chain, topic, index head). The head
# *hash* is part of the key: a replaced block at the same height (fork heal)
# changes it and therefore misses. Memory-only, bounded LRU, thread-safe;
# callers always get a deep copy so cached state can never be mutated through
# a returned object.

_MOD_CACHE_SIZE = 256
_MOD_CACHE_LOCK = threading.Lock()
_MOD_CACHE: OrderedDict[tuple[str, str, str, int, str], Any] = OrderedDict()


def _index_head(session, chain_id: str) -> tuple[int, str]:
    """(height, block hash) of the index head — the cache-key component."""
    row = session.exec(
        select(col(Block.height), col(Block.hash))
        .where(col(Block.chain_id) == chain_id)
        .order_by(col(Block.height).desc())
        .limit(1)
    ).first()
    if row is None:
        return 0, ""
    return int(row[0]), str(row[1])


def _mod_cache_get(key: tuple[str, str, str, int, str]) -> Any:
    with _MOD_CACHE_LOCK:
        hit = _MOD_CACHE.get(key)
        if hit is not None:
            _MOD_CACHE.move_to_end(key)
            return copy.deepcopy(hit)
    return None


def _mod_cache_put(key: tuple[str, str, str, int, str], value: Any) -> Any:
    with _MOD_CACHE_LOCK:
        _MOD_CACHE[key] = value
        _MOD_CACHE.move_to_end(key)
        while len(_MOD_CACHE) > _MOD_CACHE_SIZE:
            _MOD_CACHE.popitem(last=False)
    return copy.deepcopy(value)


def _cached_moderation_state(session, chain_id: str, topic: str) -> _ModState:
    h, head_hash = _index_head(session, chain_id)
    key = ("mod", chain_id, topic, h, head_hash)
    hit = _mod_cache_get(key)
    if hit is not None:
        return typing.cast(_ModState, hit)
    return typing.cast(_ModState, _mod_cache_put(key, moderation_state(session, chain_id, topic)))


def _cached_locked_descendants(
    session, chain_id: str, topic: str, root_intervals: dict[str, list[list]]
) -> dict[str, list[list]]:
    if not root_intervals:
        return {}
    h, head_hash = _index_head(session, chain_id)
    key = ("desc", chain_id, topic, h, head_hash)
    hit = _mod_cache_get(key)
    if hit is not None:
        return typing.cast(dict[str, list[list]], hit)
    return typing.cast(
        dict[str, list[list]], _mod_cache_put(key, _locked_descendants(session, chain_id, topic, root_intervals))
    )


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
    # A vote only counts in the topic it claims; a wrong-topic vote is a
    # sealed no-op (§4). Partitioning by the claimed topic as well keeps
    # such a row in its own partition — it can never take the newest slot
    # and silently retract the voter's valid vote on the same target.
    v_topic = _env_text("topic")
    rn = func.row_number().over(
        partition_by=(voter, v_target, v_topic),
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
            v_topic.label("env_topic"),
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
        stmt = stmt.where(inner.c.v_target.in_([_bare_hash(t) for t in targets]))
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
    topic_of = {_bare_hash(m["tx_hash"]): str(m.get("topic")) for m in items}
    for _signer, target, v, vtopic in votes:
        if vtopic == topic_of.get(target):
            per.setdefault(target, []).append(v)
    for m in items:
        vals = per.get(_bare_hash(m["tx_hash"]), [])
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
    st = _cached_moderation_state(session, chain_id, topic)
    hidden = _hidden_map(st)
    pinned = _pinned_map(st)
    descendants = _cached_locked_descendants(session, chain_id, topic, _root_lock_intervals(st))
    msgs: list[dict[str, Any]] = []
    pins: list[dict[str, Any]] = []
    for m in items:
        pos = (int(m["block_height"]), str(m["tx_hash"]).lower())
        mkey = _bare_hash(m["tx_hash"])
        h = hidden.get(mkey)
        m["hidden"] = h is not None
        m["hidden_by"] = {"action_tx_hash": h[0], "moderator": h[1], "block_height": h[2][0]} if h else None
        after_lock = _in_interval(pos, st.topic_intervals) or (mkey in descendants and _in_interval(pos, descendants[mkey]))
        m["after_lock"] = bool(after_lock)
        p = pinned.get(mkey)
        m["pinned"] = p is not None
        m["pinned_by"] = {"action_tx_hash": p[0], "moderator": p[1], "block_height": p[2][0]} if p else None
        if m.get("parent"):
            m["parent_hidden"] = _bare_hash(m["parent"]) in hidden
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
    st = _cached_moderation_state(session, chain_id, canonical)
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
    # Chunk the IN(...) list: one literal per target would hit SQLite's
    # variable limit for a prolific author (500 at a time is far inside
    # the 999/32766 bounds). Chunks are disjoint on target, so merging
    # standing-vote rows keeps the result exact — no truncation.
    votes: list[tuple[str, str, int, str]] = []
    for i in range(0, len(targets) or 1, _VOTE_TARGET_CHUNK):
        votes.extend(_standing_votes(session, chain_id, targets=targets[i : i + _VOTE_TARGET_CHUNK] or ["\x00"]))
    topic_of = {_bare_hash(r.tx_hash): _decode_env_bytes(r.env_topic) for r in authored}
    per: dict[str, list[tuple[str, int]]] = {}
    for signer, target, v, vtopic in votes:
        if vtopic == topic_of.get(target):
            per.setdefault(target, []).append((signer, v))
    total = 0
    counted = 0
    for r in authored:
        vals = [(s, v) for s, v in per.get(_bare_hash(r.tx_hash), []) if s != address.lower()]
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


# -- MSG-8: encrypted direct messages -----------------------------------------
# The index stores and serves ciphertext only — no plaintext, no keys. The
# `dm` slug is reserved for the DM kinds (enforced bidirectionally by the
# predicate and by the branch-level topic rules in _candidate_where), so a
# single check — kind + slug — is the whole carve-out: DM rows are invisible
# to topics/messages/state/search reads because they are never POST_KINDS,
# and they surface only through the two functions below.


def is_dm_row(env: dict[str, Any]) -> bool:
    """The one DM carve-out predicate: envelope is a DM row iff its kind is a
    DM kind *and* it sits on the reserved slug (the admission rule, mirrored
    for reads)."""
    return env.get("kind") in DM_KINDS and env.get("topic") == DM_TOPIC


def _dm_view(row: Any) -> dict[str, Any]:
    env = _env_from_row(row)
    return {
        "tx_hash": row.tx_hash,
        "block_height": row.block_height,
        "sender": _to_ait_address(row.sender),
        "to": env.get("to"),
        "ct": env.get("ct"),
        "kind": env.get("kind"),
    }


def dm_inbox(
    session,
    chain_id: str,
    address: str,
    *,
    limit: int = DEFAULT_READ_LIMIT,
    cursor: str | None = None,
) -> dict[str, Any]:
    """The recipient's DM inbox: valid ``dm`` rows with ``to == address``,
    newest-first under the same ``<height>:<tx_hash>`` cursor shape."""
    limit = max(1, min(int(limit), MAX_READ_LIMIT))
    parsed = parse_cursor(cursor)
    stmt = _candidate_select(chain_id).where(
        _env_json("kind") == "dm",
        func.lower(_env_json("to")) == address.lower(),
    )
    rows, next_cursor, bounded = _scan_valid(session, stmt, cursor=parsed, limit=limit, scan_bound=SCAN_BOUND)
    return {
        "success": True,
        "chain_id": chain_id,
        "index_height": _index_height(session, chain_id),
        "messages": [_dm_view(r) for r in rows],
        "count": len(rows),
        "next_cursor": next_cursor,
        "scan_bounded": bounded,
    }


def latest_dm_key(session, chain_id: str, address: str) -> dict[str, Any] | None:
    """The newest valid ``dm_key`` published by ``address``, or ``None``.

    Latest wins in ``(block_height, tx_hash)`` order — rotation is a fresh
    envelope. Invalid rows never count (same predicate arbiter as the rest
    of the index).
    """
    stmt = _candidate_select(chain_id).where(
        _env_json("kind") == "dm_key",
        func.lower(_env_json("agent_address")) == address.lower(),
    )
    cursor: tuple[int, str] | None = None
    while True:
        # _scan_valid's cursor always advances past junk, so a hostile run of
        # invalid dm_key rows can never hide a valid earlier key.
        rows, next_cursor, _bounded = _scan_valid(session, stmt, cursor=cursor, limit=1, scan_bound=SCAN_BOUND)
        if rows:
            row = rows[0]
            env = _env_from_row(row)
            return {
                "address": _canonical(row.sender),
                "enc_pubkey": env.get("enc_pubkey"),
                "tx_hash": row.tx_hash,
                "block_height": row.block_height,
            }
        if next_cursor is None:
            return None
        cursor = parse_cursor(next_cursor)


# -- Split helpers -------------------------------------------------------------
# The query/scan and moderation-derivation helpers live in
# ``messaging_index_query``; every name is re-exported here so
# ``aitbc_chain.messaging_index.<name>`` keeps resolving (and staying
# monkeypatchable) exactly as it did when this was a single module.
from .messaging_index_query import (  # noqa: F401
    _CURSOR_HASH_RE,
    _ModState,
    _apply_cursor,
    _apply_mod_effect,
    _asc_after,
    _asc_select,
    _bare_hash,
    _block_timestamps,
    _candidate_columns,
    _candidate_select,
    _candidate_where,
    _canonical,
    _decode_env_bytes,
    _env_from_row,
    _env_json,
    _env_text,
    _advance_moderators,
    _grant_pass,
    _hidden_map,
    _in_interval,
    _index_height,
    _iter_valid_asc,
    _like_escape,
    _locked_descendants,
    _member_signed_stmt,
    _moderators_at_pos,
    _pinned_map,
    _pos,
    _record_lock_interval,
    _resolve_parents,
    _root_lock_intervals,
    _row_error,
    _scan_valid,
    _target_where,
    _tx_hash_bare,
    _view,
    admission_error,
    get_message,
    list_messages,
    list_topics,
    parse_cursor,
    state,
    topic_founder,
)


def __getattr__(name: str):
    """Resolve any other previously-importable name against the helper module.

    Keeps collaborator names that moved with the helpers (``func``,
    ``envelope_error``, ``canonical_address`` …) importable from
    ``aitbc_chain.messaging_index`` exactly as before the split.
    """
    from . import messaging_index_query as _helpers

    try:
        return getattr(_helpers, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
