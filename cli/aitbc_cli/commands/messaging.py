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
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import click

from aitbc.messaging import BROADCAST_TOPIC, MAX_MESSAGE_BODY_BYTES, MIN_SEARCH_CHARS, build_envelope, normalize_topic
from aitbc.textsafety import sanitize_chain_obj
from aitbc.utils.units import DEFAULT_TX_FEE_AIT

from ..utils import DECIMAL, output, success
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


def _wait_for_seal(ctx, http_client: AITBCHTTPClient, tx_hash: str, timeout: float) -> None:
    """Poll the transaction until it is sealed into a block or ``timeout`` passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = http_client.get(f"/rpc/transaction/{tx_hash}")
        except Exception:
            time.sleep(_WAIT_POLL_SECONDS)
            continue
        if result.get("block_height") is not None:
            success(f"Sealed at block {result['block_height']} (status {result.get('status')})")
            return
        time.sleep(_WAIT_POLL_SECONDS)
    abort(ctx, f"Transaction {tx_hash} not sealed within {timeout:.0f}s — check `aitbc transactions status`")


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
@click.option("--reply-to", default=None, help="Parent message tx_hash — makes the post a reply")
@click.option("--fee", type=DECIMAL, default=DEFAULT_TX_FEE_AIT, show_default=True, help="Transaction fee (AIT)")
@click.option("--confirm", is_flag=True, help="Sign and submit once (default: dry run — prints the post, signs nothing)")
@click.option("--wait/--no-wait", default=True, help="With --confirm: poll until the transaction is sealed (default: wait)")
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
            # stored tx_hash values are lowercase; an uppercase --reply-to
            # would sign a parent the index can never resolve
            parent=reply_to.lower() if reply_to else None,
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
        _wait_for_seal(ctx, _rpc_client(resolved_rpc), tx_hash, wait_timeout)


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
@click.argument("tx_hash")
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def show(ctx, tx_hash, rpc_url):
    """Show one forum message by its transaction hash."""
    rpc = _resolve_transaction_rpc_url(rpc_url)
    try:
        http_client = _rpc_client(rpc)
        result = http_client.get(f"/rpc/messaging/messages/{tx_hash}")
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
        view = http_client.get(f"/rpc/messaging/messages/{tx_hash}")
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
        _wait_for_seal(ctx, _rpc_client(resolved_rpc), tx_hash, wait_timeout)


def _action_options(f):
    f = click.option("--wallet", "wallet_name", required=True, help="Wallet name that signs the action")(f)
    f = click.option("--fee", type=DECIMAL, default=DEFAULT_TX_FEE_AIT, show_default=True, help="Transaction fee (AIT)")(f)
    f = click.option(
        "--confirm", is_flag=True, help="Sign and submit once (default: dry run — prints the action, signs nothing)"
    )(f)
    f = click.option("--wait/--no-wait", default=True, help="With --confirm: poll until sealed (default: wait)")(f)
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
@click.argument("tx_hash")
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
    @click.argument("tx_hash")
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
@click.option("--target", default=None, help="Lock the reply subtree under this message")
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
@click.option("--target", default=None, help="Unlock the reply subtree under this message")
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
