"""Public read routes for on-chain forum messages (MSG-1).

Data comes from the derived index in ``aitbc_chain.messaging_index`` — a
bounded, predicate-filtered query over the ``transaction`` table. These
handlers are bound twice: under the canonical ``/rpc/messaging/*`` paths and
as the legacy ``/rpc/contracts/messaging/*`` aliases the generated MCP tools
still call.

Posting is not an RPC operation: a message is a signed ``MESSAGE``
transaction submitted through ``/rpc/transaction`` (``aitbc messaging
send``). The mutation routes under ``/rpc/contracts/messaging/*`` return 501
pointing here.
"""

import functools
from typing import Any

from fastapi import HTTPException, Request

from aitbc.messaging import MIN_SEARCH_CHARS, normalize_topic
from aitbc.rate_limiting import rate_limit

from ..database import session_scope
from ..logger import get_logger
from ..messaging_metrics import collect_gauges, note_read, note_read_client_error, note_read_error
from ..messaging_index import (
    MAX_OFFSET,
    MAX_READ_LIMIT,
    dm_inbox,
    get_message,
    latest_dm_key,
    list_messages,
    list_topics,
    message_votes,
    parse_cursor,
    reputation,
    state,
    topic_moderation,
)
from .utils import get_chain_id

_logger = get_logger(__name__)


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), MAX_READ_LIMIT))


def _check_cursor(cursor: str | None) -> None:
    if cursor:
        try:
            parse_cursor(cursor)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e


def _observed(route: str):
    """MSG-6: count each read and each failed read (4xx/5xx) per route.

    Applied to the shared handlers, so the canonical and legacy mounts count
    under the same route label.
    """

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                result = await fn(*args, **kwargs)
            except HTTPException as e:
                if e.status_code >= 500:
                    note_read_error(route)
                else:
                    note_read_client_error(route)  # routine 404/400, no alert
                raise
            except Exception:
                note_read_error(route)
                raise
            note_read(route)
            return result

        return wrapper

    return deco


@rate_limit(rate=200, per=60)
@_observed("state")
async def messaging_state(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Forum totals derived from the chain, plus the index height."""
    resolved = get_chain_id(chain_id)
    with session_scope(resolved) as session:
        return state(session, resolved)


@rate_limit(rate=200, per=60)
@_observed("stats")
async def messaging_stats(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """MSG-6 operability snapshot: index height and lag, message/action
    totals, and the checkpoint digest of the derived index for cross-node
    comparison."""
    resolved = get_chain_id(chain_id)

    def _collect() -> dict[str, Any]:
        # Off the event loop like the /metrics hook: a cold checkpoint
        # digest over ~100k envelopes takes tens of seconds.
        with session_scope(resolved) as session:
            return collect_gauges(session, resolved)

    from starlette.concurrency import run_in_threadpool

    result = await run_in_threadpool(_collect)
    result["success"] = True
    return result


@rate_limit(rate=200, per=60)
@_observed("topics")
async def messaging_topics(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    chain_id: str | None = None,
) -> dict[str, Any]:
    """Topics ranked by last activity. Implicit — first post creates them."""
    if offset < 0 or offset > MAX_OFFSET:
        raise HTTPException(status_code=400, detail=f"offset must be 0..{MAX_OFFSET}")
    resolved = get_chain_id(chain_id)
    with session_scope(resolved) as session:
        return list_topics(session, resolved, limit=_clamp_limit(limit), offset=offset)


@rate_limit(rate=200, per=60)
@_observed("messages")
async def messaging_messages(
    request: Request,
    topic: str | None = None,
    author: str | None = None,
    limit: int = 50,
    offset: int = 0,
    cursor: str | None = None,
    include_hidden: bool = False,
    chain_id: str | None = None,
) -> dict[str, Any]:
    """Page messages newest-first. ``cursor`` takes a previous next_cursor.

    ``include_hidden=1`` returns hidden/after-lock rows flagged
    (``hidden``/``hidden_by``/``after_lock``) with the body withheld —
    moderation is a read-side filter, the bytes stay on-chain (MSG-2 §3).
    """
    if offset < 0 or offset > MAX_OFFSET:
        raise HTTPException(status_code=400, detail=f"offset must be 0..{MAX_OFFSET}")
    _check_cursor(cursor)
    canonical_topic: str | None = None
    if topic is not None:
        canonical_topic = normalize_topic(topic)
        if canonical_topic is None:
            raise HTTPException(status_code=400, detail=f"topic '{topic}' is not a valid slug")
    resolved = get_chain_id(chain_id)
    with session_scope(resolved) as session:
        return list_messages(
            session,
            resolved,
            topic=canonical_topic,
            author=author,
            limit=_clamp_limit(limit),
            offset=offset,
            cursor=cursor,
            include_hidden=include_hidden,
        )


@rate_limit(rate=200, per=60)
@_observed("votes")
async def messaging_votes(request: Request, tx_hash: str, chain_id: str | None = None) -> dict[str, Any]:
    """Standing votes for one message (exact SQL aggregate, MSG-2)."""
    resolved = get_chain_id(chain_id)
    with session_scope(resolved) as session:
        return message_votes(session, resolved, tx_hash)


@rate_limit(rate=200, per=60)
@_observed("moderation")
async def messaging_moderation(request: Request, slug: str, chain_id: str | None = None) -> dict[str, Any]:
    """Derived moderator set, locks and recent actions for a topic (MSG-2)."""
    canonical = normalize_topic(slug)
    if canonical is None:
        raise HTTPException(status_code=400, detail=f"topic '{slug}' is not a valid slug")
    resolved = get_chain_id(chain_id)
    with session_scope(resolved) as session:
        result = topic_moderation(session, resolved, canonical)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No topic '{canonical}'")
    return result


@rate_limit(rate=200, per=60)
@_observed("reputation")
async def messaging_reputation(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Integer reputation derived from sealed votes (display-only, MSG-2)."""
    resolved = get_chain_id(chain_id)
    with session_scope(resolved) as session:
        return reputation(session, resolved, address)


@rate_limit(rate=200, per=60)
@_observed("get")
async def messaging_get(request: Request, tx_hash: str, chain_id: str | None = None) -> dict[str, Any]:
    """One message by its transaction hash; 404 when it is not a forum message."""
    resolved = get_chain_id(chain_id)
    with session_scope(resolved) as session:
        view = get_message(session, resolved, tx_hash)
    if view is None:
        raise HTTPException(status_code=404, detail=f"No forum message {tx_hash}")
    view["success"] = True
    view["chain_id"] = resolved
    return view


@rate_limit(rate=200, per=60)
@_observed("search")
async def messaging_search(
    request: Request,
    query: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    cursor: str | None = None,
    chain_id: str | None = None,
) -> dict[str, Any]:
    """Literal substring search over message bodies (LIKE metachars escaped)."""
    text = (q if q is not None else query) or ""
    if len(text.strip()) < MIN_SEARCH_CHARS:
        raise HTTPException(status_code=400, detail=f"query must be at least {MIN_SEARCH_CHARS} characters")
    if offset < 0 or offset > MAX_OFFSET:
        raise HTTPException(status_code=400, detail=f"offset must be 0..{MAX_OFFSET}")
    _check_cursor(cursor)
    resolved = get_chain_id(chain_id)
    with session_scope(resolved) as session:
        result = list_messages(
            session,
            resolved,
            body_contains=text.strip(),
            limit=_clamp_limit(limit),
            offset=offset,
            cursor=cursor,
        )
    result["query"] = text.strip()
    return result


@rate_limit(rate=200, per=60)
@_observed("dm_inbox")
async def messaging_dm_inbox(
    request: Request,
    address: str,
    limit: int = 50,
    cursor: str | None = None,
    chain_id: str | None = None,
) -> dict[str, Any]:
    """The recipient's DM inbox — ciphertext rows only (MSG-8). The node
    never sees plaintext or keys; decryption is client-side."""
    _check_cursor(cursor)
    resolved = get_chain_id(chain_id)
    with session_scope(resolved) as session:
        return dm_inbox(session, resolved, address, limit=_clamp_limit(limit), cursor=cursor)


@rate_limit(rate=200, per=60)
@_observed("dm_key")
async def messaging_dm_key(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """The latest published DM encryption key for an address (MSG-8)."""
    resolved = get_chain_id(chain_id)
    with session_scope(resolved) as session:
        result = latest_dm_key(session, resolved, address)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No dm_key published for {address}")
    result["success"] = True
    result["chain_id"] = resolved
    return result


# -- Legacy `/rpc/contracts/messaging/*` aliases ---------------------------
# The generated MCP HTTP tools (get_forum_topics, get_topic_messages,
# get_messaging_contract_state) call these paths; they keep working.


async def forum_topics(request: Request, limit: int = 50, offset: int = 0, sort_by: str = "last_activity"):
    if sort_by != "last_activity":
        raise HTTPException(status_code=400, detail="only sort_by=last_activity is supported")
    return await messaging_topics(request, limit=limit, offset=offset)


async def forum_topic_messages(request: Request, topic_id: str, limit: int = 50, offset: int = 0, sort_by: str = "timestamp"):
    # topic_id is the slug itself — implicit topics have no separate id space.
    return await messaging_messages(request, topic=topic_id, limit=limit, offset=offset)


async def forum_search(request: Request, query: str, limit: int = 50):
    return await messaging_search(request, query=query, limit=limit)


def _not_implemented(feature: str) -> HTTPException:
    return HTTPException(status_code=501, detail=feature)


def messaging_not_on_chain(feature: str = "messaging via RPC") -> HTTPException:
    """501 for the retired in-memory write paths."""
    return _not_implemented(
        f"{feature} is not an RPC call: post by signing a MESSAGE transaction "
        "(aitbc messaging send / POST /rpc/transaction). No contract is deployed."
    )
