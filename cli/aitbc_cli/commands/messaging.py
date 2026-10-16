"""On-chain forum messaging commands for AITBC CLI (MSG-1).

Forum messages are signed ``MESSAGE`` transactions carrying an
``aitbc_msg`` envelope (see ``aitbc.messaging`` for the wire contract).
There is no RPC post endpoint: this command builds, signs and submits the
transaction itself — the signature is what makes the author real.

WARNING printed on every post: content is public, replicated on every node
and cannot be edited or deleted — moderation (MSG-2) can only ever be a
read-side filter. Agent-to-agent realtime messaging stays with
``aitbc agent-msg``.
"""

import json
import re
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import click

from aitbc.messaging import (
    BROADCAST_TOPIC,
    DM_TOPIC,
    MAX_MESSAGE_BODY_BYTES,
    MIN_SEARCH_CHARS,
    build_envelope,
    normalize_topic,
)
from aitbc.textsafety import sanitize_chain_obj
from aitbc.utils.units import DEFAULT_TX_FEE_AIT

from ..utils import DECIMAL, info, output, success, warning
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError
from ..utils.wallet_paths import find_wallet_file_report, wallet_not_found_message
from ..utils.wallet_secret import resolve_wallet_password, wallet_password_options
from .transactions import _resolve_transaction_rpc_url, _send_transaction_impl

_PERMANENCE_WARNING = (
    "This posts a public, permanent chain transaction: the content is "
    "replicated to every node and cannot be edited or deleted."
)

_WAIT_POLL_SECONDS = 2.0

_TX_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _normalize_tx_hash(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
    """Accept a bare or ``0x``-prefixed 64-hex transaction hash; return the bare form."""
    if value is None:
        return None
    h = value.strip().lower().removeprefix("0x")
    if not _TX_HASH_RE.fullmatch(h):
        raise click.BadParameter("expected 64 hex characters, with or without 0x")
    return h


def _rpc_client(rpc_url: str) -> AITBCHTTPClient:
    """Blockchain-RPC client carrying the configured X-API-Key when present."""
    from ..config import get_config

    return AITBCHTTPClient(base_url=rpc_url, timeout=10, api_key=get_config().blockchain_rpc_api_key)


def _wallet_address(ctx, wallet_name: str) -> str:
    """Sender address from wallet file metadata — no password needed."""
    report = find_wallet_file_report(wallet_name)
    if report.path is None:
        abort(ctx, wallet_not_found_message(report))
    path = cast(Path, report.path)
    try:
        address = json.loads(path.read_text()).get("address")
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure aborts cleanly, never tracebacks
        abort(ctx, f"Wallet '{wallet_name}' unreadable: {e}", from_exception=e)
    if not address:
        abort(ctx, f"Wallet '{wallet_name}' carries no address field")
    return str(address)


# The seal-wait/read detection kernel lives in aitbc.messaging_client (MSG-15)
# so the SDK and MCP share it; it is re-imported under its historical _names —
# the wait tests patch this module's attributes.
from aitbc.messaging_client import (
    MODERATION_ACTIONS_CAP as _MODERATION_ACTIONS_CAP,
    MODERATOR_GATED_KINDS as _MODERATOR_GATED_KINDS,
    STATE_ACTION_KINDS as _STATE_ACTION_KINDS,
    UNREACHABLE as _UNREACHABLE,
)
from aitbc.messaging_client import (
    action_state_matches as _action_state_matches,
    action_state_probe as _action_state_probe,
    action_wait_route as _action_wait_route,
    poll_read as _poll_read,
    sealed_block as _sealed_block,
    topic_moderators_probe as _topic_moderators_probe,
    wait_hint as _wait_hint,
)

_CAPPED_WAIT_SECONDS = 30.0


def _presend_expectations(
    rpc_url: str, kind: str, topic: str, target: str | None, *, sender: str, value: int | None, grantee: str | None
) -> tuple[bool, bool]:
    """One-shot reads for the post-submit wait: ``(pre_matched, expect_listed)``.

    ``pre_matched`` — the state kinds already read as expected (a retract
    with no standing vote counts). ``expect_listed=False`` — a
    moderator-gated kind signed by a non-moderator seals but never takes
    effect, so the wait must not poll for it. ``None`` moderator reads
    leave ``expect_listed`` True (degrade to waiting, not to skipping).
    """
    if kind in _STATE_ACTION_KINDS and _action_state_probe(
        rpc_url, kind, topic, target, sender=sender, value=value, grantee=grantee
    ):
        return True, True
    if kind in _MODERATOR_GATED_KINDS:
        mods = _topic_moderators_probe(rpc_url, topic)
        if mods is not None and sender.lower() not in mods:
            return False, False
    return False, True


def _wait_confirmed(
    data: Any,
    want: str,
    *,
    is_action: bool,
    state_kind: bool,
    kind: str,
    topic: str,
    tx_hash: str,
    sender: str | None,
    value: int | None,
    grantee: str | None,
) -> bool:
    """Print the success line and return True when this poll body confirms the tx."""
    if state_kind:
        if not _action_state_matches(kind, data, sender=sender, value=value, grantee=grantee):
            return False
        if kind == "vote" and value == 0:
            success(f"vote retracted — signer absent from standing votes on '{topic}' (tx {tx_hash})")
        else:
            success(f"'{kind}' reads as expected on topic '{topic}' (tx {tx_hash})")
        return True
    block = _sealed_block(data, want, is_action)
    if block is None:
        return False
    success(f"Sealed at block {block}")
    return True


def _wait_for_seal(
    ctx,
    rpc_url: str,
    tx_hash: str,
    timeout: float,
    *,
    topic: str,
    is_action: bool,
    kind: str | None = None,
    target: str | None = None,
    sender: str | None = None,
    value: int | None = None,
    grantee: str | None = None,
    expect_listed: bool = True,
) -> None:
    """Poll the messaging read route until the tx is indexed or ``timeout`` passes.

    The generic ``/rpc/transaction/{hash}`` route 404s for MESSAGE
    transactions even after they seal, so polling it trips the HTTP
    client's circuit breaker ("Circuit breaker opened after 5 failures")
    on a healthy submission — seen live in MSG-3d. Posts and replies are
    detected at ``/rpc/messaging/messages/{tx_hash}``. Actions have no
    per-hash route: the six moderation kinds are detected by tx hash in
    the topic's moderation ``actions`` list (which only ever lists
    moderator-signed rows, so ``expect_listed=False`` from a non-moderator
    signer exits at once), while ``vote`` and ``mod_grant``/``mod_revoke``
    never appear there and are detected by their resulting *state*
    instead (reported as "reads as expected", not "sealed"; a retract is
    the signer's *absence* from standing votes). The ``actions`` list is
    capped at 100 entries, so when it reads full the hash match gets a
    short bound — a fresh hash may already have scrolled out. Plain
    ``requests`` keeps expected 404s away from the client's retry/breaker
    machinery (same pattern as ``utils.gpu_onchain.wait_for_tx``).
    Timeout degrades to a printed hint — the transaction was already
    submitted, so this must not abort.
    """
    base = rpc_url.rstrip("/")
    want = tx_hash.lower().removeprefix("0x")
    state_kind = is_action and kind in _STATE_ACTION_KINDS
    if is_action:
        route = _action_wait_route(base, kind or "", topic, target)
    else:
        route = f"{base}/rpc/messaging/messages/0x{want}"
    if route is None:
        warning(
            f"Transaction {tx_hash} submitted; no read route can confirm a '{kind}' — "
            f"verify via /rpc/messaging/topics/{topic}/moderation"
        )
        return
    if is_action and not expect_listed:
        warning(
            f"Transaction {tx_hash} submitted; '{kind}' is recorded but not effective for a non-moderator — "
            "verify with the raw transaction"
        )
        return
    start = time.monotonic()
    deadline = start + timeout
    cap_deadline: float | None = None
    saw_response = False
    while time.monotonic() < deadline and (cap_deadline is None or time.monotonic() < cap_deadline):
        data = _poll_read(route)
        if data is not _UNREACHABLE:
            # Any HTTP response — including an expected 404 — counts as the
            # RPC answering; 404 simply means "not indexed yet".
            saw_response = True
            if _wait_confirmed(
                data,
                want,
                is_action=is_action,
                state_kind=state_kind,
                kind=kind or "",
                topic=topic,
                tx_hash=tx_hash,
                sender=sender,
                value=value,
                grantee=grantee,
            ):
                return
            if (
                is_action
                and not state_kind
                and cap_deadline is None
                and isinstance(data, dict)
                and len(data.get("actions") or []) >= _MODERATION_ACTIONS_CAP
            ):
                cap_deadline = start + _CAPPED_WAIT_SECONDS
        time.sleep(_WAIT_POLL_SECONDS)
    hint = _wait_hint(is_action, kind, topic, target, tx_hash)
    if saw_response:
        warning(f"Transaction {tx_hash} submitted but not confirmed within {timeout:.0f}s — {hint}")
    else:
        warning(f"Transaction {tx_hash} submitted; no answer from RPC at {base} — {hint}")


@click.group(
    epilog="""Examples:

  aitbc messaging list --topic broadcast

  aitbc messaging send --wallet my-wallet --message 'hello' --topic broadcast"""
)
def messaging():
    """Read and post genuinely on-chain forum messages (signed MESSAGE transactions)."""
    pass


@messaging.command(
    epilog="""Examples:

  aitbc messaging send --wallet my-wallet --message 'hello'

  aitbc messaging send --wallet my-wallet --message 'see the announcement' --topic broadcast \\
      --reply-to 00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"""
)
@click.option("--wallet", "wallet_name", required=True, help="Wallet name that signs the post (the message author)")
@click.option("--message", required=True, help="Message body (public and permanent)")
@click.option("--topic", default=BROADCAST_TOPIC, show_default=True, help="Topic slug (lowercased, whitespace → '-')")
@click.option(
    "--reply-to",
    default=None,
    callback=_normalize_tx_hash,
    help="Parent message tx_hash — makes the post a reply (bare or 0x-prefixed 64-hex)",
)
@click.option("--fee", type=DECIMAL, default=DEFAULT_TX_FEE_AIT, show_default=True, help="Transaction fee (AIT)")
@click.option("--confirm", is_flag=True, help="Sign and submit once (default: dry run — prints the post, signs nothing)")
@click.option(
    "--wait/--no-wait",
    default=True,
    help="With --confirm: poll /rpc/messaging/messages/<hash> until the post is indexed (default: --wait); --no-wait prints only the submitted hash",
)
@click.option("--wait-timeout", type=float, default=180.0, show_default=True, help="Seconds --wait polls for")
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@wallet_password_options
@click.pass_context
def send(
    ctx,
    wallet_name: str,
    message: str,
    topic: str,
    reply_to: str | None,
    fee: Decimal,
    confirm: bool,
    wait: bool,
    wait_timeout: float,
    rpc_url: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
):
    """Post a forum message as a signed MESSAGE transaction.

    The default is a DRY RUN: it prints the wallet, sender address, topic,
    body length and fee and signs nothing. ``--confirm`` resolves the wallet
    password, signs once and submits once.
    """
    if not message or not message.strip():
        abort(ctx, "Empty message refused — a post must carry a body")
    if len(message.encode("utf-8")) > MAX_MESSAGE_BODY_BYTES:
        abort(ctx, f"Message is {len(message.encode('utf-8'))} bytes; maximum is {MAX_MESSAGE_BODY_BYTES}")

    canonical_topic = normalize_topic(topic)
    if canonical_topic is None:
        abort(ctx, f"Topic '{topic}' cannot become a slug (1–64 chars of a-z 0-9 . _ -)")
    assert canonical_topic is not None  # abort() raises; narrow for mypy
    if canonical_topic != topic:
        click.echo(f"topic normalized to '{canonical_topic}'", err=True)

    sender_address = _wallet_address(ctx, wallet_name)
    resolved_rpc = _resolve_transaction_rpc_url(rpc_url)

    try:
        envelope = build_envelope(
            kind="reply" if reply_to else "post",
            topic=canonical_topic,
            body=message,
            agent_address=sender_address,
            parent=reply_to,
        )
    except ValueError as e:
        abort(ctx, f"Invalid message envelope: {e}", from_exception=e)

    if not confirm:
        click.echo("DRY RUN — nothing signed, nothing sent. Re-run with --confirm to sign and submit once:", err=True)
        output(
            {
                "wallet": wallet_name,
                "sender": sender_address,
                "topic": canonical_topic,
                "kind": envelope["kind"],
                "parent": envelope.get("parent"),
                "body_bytes": len(message.encode("utf-8")),
                "fee_ait": str(fee),
            },
            (ctx.obj or {}).get("output_format", "table"),
            title="Message dry run",
        )
        return

    resolved_password = resolve_wallet_password(
        wallet_name=wallet_name,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
        ctx=ctx,
    )

    click.echo(_PERMANENCE_WARNING, err=True)
    tx_hash = _send_transaction_impl(
        wallet_name,
        sender_address,
        Decimal(0),
        fee,
        resolved_password,
        rpc_url=resolved_rpc,
        tx_type="MESSAGE",
        payload={"aitbc_msg": envelope},
    )
    if not tx_hash:
        raise SystemExit(1)

    output(
        {"tx_hash": tx_hash, "topic": canonical_topic, "kind": envelope["kind"], "author": sender_address},
        (ctx.obj or {}).get("output_format", "table"),
        title="Message submitted",
    )
    if wait:
        _wait_for_seal(ctx, resolved_rpc, tx_hash, wait_timeout, topic=canonical_topic, is_action=False)


@messaging.command(
    epilog="""Examples:

  aitbc messaging list

  aitbc messaging list --topic broadcast --limit 20 --cursor 42100:17"""
)
@click.option("--topic", default=None, help="Only this topic slug")
@click.option("--author", default=None, help="Only this author address")
@click.option("--query", default=None, help="Substring search over bodies (min 3 chars)")
@click.option("--limit", type=int, default=50, help="Max messages (server caps at 100)")
@click.option("--offset", type=int, default=0, help="Skip the first N results (bounded)")
@click.option("--cursor", default=None, help="Resume from a previous next_cursor")
@click.option("--include-hidden", is_flag=True, default=False, help="Show hidden/after-lock rows flagged, body withheld")
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def list(ctx, topic, author, query, limit, offset, cursor, include_hidden, rpc_url):
    """List forum messages, newest first."""
    if query is not None and len(query.strip()) < MIN_SEARCH_CHARS:
        abort(ctx, f"--query must be at least {MIN_SEARCH_CHARS} characters")
    rpc = _resolve_transaction_rpc_url(rpc_url)
    try:
        http_client = _rpc_client(rpc)
        if query:
            result = http_client.get(
                "/rpc/messaging/messages/search",
                params={"query": query, "limit": limit, "offset": offset, "cursor": cursor},
            )
        else:
            result = http_client.get(
                "/rpc/messaging/messages",
                params={
                    "topic": topic,
                    "author": author,
                    "limit": limit,
                    "offset": offset,
                    "cursor": cursor,
                    "include_hidden": str(include_hidden).lower(),
                },
            )
        output(sanitize_chain_obj(result), (ctx.obj or {}).get("output_format", "table"), title="Messages")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC unavailable at {rpc}: {e}", from_exception=e)
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure aborts cleanly, never tracebacks
        abort(ctx, f"Error listing messages: {e}", from_exception=e)


@messaging.command(
    epilog="""Example:

  aitbc messaging topics --limit 20"""
)
@click.option("--limit", type=int, default=50, help="Max topics (server caps at 100)")
@click.option("--offset", type=int, default=0, help="Skip the first N topics (bounded)")
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def topics(ctx, limit, offset, rpc_url):
    """List forum topics ranked by last activity."""
    rpc = _resolve_transaction_rpc_url(rpc_url)
    try:
        http_client = _rpc_client(rpc)
        result = http_client.get("/rpc/messaging/topics", params={"limit": limit, "offset": offset})
        output(sanitize_chain_obj(result), (ctx.obj or {}).get("output_format", "table"), title="Topics")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC unavailable at {rpc}: {e}", from_exception=e)
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure aborts cleanly, never tracebacks
        abort(ctx, f"Error listing topics: {e}", from_exception=e)


@messaging.command(
    epilog="""Examples:

  aitbc messaging subscribe dev --max-polls 1            # one-shot: what's new now
  aitbc messaging subscribe dev --follow                 # stream new messages until Ctrl-C
  aitbc messaging subscribe dev --from-cursor 420:ab12…  # resume after a marker"""
)
@click.argument("topic")
@click.option("--from-cursor", "from_cursor", default=None, help="Resume after a <height>:<tx_hash> marker")
@click.option("--follow", is_flag=True, help="Keep polling (default: one poll then exit)")
@click.option("--interval", type=float, default=5.0, show_default=True, help="Seconds between polls when --follow")
@click.option("--max-polls", type=int, default=None, help="Bound the poll count even with --follow")
@click.option("--limit", type=int, default=50, help="Rows fetched per poll (server caps at 100)")
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def subscribe(ctx, topic, from_cursor, follow, interval, max_polls, limit, rpc_url):
    """Poll a topic for new messages (cursor polling — there is no push stream).

    Yields rows strictly newer than --from-cursor; without a cursor it starts
    at the current head (no backlog). Each poll prints the new rows plus the
    ``next_cursor`` marker to resume from. This is the agent-facing durable
    subscribe path (MSG-15) — the same kernel the SDK's
    ``MessagingClient.subscribe`` uses.
    """
    from aitbc.messaging_client import parse_seen_cursor

    if from_cursor and parse_seen_cursor(from_cursor) is None:
        abort(ctx, f"--from-cursor '{from_cursor}' is not a '<height>:<tx_hash>' marker")
    rpc = _resolve_transaction_rpc_url(rpc_url)
    seen, rows = _subscribe_first_batch(ctx, rpc, topic, limit, parse_seen_cursor(from_cursor))
    if follow:
        marker = f"{seen[0]}:{seen[1]}" if seen else None
        last = _subscribe_follow(ctx, rpc, topic, marker, interval, max_polls)
        if last is not None:
            seen = last
    if seen is not None:
        click.echo(f"next_cursor: {seen[0]}:{seen[1]}", err=True)
    elif not rows:
        click.echo(f"no messages on topic '{topic}'", err=True)


def _subscribe_first_batch(ctx, rpc, topic, limit, seen):
    """Fetch the topic head, emit rows newer than ``seen``; returns ``(seen, rows)``."""
    from aitbc.messaging_client import (
        UNREACHABLE,
        fetch_messages,
        message_sort_key,
    )

    data = fetch_messages(rpc, topic=topic, limit=limit)
    if data is UNREACHABLE:
        abort(ctx, f"Blockchain RPC unavailable at {rpc}")
    if not isinstance(data, dict):
        abort(ctx, f"Messages index returned no data for topic '{topic}' at {rpc}")
    rows = sorted((data.get("messages") or []), key=message_sort_key)
    for row in rows:
        if seen is not None and message_sort_key(row) > seen:
            seen = message_sort_key(row)
            _sub_emit(ctx, row)
    if seen is None and rows:
        seen = message_sort_key(rows[-1])
    return seen, rows


def _sub_emit(ctx, row):
    output(sanitize_chain_obj(row), (ctx.obj or {}).get("output_format", "table"), title=None)


def _subscribe_follow(ctx, rpc, topic, marker, interval, max_polls):
    """Poll loop for ``messaging subscribe --follow``; returns the last sort key emitted."""
    from aitbc.messaging_client import message_sort_key
    from aitbc.messaging_client import subscribe as _subscribe

    last = None
    try:
        for row in _subscribe(rpc, topic, from_cursor=marker, interval=interval, max_polls=max_polls):
            last = message_sort_key(row)
            _sub_emit(ctx, row)
    except KeyboardInterrupt:
        pass
    return last


@messaging.command(
    "topic",
    epilog="""Example:

  aitbc messaging topic""",
    deprecated=True,
)
@click.option("--limit", type=int, default=50, help="Max topics (server caps at 100)")
@click.option("--offset", type=int, default=0, help="Skip the first N topics (bounded)")
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def topic_alias(ctx, limit, offset, rpc_url):
    """Alias of ``messaging topics`` — implicit topics have no create call."""
    ctx.invoke(topics, limit=limit, offset=offset, rpc_url=rpc_url)


@messaging.command(
    epilog="""Example:

  aitbc messaging show 00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"""
)
@click.argument("tx_hash", callback=_normalize_tx_hash)
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def show(ctx, tx_hash, rpc_url):
    """Show one forum message by its transaction hash (bare or 0x-prefixed)."""
    rpc = _resolve_transaction_rpc_url(rpc_url)
    try:
        http_client = _rpc_client(rpc)
        result = http_client.get(f"/rpc/messaging/messages/0x{tx_hash}")
        output(sanitize_chain_obj(result), (ctx.obj or {}).get("output_format", "table"), title="Message")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC unavailable at {rpc}: {e}", from_exception=e)
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure aborts cleanly, never tracebacks
        abort(ctx, f"Error fetching message: {e}", from_exception=e)


# -- MSG-2: signed on-chain actions ------------------------------------------
# Votes and moderation are signed MESSAGE transactions carrying action-kind
# `aitbc_msg` envelopes — never RPC writes. Moderation is a read-side filter;
# the bytes stay on every replica (docs/design/msg2-votes-moderation.md).

_TARGET_ACTIONS = {"hide", "unhide", "pin", "unpin"}


def _target_topic(ctx, http_client: AITBCHTTPClient, tx_hash: str) -> str:
    """Resolve an action target's topic by reading the message (avoids a
    mismatched-topic no-op only the index would see)."""
    try:
        view = http_client.get(f"/rpc/messaging/messages/0x{tx_hash}")
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure aborts cleanly, never tracebacks
        abort(ctx, f"Cannot resolve target {tx_hash} — not a forum message ({e})", from_exception=e)
    topic = view.get("topic")
    if not topic:
        abort(ctx, f"Target {tx_hash} is not a forum message")
    return str(topic)


def _effectiveness_now(http_client: AITBCHTTPClient, kind: str, topic: str, sender: str) -> Any:
    """Would this action be effective if it sealed right now?

    A vote always counts. Moderation kinds need the signer in the topic's
    derived moderator set. Returns True/False, or an ``unknown: …`` string
    when the moderation read fails — the dry run should still print.
    """
    if kind == "vote":
        return True
    try:
        view = http_client.get(f"/rpc/messaging/topics/{topic}/moderation")
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure aborts cleanly, never tracebacks
        return f"unknown: moderation read failed ({e})"
    if view.get("authority_unresolved"):
        return "unknown: topic authority unresolved"
    moderators = {str(m).lower() for m in view.get("moderators") or []}
    return sender.lower() in moderators


def _submit_action(
    ctx,
    wallet_name: str,
    kind: str,
    topic: str,
    fee: Decimal,
    confirm: bool,
    wait: bool,
    wait_timeout: float,
    rpc_url: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    *,
    target: str | None = None,
    value: int | None = None,
    grantee: str | None = None,
) -> None:
    sender_address = _wallet_address(ctx, wallet_name)
    resolved_rpc = _resolve_transaction_rpc_url(rpc_url)
    try:
        envelope = build_envelope(
            kind=kind,
            topic=topic,
            agent_address=sender_address,
            target=target,
            value=value,
            grantee=grantee,
        )
    except ValueError as e:
        abort(ctx, f"Invalid action envelope: {e}", from_exception=e)

    if not confirm:
        click.echo("DRY RUN — nothing signed, nothing sent. Re-run with --confirm to sign and submit once:", err=True)
        # `topic` may be chain-resolved (when it came from the target row
        # rather than the user's flag) — sanitise the whole echo.
        output(
            sanitize_chain_obj(
                {
                    "wallet": wallet_name,
                    "sender": sender_address,
                    "topic": topic,
                    "kind": kind,
                    "target": target,
                    "value": value,
                    "grantee": grantee,
                    "fee_ait": str(fee),
                    "envelope": envelope,
                    "would_be_effective_now": _effectiveness_now(_rpc_client(resolved_rpc), kind, topic, sender_address),
                }
            ),
            (ctx.obj or {}).get("output_format", "table"),
            title=f"{kind} dry run",
        )
        return

    resolved_password = resolve_wallet_password(
        wallet_name=wallet_name,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
        ctx=ctx,
    )
    pre_matched, expect_listed = (False, True)
    if wait:
        pre_matched, expect_listed = _presend_expectations(
            resolved_rpc, kind, topic, target, sender=sender_address, value=value, grantee=grantee
        )
    click.echo(_PERMANENCE_WARNING, err=True)
    tx_hash = _send_transaction_impl(
        wallet_name,
        sender_address,
        Decimal(0),
        fee,
        resolved_password,
        rpc_url=resolved_rpc,
        tx_type="MESSAGE",
        payload={"aitbc_msg": envelope},
    )
    if not tx_hash:
        raise SystemExit(1)
    output(
        sanitize_chain_obj({"tx_hash": tx_hash, "topic": topic, "kind": kind, "author": sender_address}),
        (ctx.obj or {}).get("output_format", "table"),
        title=f"{kind} submitted",
    )
    if wait:
        if pre_matched:
            if kind == "vote" and value == 0:
                info(f"retract found no standing vote from this signer on '{topic}' — nothing to retract; not waiting")
            else:
                info(f"'{kind}' state already reads as expected on '{topic}' (matched before this send) — not waiting")
        else:
            _wait_for_seal(
                ctx,
                resolved_rpc,
                tx_hash,
                wait_timeout,
                topic=topic,
                is_action=True,
                kind=kind,
                target=target,
                sender=sender_address,
                value=value,
                grantee=grantee,
                expect_listed=expect_listed,
            )


def _action_options(f):
    f = click.option("--wallet", "wallet_name", required=True, help="Wallet name that signs the action")(f)
    f = click.option("--fee", type=DECIMAL, default=DEFAULT_TX_FEE_AIT, show_default=True, help="Transaction fee (AIT)")(f)
    f = click.option(
        "--confirm", is_flag=True, help="Sign and submit once (default: dry run — prints the action, signs nothing)"
    )(f)
    f = click.option(
        "--wait/--no-wait",
        default=True,
        help="With --confirm: poll the kind's read route until confirmed — the topic moderation actions list for hide/pin/lock kinds, the target's votes route for vote, the moderators list for grant/revoke (default: --wait); --no-wait prints only the submitted hash",
    )(f)
    f = click.option("--wait-timeout", type=float, default=180.0, show_default=True)(f)
    f = click.option("--rpc-url", default=None, help="Blockchain RPC URL")(f)
    return wallet_password_options(f)


def _target_action(ctx, kind: str, tx_hash: str, topic: str | None, kw: dict) -> None:
    rpc = _resolve_transaction_rpc_url(kw["rpc_url"])
    resolved_topic = topic or _target_topic(ctx, _rpc_client(rpc), tx_hash)
    canonical_topic = normalize_topic(resolved_topic)
    if canonical_topic is None:
        abort(ctx, f"Topic '{resolved_topic}' is not a valid slug")
    assert canonical_topic is not None  # abort() raises; narrow for mypy
    _submit_action(ctx, kind=kind, topic=canonical_topic, target=tx_hash, **kw)


@messaging.command(
    epilog="""Example:

  aitbc messaging vote 0011…eeff up --wallet my-wallet"""
)
@click.argument("tx_hash", callback=_normalize_tx_hash)
@click.argument("direction", type=click.Choice(["up", "down", "retract"]))
@click.option("--topic", default=None, help="Topic slug (default: the target's own topic)")
@_action_options
@click.pass_context
def vote(
    ctx,
    tx_hash,
    direction,
    topic,
    wallet_name,
    fee,
    confirm,
    wait,
    wait_timeout,
    rpc_url,
    password,
    password_file,
    password_stdin,
):
    """Vote on a forum message. Last vote per signer wins; 'retract' clears it."""
    _target_action(
        ctx,
        "vote",
        tx_hash,
        topic,
        {
            "wallet_name": wallet_name,
            "fee": fee,
            "confirm": confirm,
            "wait": wait,
            "wait_timeout": wait_timeout,
            "rpc_url": rpc_url,
            "password": password,
            "password_file": password_file,
            "password_stdin": password_stdin,
            "value": {"up": 1, "down": -1, "retract": 0}[direction],
        },
    )


def _simple_target_command(kind: str, help_text: str):
    @messaging.command(kind, epilog=f"Example:\n\n  aitbc messaging {kind} <tx_hash> --wallet my-wallet")
    @click.argument("tx_hash", callback=_normalize_tx_hash)
    @click.option("--topic", default=None, help="Topic slug (default: the target's own topic)")
    @_action_options
    @click.pass_context
    def cmd(
        ctx, tx_hash, topic, wallet_name, fee, confirm, wait, wait_timeout, rpc_url, password, password_file, password_stdin
    ):
        _target_action(
            ctx,
            kind,
            tx_hash,
            topic,
            {
                "wallet_name": wallet_name,
                "fee": fee,
                "confirm": confirm,
                "wait": wait,
                "wait_timeout": wait_timeout,
                "rpc_url": rpc_url,
                "password": password,
                "password_file": password_file,
                "password_stdin": password_stdin,
            },
        )

    cmd.__doc__ = help_text
    return cmd


_simple_target_command("hide", "Hide a message in default reads (moderator only).")
_simple_target_command("unhide", "Undo a hide (moderator only).")
_simple_target_command("pin", "Pin a message atop its topic (moderator only).")
_simple_target_command("unpin", "Undo a pin (moderator only).")


def _lock_impl(
    ctx,
    action: str,
    topic,
    target,
    wallet_name,
    fee,
    confirm,
    wait,
    wait_timeout,
    rpc_url,
    password,
    password_file,
    password_stdin,
):
    """Lock a topic or one thread (moderator only). Exactly one of --topic/--target."""
    if (topic is None) == (target is None):
        abort(ctx, "Pass exactly one of --topic (whole topic) or --target (thread root)")
    canonical_topic: str | None
    if target is not None:
        rpc = _resolve_transaction_rpc_url(rpc_url)
        canonical_topic = _target_topic(ctx, _rpc_client(rpc), target)
    else:
        assert topic is not None  # the exactly-one check above guarantees it
        canonical_topic = normalize_topic(topic)
        if canonical_topic is None:
            abort(ctx, f"Topic '{topic}' is not a valid slug")
    assert canonical_topic is not None  # abort() raises; narrow for mypy
    _submit_action(
        ctx,
        wallet_name=wallet_name,
        kind=action,
        confirm=confirm,
        topic=canonical_topic,
        target=target,
        fee=fee,
        wait=wait,
        wait_timeout=wait_timeout,
        rpc_url=rpc_url,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
    )


@messaging.command(
    epilog="""Examples:

  aitbc messaging lock --topic dev --wallet my-wallet          # whole topic
  aitbc messaging lock --target <tx_hash> --wallet my-wallet   # one thread"""
)
@click.option("--topic", default=None, help="Lock the whole topic")
@click.option("--target", default=None, callback=_normalize_tx_hash, help="Lock the reply subtree under this message")
@_action_options
@click.pass_context
def lock(ctx, topic, target, wallet_name, fee, confirm, wait, wait_timeout, rpc_url, password, password_file, password_stdin):
    """Lock a topic or one thread (moderator only)."""
    _lock_impl(
        ctx,
        "lock",
        topic,
        target,
        wallet_name,
        fee,
        confirm,
        wait,
        wait_timeout,
        rpc_url,
        password,
        password_file,
        password_stdin,
    )


@messaging.command("unlock", epilog="Same options as `messaging lock`.")
@click.option("--topic", default=None, help="Unlock the whole topic")
@click.option("--target", default=None, callback=_normalize_tx_hash, help="Unlock the reply subtree under this message")
@_action_options
@click.pass_context
def unlock(
    ctx, topic, target, wallet_name, fee, confirm, wait, wait_timeout, rpc_url, password, password_file, password_stdin
):
    """Undo a lock (moderator only)."""
    _lock_impl(
        ctx,
        "unlock",
        topic,
        target,
        wallet_name,
        fee,
        confirm,
        wait,
        wait_timeout,
        rpc_url,
        password,
        password_file,
        password_stdin,
    )


def _mod_grant_command(kind: str, help_text: str):
    @messaging.command(
        kind.replace("_", "-"),
        epilog=f"Example:\n\n  aitbc messaging {kind.replace('_', '-')} <address> --topic dev --wallet my-wallet",
    )
    @click.argument("grantee")
    @click.option("--topic", required=True, help="Topic slug the grant applies to")
    @_action_options
    @click.pass_context
    def cmd(
        ctx, grantee, topic, wallet_name, fee, confirm, wait, wait_timeout, rpc_url, password, password_file, password_stdin
    ):
        canonical_topic = normalize_topic(topic)
        if canonical_topic is None:
            abort(ctx, f"Topic '{topic}' is not a valid slug")
        assert canonical_topic is not None  # abort() raises; narrow for mypy
        _submit_action(
            ctx,
            wallet_name=wallet_name,
            kind=kind,
            topic=canonical_topic,
            grantee=grantee,
            confirm=confirm,
            fee=fee,
            wait=wait,
            wait_timeout=wait_timeout,
            rpc_url=rpc_url,
            password=password,
            password_file=password_file,
            password_stdin=password_stdin,
        )

    cmd.__doc__ = help_text
    return cmd


_mod_grant_command("mod_grant", "Grant topic moderation to an address (moderator only).")
_mod_grant_command("mod_revoke", "Revoke a topic moderator (moderator only; cannot empty the set).")


@messaging.command(
    epilog="""Example:

  aitbc messaging reputation 0x…"""
)
@click.argument("address")
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def reputation(ctx, address, rpc_url):
    """Show an address's derived forum reputation (display-only integer)."""
    rpc = _resolve_transaction_rpc_url(rpc_url)
    try:
        result = _rpc_client(rpc).get(f"/rpc/messaging/reputation/{address}")
        output(sanitize_chain_obj(result), (ctx.obj or {}).get("output_format", "table"), title="Reputation")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC unavailable at {rpc}: {e}", from_exception=e)
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure aborts cleanly, never tracebacks
        abort(ctx, f"Error fetching reputation: {e}", from_exception=e)


@messaging.command(
    epilog="""Example:

  aitbc messaging moderators dev"""
)
@click.argument("topic")
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def moderators(ctx, topic, rpc_url):
    """Show a topic's derived moderator set, locks and recent actions."""
    rpc = _resolve_transaction_rpc_url(rpc_url)
    try:
        result = _rpc_client(rpc).get(f"/rpc/messaging/topics/{topic}/moderation")
        output(sanitize_chain_obj(result), (ctx.obj or {}).get("output_format", "table"), title=f"Moderation: {topic}")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC unavailable at {rpc}: {e}", from_exception=e)
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure aborts cleanly, never tracebacks
        abort(ctx, f"Error fetching moderation state: {e}", from_exception=e)


@messaging.command(
    epilog="""Example:

  aitbc messaging state"""
)
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def state(ctx, rpc_url):
    """Show forum index totals and the index height."""
    rpc = _resolve_transaction_rpc_url(rpc_url)
    try:
        http_client = _rpc_client(rpc)
        result = http_client.get("/rpc/messaging/state")
        output(sanitize_chain_obj(result), (ctx.obj or {}).get("output_format", "table"), title="Messaging state")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC unavailable at {rpc}: {e}", from_exception=e)
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure aborts cleanly, never tracebacks
        abort(ctx, f"Error fetching state: {e}", from_exception=e)


# -- MSG-8: encrypted direct messages ----------------------------------------
# SealedBox (libsodium crypto_box_seal) to a recipient's published `dm_key`;
# the chain carries ciphertext only and the node never sees plaintext. The
# X25519 private key is client state: one mode-600 JSON file per wallet in a
# `dm-keys/` dir that is a sibling of the wallet's directory — key material
# stays out of the wallet file format entirely.


# Crypto + key-store kernel lives in ``aitbc.dm_client`` (shared with the
# SDK); re-imported under the historical ``_names`` so test patch points
# and import sites keep working.
from aitbc.dm_client import (
    DmStoreCorruptError,
    dm_keys_dir as _dm_keys_dir,
    dm_mark_published as _dm_mark_published,
    dm_max_plaintext_bytes as _dm_max_plaintext_bytes,
    dm_prepare_era as _dm_prepare_era,
    dm_store_load as _dm_store_load,
    dm_store_save as _dm_store_save,  # noqa: F401  (test-suite import surface)
    open_dm as _open_dm,
    seal_dm as _seal_dm,
)


def _dm_key_file(ctx, wallet_name: str) -> Path:
    report = find_wallet_file_report(wallet_name)
    if report.path is None:
        abort(ctx, wallet_not_found_message(report))
    path = cast(Path, report.path)
    return _dm_keys_dir(path) / f"{wallet_name}.json"


def _dm_current_key(ctx, wallet_name: str) -> tuple[dict[str, Any], Path]:
    """The newest key era for the wallet, or abort with the fix."""
    path = _dm_key_file(ctx, wallet_name)
    try:
        store = _dm_store_load(path, strict=True)
    except DmStoreCorruptError as e:
        abort(ctx, str(e), from_exception=e)
    if store["keys"]:
        return store["keys"][-1], path
    abort(
        ctx,
        f"No DM key for wallet '{wallet_name}' — run `aitbc messaging dm keygen --wallet {wallet_name} --confirm` first",
    )
    raise AssertionError  # unreachable


@messaging.group("dm")
def dm_group():
    """Encrypted direct messages (MSG-8): ciphertext on-chain, keys client-side."""


@dm_group.command(
    "keygen",
    epilog="""Example:

  aitbc messaging dm keygen --wallet my-wallet --confirm""",
)
@click.option("--wallet", "wallet_name", required=True, help="Wallet that signs the dm_key publication")
@click.option("--fee", type=DECIMAL, default=DEFAULT_TX_FEE_AIT, show_default=True, help="Transaction fee (AIT)")
@click.option("--confirm", is_flag=True, help="Generate the key (if needed) and sign+submit once (default: dry run)")
@click.option(
    "--rotate",
    is_flag=True,
    help="Publish a fresh key even if one exists (old eras are kept in the key file for old ciphertext)",
)
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@wallet_password_options
@click.pass_context
def dm_keygen(ctx, wallet_name, fee, confirm, rotate, rpc_url, password, password_file, password_stdin):
    """Create (or rotate) this wallet's DM key and publish the public half on-chain.

    DRY RUN by default. With --confirm: a new X25519 keypair is stored in the
    mode-600 dm-keys file and a ``dm_key`` envelope is signed and submitted.
    """
    path = _dm_key_file(ctx, wallet_name)
    try:
        era, store = _dm_prepare_era(path, rotate=rotate)
    except DmStoreCorruptError as e:
        abort(ctx, str(e), from_exception=e)
    if era is None:
        pub = store["keys"][-1]["enc_pubkey"]
        click.echo(f"DM key already exists for '{wallet_name}' (enc_pubkey {pub}); use --rotate to publish a new one")
        return
    pub = era["enc_pubkey"]
    sender_address = _wallet_address(ctx, wallet_name)
    resolved_rpc = _resolve_transaction_rpc_url(rpc_url)
    envelope = build_envelope(kind="dm_key", topic=DM_TOPIC, agent_address=sender_address, enc_pubkey=pub)
    if not confirm:
        click.echo("DRY RUN — nothing signed, nothing sent. Re-run with --confirm to sign and submit once:", err=True)
        output(
            {"wallet": wallet_name, "sender": sender_address, "kind": "dm_key", "enc_pubkey": pub, "fee_ait": str(fee)},
            (ctx.obj or {}).get("output_format", "table"),
            title="dm_key dry run",
        )
        return
    resolved_password = resolve_wallet_password(
        wallet_name=wallet_name,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
        ctx=ctx,
    )
    click.echo(_PERMANENCE_WARNING, err=True)
    tx_hash = _send_transaction_impl(
        wallet_name,
        sender_address,
        Decimal(0),
        fee,
        resolved_password,
        rpc_url=resolved_rpc,
        tx_type="MESSAGE",
        payload={"aitbc_msg": envelope},
    )
    if not tx_hash:
        click.echo(
            f"Submission failed — the DM key era is kept unpublished on disk ({path}); "
            "re-run `dm keygen` to publish the same era.",
            err=True,
        )
        raise SystemExit(1)
    _dm_mark_published(path, store, era, tx_hash)
    output(
        {"tx_hash": tx_hash, "kind": "dm_key", "author": sender_address, "key_file": str(path)},
        (ctx.obj or {}).get("output_format", "table"),
        title="dm_key submitted",
    )


@dm_group.command(
    "send",
    epilog="""Example:

  aitbc messaging dm send 0xRECIPIENT --message 'hello' --wallet my-wallet --confirm""",
)
@click.argument("recipient")
@click.option("--wallet", "wallet_name", required=True, help="Wallet that signs the DM")
@click.option("--message", required=True, help="Plaintext body (encrypted before it leaves this process)")
@click.option("--fee", type=DECIMAL, default=DEFAULT_TX_FEE_AIT, show_default=True, help="Transaction fee (AIT)")
@click.option("--confirm", is_flag=True, help="Seal, sign and submit once (default: dry run)")
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@wallet_password_options
@click.pass_context
def dm_send(ctx, recipient, wallet_name, message, fee, confirm, rpc_url, password, password_file, password_stdin):
    """Send an encrypted DM to a recipient who has published a dm_key.

    Metadata (sender, recipient, size, time) is public by design; only the
    body is sealed.
    """
    from aitbc.crypto.signature_recovery import canonical_address

    try:
        recipient_c = canonical_address(recipient, strict=True)
    except ValueError:
        abort(ctx, f"Recipient '{recipient}' is not a 0x address")
    if not message:
        abort(ctx, "Empty message refused")
    limit = _dm_max_plaintext_bytes()
    if len(message.encode("utf-8")) > limit:
        abort(ctx, f"Message is {len(message.encode('utf-8'))} bytes; the DM limit is ~{limit}")
    sender_address = _wallet_address(ctx, wallet_name)
    resolved_rpc = _resolve_transaction_rpc_url(rpc_url)
    try:
        keyinfo = _rpc_client(resolved_rpc).get(f"/rpc/messaging/dm-keys/{recipient_c}")
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure aborts cleanly, never tracebacks
        abort(ctx, f"Recipient {recipient_c} has no published dm_key ({e})", from_exception=e)
    enc_pub = (keyinfo or {}).get("enc_pubkey")
    if not isinstance(enc_pub, str) or not enc_pub:
        abort(ctx, f"Recipient {recipient_c} has no published dm_key")
    ct = _seal_dm(cast(str, enc_pub), sender_address, recipient_c, message)
    envelope = build_envelope(kind="dm", topic=DM_TOPIC, agent_address=sender_address, to=recipient_c, ct=ct)
    if not confirm:
        click.echo("DRY RUN — nothing signed, nothing sent. Re-run with --confirm to sign and submit once:", err=True)
        output(
            {
                "wallet": wallet_name,
                "sender": sender_address,
                "to": recipient_c,
                "kind": "dm",
                "ct_bytes": len(ct),
                "fee_ait": str(fee),
            },
            (ctx.obj or {}).get("output_format", "table"),
            title="dm dry run",
        )
        return
    resolved_password = resolve_wallet_password(
        wallet_name=wallet_name,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
        ctx=ctx,
    )
    click.echo(_PERMANENCE_WARNING, err=True)
    tx_hash = _send_transaction_impl(
        wallet_name,
        sender_address,
        Decimal(0),
        fee,
        resolved_password,
        rpc_url=resolved_rpc,
        tx_type="MESSAGE",
        payload={"aitbc_msg": envelope},
    )
    if not tx_hash:
        raise SystemExit(1)
    output(
        {"tx_hash": tx_hash, "kind": "dm", "author": sender_address, "to": recipient_c},
        (ctx.obj or {}).get("output_format", "table"),
        title="dm submitted",
    )


@dm_group.command(
    "inbox",
    epilog="""Example:

  aitbc messaging dm inbox --wallet my-wallet""",
)
@click.option("--wallet", "wallet_name", required=True, help="Wallet whose address is the recipient")
@click.option("--limit", type=int, default=50, help="Max rows (server caps at 100)")
@click.option("--cursor", default=None, help="Resume from a previous next_cursor")
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def dm_inbox_cmd(ctx, wallet_name, limit, cursor, rpc_url):
    """List this wallet's DM inbox — ciphertext metadata only, nothing decrypted."""
    address = _wallet_address(ctx, wallet_name)
    rpc = _resolve_transaction_rpc_url(rpc_url)
    try:
        result = _rpc_client(rpc).get(f"/rpc/messaging/dm/{address}", params={"limit": limit, "cursor": cursor})
        output(sanitize_chain_obj(result), (ctx.obj or {}).get("output_format", "table"), title="DM inbox")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC unavailable at {rpc}: {e}", from_exception=e)
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure aborts cleanly, never tracebacks
        abort(ctx, f"Error fetching inbox: {e}", from_exception=e)


@dm_group.command(
    "read",
    epilog="""Example:

  aitbc messaging dm read 0011…eeff --wallet my-wallet""",
)
@click.argument("tx_hash", callback=_normalize_tx_hash)
@click.option("--wallet", "wallet_name", required=True, help="Wallet whose DM key decrypts the message")
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def dm_read(ctx, tx_hash, wallet_name, rpc_url):
    """Fetch and decrypt one DM addressed to this wallet."""
    address = _wallet_address(ctx, wallet_name)
    key, _path = _dm_current_key(ctx, wallet_name)
    rpc = _resolve_transaction_rpc_url(rpc_url)
    want = tx_hash.lower()
    row = None
    cursor = None
    try:
        http = _rpc_client(rpc)
        for _ in range(20):
            page = http.get(f"/rpc/messaging/dm/{address}", params={"limit": 100, "cursor": cursor})
            for m in page.get("messages") or []:
                if str(m.get("tx_hash", "")).lower().removeprefix("0x") == want:
                    row = m
                    break
            if row is not None or not page.get("next_cursor"):
                break
            cursor = page["next_cursor"]
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC unavailable at {rpc}: {e}", from_exception=e)
    if row is None:
        abort(ctx, f"No DM to {address} with tx hash 0x{tx_hash} in the scanned inbox pages")
    row = cast("dict[str, Any]", row)
    try:
        body = _open_dm(key["secret_key"], row["sender"], address, row["ct"])
    except ValueError as e:
        abort(ctx, f"Cannot read message: {e}", from_exception=e)
    output(
        {
            "tx_hash": row["tx_hash"],
            "block_height": row["block_height"],
            "from": row["sender"],
            "to": address,
            "body": sanitize_chain_obj(body),
        },
        (ctx.obj or {}).get("output_format", "table"),
        title="Direct message",
    )


@messaging.command(
    epilog="""Example:

  aitbc messaging stats"""
)
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def stats(ctx, rpc_url):
    """MSG-6 operability snapshot: index height, lag and checkpoint digest.

    Read-only; the checkpoint digest is the same value the node exports as
    ``aitbc_messaging_index_digest`` for cross-node comparison.
    """
    rpc = _resolve_transaction_rpc_url(rpc_url)
    try:
        http_client = _rpc_client(rpc)
        result = http_client.get("/rpc/messaging/stats")
        output(sanitize_chain_obj(result), (ctx.obj or {}).get("output_format", "table"), title="Messaging stats")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC unavailable at {rpc}: {e}", from_exception=e)
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure aborts cleanly, never tracebacks
        abort(ctx, f"Error fetching stats: {e}", from_exception=e)
