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

from sqlalchemy import func
from sqlmodel import col

from aitbc.messaging import (
    DM_KINDS,
    DM_TOPIC,
    POST_KINDS,
)

from .base_models import _to_ait_address
from .models import Transaction

# The query/scan and moderation-derivation helpers live in
# ``messaging_index_query``; every name is re-exported here so
# ``aitbc_chain.messaging_index.<name>`` keeps resolving exactly as it did
# when this was a single module. The helper owns the read-path bounds and
# the whole moderation/vote derivation so it has no dependency back on this
# module — ``import aitbc_chain.messaging_index_query`` works standalone in
# either import order. This import sits at the top (not the bottom) because
# ``DEFAULT_READ_LIMIT`` etc. are used as default-argument values below.
from .messaging_index_query import (  # noqa: F401
    DEFAULT_READ_LIMIT,
    MAX_OFFSET,
    MAX_READ_LIMIT,
    SCAN_BOUND,
    AUTHORITY_PASSES_CAP,
    LOCK_WALK_LIMIT,
    _CURSOR_HASH_RE,
    _GRANT_KINDS,
    _MOD_CACHE,
    _MOD_CACHE_LOCK,
    _MOD_CACHE_SIZE,
    _MOD_EFFECT_KINDS,
    _ModState,
    _VOTE_TARGET_CHUNK,
    _apply_cursor,
    _apply_mod_effect,
    _asc_after,
    _asc_select,
    _bare_hash,
    _block_timestamps,
    _cached_locked_descendants,
    _cached_moderation_state,
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
    _index_head,
    _index_height,
    _in_interval,
    _iter_valid_asc,
    _like_escape,
    _locked_descendants,
    _member_signed_stmt,
    _moderation_fields,
    _moderators_at_pos,
    _mod_cache_get,
    _mod_cache_put,
    _pinned_map,
    _pos,
    _record_lock_interval,
    _resolve_parents,
    _root_lock_intervals,
    _row_error,
    _scan_valid,
    _score_fields,
    _standing_votes,
    _target_where,
    _tx_hash_bare,
    _view,
    _walk_locked_subtree,
    admission_error,
    get_message,
    list_messages,
    list_topics,
    moderation_state,
    parse_cursor,
    state,
    topic_founder,
)

_HEX64 = set("0123456789abcdef")


# -- MSG-2: votes, moderation, reputation ------------------------------------
# Everything below derives from the same sealed `transaction` rows, in the
# canonical (block_height, tx_hash) order — the F3 order. Authority is a
# fixpoint over moderator-signed grant/revoke rows; standing votes are an
# exact SQL window aggregate; nothing truncates silently. See
# docs/design/msg2-votes-moderation.md.

#: Reputation clamp per message (§5 of the design note). Display-only.
VOTE_CAP = 20


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
# ``messaging_index_query`` names are re-exported via the import at the top of
# this module; ``__getattr__`` below resolves any other previously-importable
# name against the helper module.


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
