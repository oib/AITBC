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
    """The index's ordering key: ``(block_height, tx_hash)``, newest last."""
    return (int(message.get("block_height") or 0), str(message.get("tx_hash") or "").lower())


def parse_seen_cursor(cursor: str | None) -> tuple[int, str] | None:
    """``<height>:<tx_hash>`` resume token, or ``None``."""
    if not cursor:
        return None
    try:
        h, _, hsh = cursor.partition(":")
        return (int(h), hsh.lower().removeprefix("0x"))
    except (ValueError, AttributeError):
        return None


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
    """
    seen = parse_seen_cursor(from_cursor)
    first = True
    polls = 0
    while max_polls is None or polls < max_polls:
        polls += 1
        data = fetch_messages(rpc_url, topic=topic, limit=limit, timeout=timeout)
        if isinstance(data, dict):
            rows = list(data.get("messages") or [])
            rows.sort(key=message_sort_key)
            if first and seen is None and rows:
                # Start at the head: emit nothing historical.
                seen = message_sort_key(rows[-1])
            elif seen is None and rows:
                seen = message_sort_key(rows[-1])
            for row in rows:
                if seen is not None and message_sort_key(row) > seen:
                    seen = message_sort_key(row)
                    yield row
        first = False
        sleep(interval)
