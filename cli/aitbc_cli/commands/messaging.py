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

import click

from aitbc.messaging import BROADCAST_TOPIC, MAX_MESSAGE_BODY_BYTES, MIN_SEARCH_CHARS, build_envelope, normalize_topic
from aitbc.utils.units import DEFAULT_TX_FEE_AIT

from ..utils import DECIMAL, output, success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError
from ..utils.wallet_paths import wallet_dir
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
    path = wallet_dir() / f"{wallet_name}.json"
    if not path.exists():
        abort(ctx, f"Wallet '{wallet_name}' not found at {path}")
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
@click.option("--wait/--no-wait", default=True, help="Poll until the transaction is sealed (default: wait)")
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
    wait: bool,
    wait_timeout: float,
    rpc_url: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
):
    """Post a forum message as a signed MESSAGE transaction."""
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
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def list(ctx, topic, author, query, limit, offset, cursor, rpc_url):
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
                },
            )
        output(result, (ctx.obj or {}).get("output_format", "table"), title="Messages")
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
        output(result, (ctx.obj or {}).get("output_format", "table"), title="Topics")
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
        output(result, (ctx.obj or {}).get("output_format", "table"), title="Message")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC unavailable at {rpc}: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error fetching message: {e}", from_exception=e)


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
        output(result, (ctx.obj or {}).get("output_format", "table"), title="Messaging state")
    except NetworkError as e:
        abort(ctx, f"Blockchain RPC unavailable at {rpc}: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error fetching state: {e}", from_exception=e)
