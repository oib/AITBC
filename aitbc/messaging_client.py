"""Shared read/wait kernel for the on-chain messaging path (MSG-15).

The chain-backed forum (MSG-1/2/4) is read through the bounded
``/rpc/messaging/*`` routes; posting is a signed ``MESSAGE`` transaction
whose seal must be confirmed on the *messaging* read routes — the generic
``/rpc/transaction/{hash}`` route 404s for MESSAGE transactions even after
they seal (seen live in MSG-3d).

This module holds the transport and detection helpers shared by the CLI
(``cli/aitbc_cli/commands/messaging.py`` — the names are re-imported there
under their historical ``_name`` so its test-suite patch points survive),
the agent SDK (``aitbc_sdk.messaging``) and the MCP tools. It never signs
and never sees wallet material: ``post`` paths take a caller-supplied
submit callable; reads and ``subscribe`` are pure HTTP.

Wire facts (MSG-CLI-HASH-1): read routes take the ``0x``-prefixed tx hash;
stored envelopes carry the bare 64-hex hash — compare after normalising.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

MSG_RPC_PREFIX = "/rpc/messaging"

#: Action kinds whose proof is the resulting *state*, not a row in the
#: moderation ``actions`` list (``vote`` shows on the target's ``/votes``
#: route; ``mod_grant``/``mod_revoke`` show in the topic's ``moderators``).
STATE_ACTION_KINDS = frozenset({"vote", "mod_grant", "mod_revoke"})

#: The six moderation kinds detected by tx hash inside ``actions``.
TX_ACTION_KINDS = frozenset({"hide", "unhide", "pin", "unpin", "lock", "unlock"})

#: Kinds a non-moderator signer can seal but never make effective.
MODERATOR_GATED_KINDS = TX_ACTION_KINDS | {"mod_grant", "mod_revoke"}

#: The moderation ``actions`` list caps at 100 entries — a fresh hash can
#: scroll out under load, so hash waits get a short bound when it reads full.
MODERATION_ACTIONS_CAP = 100

#: Sentinel: transport failed entirely (distinct from "answered 404").
UNREACHABLE = object()


def poll_read(route: str, *, timeout: float = 10.0) -> Any:
    """One GET: parsed JSON on 200, ``None`` on other statuses, ``UNREACHABLE``
    on transport failure. Plain ``requests`` keeps expected 404s away from
    the HTTP client's retry/circuit-breaker machinery."""
    import requests

    try:
        resp = requests.get(route, timeout=timeout)
    except requests.RequestException:
        return UNREACHABLE
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def action_wait_route(base: str, kind: str, topic: str, target: str | None) -> str | None:
    """Read route that proves a messaging action, or ``None`` if none exists."""
    if kind == "vote":
        if target is None:
            return None
        prefixed = target if target.startswith("0x") else f"0x{target}"
        return f"{base}{MSG_RPC_PREFIX}/messages/{prefixed}/votes"
    if kind in STATE_ACTION_KINDS or kind in TX_ACTION_KINDS:
        return f"{base}{MSG_RPC_PREFIX}/topics/{topic}/moderation"
    return None


def action_state_matches(kind: str, data: Any, *, sender: str | None, value: int | None, grantee: str | None) -> bool:
    """True when a state-route body already shows the action's effect."""
    if not isinstance(data, dict):
        return False
    if kind == "vote":
        sender_l = (sender or "").lower()
        if value == 0:
            # A retract removes the signer from the standing votes — absence is the match.
            return sender_l not in {str(v.get("voter", "")).lower() for v in data.get("votes") or []}
        return any(str(v.get("voter", "")).lower() == sender_l and v.get("value") == value for v in data.get("votes") or [])
    mods = {str(m).lower() for m in data.get("moderators") or []}
    grantee_l = (grantee or "").lower()
    if kind == "mod_grant":
        return grantee_l in mods
    if kind == "mod_revoke":
        return grantee_l not in mods
    return False


def action_state_probe(
    rpc_url: str,
    kind: str,
    topic: str,
    target: str | None,
    *,
    sender: str,
    value: int | None,
    grantee: str | None,
) -> bool:
    """One-shot read for state-detected action kinds; False on any error.

    Lets a confirm path say "already matched before this send" instead of
    claiming a seal when the state predates the submission.
    """
    route = action_wait_route(rpc_url.rstrip("/"), kind, topic, target)
    if route is None:
        return False
    data = poll_read(route)
    if data is UNREACHABLE:
        return False
    return action_state_matches(kind, data, sender=sender, value=value, grantee=grantee)


def topic_moderators_probe(rpc_url: str, topic: str) -> set[str] | None:
    """Lowercased moderator set for a topic, or ``None`` when the read failed."""
    data = poll_read(f"{rpc_url.rstrip('/')}{MSG_RPC_PREFIX}/topics/{topic}/moderation")
    if not isinstance(data, dict):
        return None
    return {str(m).lower() for m in data.get("moderators") or []}


def sealed_block(data: Any, want: str, is_action: bool) -> Any:
    """Return the sealed block height from a read-route body, or ``None``.

    ``want`` is the bare lowercase tx hash; stored action hashes may carry
    a ``0x`` prefix (the production layout from MSG-2d onward).
    """
    if not isinstance(data, dict):
        return None
    if not is_action:
        return data.get("block_height")
    for act in data.get("actions") or []:
        if str(act.get("tx_hash", "")).lower().removeprefix("0x") == want:
            return act.get("block_height")
    return None


def wait_hint(is_action: bool, kind: str | None, topic: str, target: str | None, tx_hash: str) -> str:
    """The route or command a user should check after a timed-out wait."""
    if not is_action:
        return f"verify with `aitbc messaging show {tx_hash}`"
    if kind == "vote" and target:
        prefixed = target if target.startswith("0x") else f"0x{target}"
        return f"verify via the target's votes route ({MSG_RPC_PREFIX}/messages/{prefixed}/votes)"
    return f"verify via the topic moderation route ({MSG_RPC_PREFIX}/topics/{topic}/moderation)"


# -- Agent-facing read helpers (SDK/MCP subscribe path) ---------------------


def fetch_messages(
    rpc_url: str,
    *,
    topic: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    timeout: float = 10.0,
) -> Any:
    """One page of the messages index, newest-first.

    Returns the parsed body on 200, ``None`` on a non-200 answer, and
    ``UNREACHABLE`` on transport failure — callers keep those distinct.
    """
    base = rpc_url.rstrip("/")
    url = f"{base}{MSG_RPC_PREFIX}/messages"
    import requests

    params: dict[str, Any] = {"limit": limit}
    if topic is not None:
        params["topic"] = topic
    if cursor is not None:
        params["cursor"] = cursor
    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException:
        return UNREACHABLE
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def fetch_message(rpc_url: str, tx_hash: str, *, timeout: float = 10.0) -> Any:
    """One message by tx hash (bare or ``0x``-prefixed), or ``None``/``UNREACHABLE``."""
    want = tx_hash.lower().removeprefix("0x")
    return poll_read(f"{rpc_url.rstrip('/')}{MSG_RPC_PREFIX}/messages/0x{want}", timeout=timeout)


def message_sort_key(message: dict[str, Any]) -> tuple[int, str]:
    """The index's ordering key: ``(block_height, tx_hash)``, newest last.

    Stored ``tx_hash`` values are ``0x``-prefixed while resume cursors carry
    the bare 64-hex form — both sides normalise to bare lowercase here so a
    ``--from-cursor`` marker compares correctly against same-block rows.
    """
    return (int(message.get("block_height") or 0), str(message.get("tx_hash") or "").lower().removeprefix("0x"))


def parse_seen_cursor(cursor: str | None) -> tuple[int, str] | None:
    """``<height>:<tx_hash>`` resume token, or ``None``."""
    if not cursor:
        return None
    try:
        h, _, hsh = cursor.partition(":")
        return (int(h), hsh.lower().removeprefix("0x"))
    except (ValueError, AttributeError):
        return None


#: Baseline for "the topic was empty when polling started": every row sorts
#: strictly newer, so the first post on a previously-empty topic is delivered
#: instead of becoming the baseline itself.
EMPTY_BASELINE: tuple[int, str] = (-1, "")


class SubscribeGapError(Exception):
    """A resume cursor is further back than the back-page bound can reach.

    Raised instead of silently advancing the cursor past rows that were
    never fetched — the caller must surface the gap, not skip it.
    """


#: Pages of history ``newer_than_cursor`` walks back per poll while looking
#: for the resume cursor (``limit`` rows per page).
SUBSCRIBE_BACK_PAGE_LIMIT = 50


def fetch_topic_page(
    rpc_url: str,
    topic: str,
    *,
    cursor: str | None = None,
    limit: int = 50,
    timeout: float = 10.0,
) -> tuple[list[dict[str, Any]], str | None] | None:
    """One newest-first page of ``topic`` → ``(rows oldest-first, next_cursor)``.

    ``None`` on transport failure or a non-200 answer — callers retry on the
    next poll. ``next_cursor`` pages *older* (the index is DESC).
    """
    data = fetch_messages(rpc_url, topic=topic, cursor=cursor, limit=limit, timeout=timeout)
    if not isinstance(data, dict):
        return None
    rows = sorted((data.get("messages") or []), key=message_sort_key)
    next_cursor = data.get("next_cursor")
    return rows, str(next_cursor) if next_cursor else None


def newer_than_cursor(
    rpc_url: str,
    topic: str,
    seen: tuple[int, str],
    *,
    limit: int = 50,
    timeout: float = 10.0,
    max_back_pages: int = SUBSCRIBE_BACK_PAGE_LIMIT,
) -> list[dict[str, Any]]:
    """All ``topic`` rows strictly newer than ``seen``, oldest-first.

    The index only pages *backwards* from the head, so a resume cursor older
    than one page would otherwise be skipped: this walks ``next_cursor``
    pages back until a row ``<= seen`` or the index start is reached, which
    proves the fetched set is contiguous. Returns ``[]`` when the index
    cannot be read this poll (the caller retries with ``seen`` unchanged —
    nothing is lost). Raises ``SubscribeGapError`` when the back-page bound
    is hit first: rows between ``seen`` and the oldest fetched page may be
    missing and the cursor must not advance past them.
    """
    page = fetch_topic_page(rpc_url, topic, limit=limit, timeout=timeout)
    if page is None:
        return []
    collected, next_cursor = page
    oldest_key = message_sort_key(collected[0]) if collected else None
    back_pages = 0
    while oldest_key is not None and oldest_key > seen and next_cursor and back_pages < max_back_pages:
        page = fetch_topic_page(rpc_url, topic, cursor=next_cursor, limit=limit, timeout=timeout)
        if page is None:
            return []
        older, next_cursor = page
        if not older:
            break
        collected = older + collected
        oldest_key = message_sort_key(older[0])
        back_pages += 1
    if oldest_key is not None and oldest_key > seen and next_cursor:
        raise SubscribeGapError(f"more than {max_back_pages * limit} messages on '{topic}' are newer than the resume cursor")
    return sorted((r for r in collected if message_sort_key(r) > seen), key=message_sort_key)


def subscribe(
    rpc_url: str,
    topic: str,
    *,
    from_cursor: str | None = None,
    interval: float = 5.0,
    max_polls: int | None = None,
    limit: int = 50,
    timeout: float = 10.0,
    sleep=time.sleep,
) -> Iterator[dict[str, Any]]:
    """Yield messages on ``topic`` strictly newer than ``from_cursor``.

    Cursor polling, not push: no chain-messaging event stream is reachable
    from an agent host (the node's ``/rpc/subscribe`` machinery is the
    follower block-sync lease, not a client event API). The newest page is
    polled every ``interval`` seconds; rows newer than the last emitted key
    are yielded oldest-first. ``from_cursor=None`` starts at the current
    index head (no backlog); pass a ``<height>:<tx_hash>`` cursor to resume.
    ``max_polls`` bounds the generator for one-shot consumers; ``None``
    follows forever. Transport failures are skipped silently (the next poll
    retries); the caller decides how long an outage is acceptable.
    ``SubscribeGapError`` propagates when a resume cursor falls outside the
    back-page bound — the gap is reported, never skipped.
    """
    seen = parse_seen_cursor(from_cursor)
    polls = 0
    while max_polls is None or polls < max_polls:
        polls += 1
        if seen is None:
            # First successful read establishes the baseline: the current
            # head, or EMPTY_BASELINE when the topic has no rows yet — an
            # empty topic means everything posted afterwards is new.
            page = fetch_topic_page(rpc_url, topic, limit=limit, timeout=timeout)
            if page is not None:
                rows, _ = page
                seen = message_sort_key(rows[-1]) if rows else EMPTY_BASELINE
        else:
            for row in newer_than_cursor(rpc_url, topic, seen, limit=limit, timeout=timeout):
                seen = message_sort_key(row)
                yield row
        sleep(interval)
