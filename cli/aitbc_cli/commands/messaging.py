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
    DM_CONTEXT,
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
    except Exception as e:
        abort(ctx, f"Wallet '{wallet_name}' unreadable: {e}", from_exception=e)
    if not address:
        abort(ctx, f"Wallet '{wallet_name}' carries no address field")
    return str(address)


_STATE_ACTION_KINDS = frozenset({"vote", "mod_grant", "mod_revoke"})
_TX_ACTION_KINDS = frozenset({"hide", "unhide", "pin", "unpin", "lock", "unlock"})


def _action_wait_route(base: str, kind: str, topic: str, target: str | None) -> str | None:
    """Read route that proves a messaging action, or ``None`` if none exists.

    State kinds read their effect: ``vote`` via the target's ``/votes``
    route (standing votes carry no per-tx hash), ``mod_grant``/``mod_revoke``
    via the topic's ``moderators`` list. The six moderation kinds are
    detected by tx hash inside the moderation ``actions`` list.
    """
    if kind == "vote":
        if target is None:
            return None
        prefixed = target if target.startswith("0x") else f"0x{target}"
        return f"{base}/rpc/messaging/messages/{prefixed}/votes"
    if kind in _STATE_ACTION_KINDS or kind in _TX_ACTION_KINDS:
        return f"{base}/rpc/messaging/topics/{topic}/moderation"
    return None


def _action_state_matches(kind: str, data: Any, *, sender: str | None, value: int | None, grantee: str | None) -> bool:
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


def _action_state_probe(
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

    Lets the confirm path say "already matched before this send" instead
    of claiming a seal when the state predates the submission.
    """
    import requests

    route = _action_wait_route(rpc_url.rstrip("/"), kind, topic, target)
    if route is None:
        return False
    try:
        resp = requests.get(route, timeout=10)
        data = resp.json() if resp.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return False
    return _action_state_matches(kind, data, sender=sender, value=value, grantee=grantee)


def _sealed_block(data: Any, want: str, is_action: bool) -> Any:
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


_MODERATOR_GATED_KINDS = _TX_ACTION_KINDS | {"mod_grant", "mod_revoke"}
_CAPPED_WAIT_SECONDS = 30.0
_MODERATION_ACTIONS_CAP = 100
_UNREACHABLE = object()


def _topic_moderators_probe(rpc_url: str, topic: str) -> set[str] | None:
    """Lowercased moderator set for a topic, or ``None`` when the read failed."""
    data = _poll_read(f"{rpc_url.rstrip('/')}/rpc/messaging/topics/{topic}/moderation")
    if not isinstance(data, dict):
        return None
    return {str(m).lower() for m in data.get("moderators") or []}


def _poll_read(route: str) -> Any:
    """One GET: parsed JSON on 200, ``None`` on other statuses, ``_UNREACHABLE`` on transport failure."""
    import requests

    try:
        resp = requests.get(route, timeout=10)
    except requests.RequestException:
        return _UNREACHABLE
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


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


def _wait_hint(is_action: bool, kind: str | None, topic: str, target: str | None, tx_hash: str) -> str:
    """The route or command a user should check after a timed-out wait."""
    if not is_action:
        return f"verify with `aitbc messaging show {tx_hash}`"
    if kind == "vote" and target:
        prefixed = target if target.startswith("0x") else f"0x{target}"
        return f"verify via the target's votes route (/rpc/messaging/messages/{prefixed}/votes)"
    return f"verify via the topic moderation route (/rpc/messaging/topics/{topic}/moderation)"


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
    except Exception as e:
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
    except Exception as e:
        abort(ctx, f"Error listing topics: {e}", from_exception=e)


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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
        abort(ctx, f"Error fetching state: {e}", from_exception=e)


# -- MSG-8: encrypted direct messages ----------------------------------------
# SealedBox (libsodium crypto_box_seal) to a recipient's published `dm_key`;
# the chain carries ciphertext only and the node never sees plaintext. The
# X25519 private key is client state: one mode-600 JSON file per wallet in a
# `dm-keys/` dir that is a sibling of the wallet's directory — key material
# stays out of the wallet file format entirely.


def _dm_keys_dir(wallet_path: Path) -> Path:
    """``<wallets_dir>/../dm-keys`` — alongside the wallet directory."""
    return wallet_path.parent.parent / "dm-keys"


def _dm_key_file(ctx, wallet_name: str) -> Path:
    report = find_wallet_file_report(wallet_name)
    if report.path is None:
        abort(ctx, wallet_not_found_message(report))
    path = cast(Path, report.path)
    return _dm_keys_dir(path) / f"{wallet_name}.json"


def _dm_store_load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {"keys": []}
    except Exception:
        return {"keys": []}
    # `list` is shadowed by the Click command above — use the builtins name.
    import builtins

    return data if isinstance(data, dict) and isinstance(data.get("keys"), builtins.list) else {"keys": []}


def _dm_store_save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    path.chmod(0o600)


def _dm_current_key(ctx, wallet_name: str) -> tuple[dict[str, Any], Path]:
    """The newest key era for the wallet, or abort with the fix."""
    path = _dm_key_file(ctx, wallet_name)
    store = _dm_store_load(path)
    if store["keys"]:
        return store["keys"][-1], path
    abort(
        ctx,
        f"No DM key for wallet '{wallet_name}' — run `aitbc messaging dm keygen --wallet {wallet_name} --confirm` first",
    )
    raise AssertionError  # unreachable


def _seal_dm(recipient_pub_b64: str, sender: str, recipient: str, body: str) -> str:
    import base64

    from nacl.public import PublicKey, SealedBox

    plaintext = f"{DM_CONTEXT}\n{sender}\n{recipient}\n{body}".encode()
    box = SealedBox(PublicKey(base64.b64decode(recipient_pub_b64, validate=True)))
    return base64.b64encode(box.encrypt(plaintext)).decode("ascii")


def _open_dm(secret_b64: str, sender: str, recipient: str, ct_b64: str) -> str:
    """Decrypt + verify the authenticated inner header. Raises ValueError on
    any failure — never returns unverified plaintext."""
    import base64
    import binascii

    from nacl.exceptions import CryptoError
    from nacl.public import PrivateKey, SealedBox

    try:
        ct = base64.b64decode(ct_b64.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as e:
        raise ValueError("ciphertext is not strict base64") from e
    try:
        plain = SealedBox(PrivateKey(base64.b64decode(secret_b64, validate=True))).decrypt(ct)
    except CryptoError as e:
        raise ValueError("decryption failed — wrong key or tampered ciphertext") from e
    try:
        text = plain.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("decrypted payload is not UTF-8") from e
    return _dm_check_header(text, sender, recipient)


def _dm_check_header(text: str, sender: str, recipient: str) -> str:
    """Verify the ``aitbc-dm-v1`` inner header and return the body, or raise.

    The header ties plaintext to both identities: header sender must equal
    the transaction signer, header recipient must equal this wallet. Any
    mismatch rejects — never a guess."""
    from aitbc.crypto.signature_recovery import canonical_address

    parts = text.split("\n", 3)
    if len(parts) != 4:
        raise ValueError("decrypted payload lacks the aitbc-dm-v1 header")
    context, h_sender, h_recipient, body = parts
    if context != DM_CONTEXT:
        raise ValueError("decrypted payload has the wrong context string")
    try:
        if canonical_address(h_sender) != canonical_address(sender):
            raise ValueError("header sender does not match the transaction signer")
        if canonical_address(h_recipient) != canonical_address(recipient):
            raise ValueError("header recipient is not this wallet")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError("malformed address in the decrypted header") from e
    if not body:
        raise ValueError("decrypted payload has an empty body")
    return body


def _dm_max_plaintext_bytes() -> int:
    """Room for the message after the sealed-box overhead + inner header."""
    # 4096 base64 chars = 3072 raw bytes; SealedBox adds 48 B; the header is
    # context + 2 newlines + two 42-char addresses + 1 newline ≈ 106 B.
    return 3072 - 48 - (len(DM_CONTEXT) + 3 + 84)


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
    import base64

    from nacl.public import PrivateKey

    path = _dm_key_file(ctx, wallet_name)
    store = _dm_store_load(path)
    if store["keys"] and not rotate:
        pub = store["keys"][-1]["enc_pubkey"]
        click.echo(f"DM key already exists for '{wallet_name}' (enc_pubkey {pub}); use --rotate to publish a new one")
        era = None
    else:
        sk = PrivateKey.generate()
        pub = base64.b64encode(bytes(sk.public_key)).decode("ascii")
        era = {"enc_pubkey": pub, "secret_key": base64.b64encode(bytes(sk)).decode("ascii"), "published_tx": None}
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
        raise SystemExit(1)
    if era is not None:
        era["published_tx"] = tx_hash
        store["keys"].append(era)
        _dm_store_save(path, store)
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
    except Exception:
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
        abort(ctx, f"Error fetching stats: {e}", from_exception=e)
