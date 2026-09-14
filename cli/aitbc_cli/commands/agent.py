"""
Agent messaging commands for AITBC CLI
"""

import asyncio as _asyncio
import json
import os
from pathlib import Path
from typing import Any

import click
import websockets
from websockets.exceptions import WebSocketException

from ..config import get_config
from ..utils import error, info, output, success
from ..utils.agent_signing import (
    agent_login_token,
    check_registry_binding,
    find_agent_by_identity,
    load_signing_wallet,
    sign_send_envelope,
    signed_request_headers,
)
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ..utils.wallet_paths import find_wallet_file, wallet_search_dirs

logger = get_logger(__name__)


def _build_ws_url(base_url: str, sender: str, token: str | None = None) -> str:
    """Build WebSocket endpoint URL from HTTP base URL, sender agent ID, and optional token.

    ``token`` today is the coordinator API key / a user JWT. The signed-envelope
    roadmap (agent-signed-envelopes.md) replaces this with an agent JWT fetched
    via the coordinator's agent login endpoint (Phase B1, server-side) —
    ``?token=<agent JWT>`` — and eventually a signed first-frame hello so the
    socket binds to the wallet identity rather than a shared key. Until that
    endpoint exists the API-key token stays the only option.
    """
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    url = f"{ws_url}/api/v1/agent/messages/stream?agent_id={sender}"
    if token:
        url += f"&token={token}"
    return url


async def _consume_connection_frame(ws, timeout: int, ws_endpoint: str) -> bool:
    """Consume the connection_established frame sent on WebSocket connect.

    Returns True if the frame was consumed successfully, False on error.
    """
    try:
        conn_msg = await _asyncio.wait_for(ws.recv(), timeout=timeout)
        conn_data = json.loads(conn_msg)
        if conn_data.get("type") != "connection_established":
            error(f"Unexpected first message: {conn_data.get('type')}")
            return False
        return True
    except _asyncio.TimeoutError:
        error(f"No connection confirmation from {ws_endpoint} within {timeout}s")
        return False


def _ws_auth_token(
    ctx,
    base_url: str,
    sender: str,
    wallet_name: str | None,
    password: str | None,
    fallback_token: str | None,
) -> str | None:
    """Resolve the ?token= credential for the WebSocket stream.

    When a signing wallet is configured (--wallet/AITBC_DEFAULT_WALLET)
    and sender is identity-bound to it, mints an agent JWT via the Phase B1
    login endpoint so the stream authenticates as that agent. Any failure —
    no wallet configured, agent not registered/bound to the wallet, or a
    coordinator without the login endpoint — falls back to
    fallback_token (the shared API key), keeping pre-B1 coordinators and
    unsigned setups working.
    """
    try:
        signing = load_signing_wallet(ctx, wallet_name=wallet_name, password=password)
    except Exception as e:
        info(f"Wallet login unavailable ({e}) — falling back to the shared API key token")
        return fallback_token
    if signing is None:
        return fallback_token
    address, private_key = signing
    client = AITBCHTTPClient(base_url=base_url, timeout=10)
    binding_error = check_registry_binding(client, sender, address)
    if binding_error:
        info(f"{binding_error} — falling back to the shared API key token")
        return fallback_token
    token = agent_login_token(client, sender, address, private_key)
    if token is None:
        info("Agent login endpoint did not issue a token — falling back to the shared API key token")
        return fallback_token
    return token


def _default_wallet_name() -> str | None:
    """Resolve the configured default wallet name.

    Checks the AITBC_DEFAULT_WALLET env var first, then ``active_wallet`` in
    ~/.aitbc/config.yaml. Returns None when neither is set.
    """
    wallet_name = os.environ.get("AITBC_DEFAULT_WALLET")
    if wallet_name:
        return wallet_name
    config_file = Path.home() / ".aitbc" / "config.yaml"
    if not config_file.exists():
        return None
    try:
        import yaml

        with open(config_file) as f:
            config = yaml.safe_load(f)
        return config.get("active_wallet") if isinstance(config, dict) else None
    except Exception:
        logger.debug("Failed to read active_wallet from config.yaml", exc_info=True)
        return None


def _resolve_wallet_address(wallet_name: str | None) -> str | None:
    """Resolve wallet address from local wallet files.

    Priority: explicit wallet_name arg > AITBC_DEFAULT_WALLET env var >
    active_wallet in ~/.aitbc/config.yaml > first wallet found.
    Searches the configured wallet directory plus the standard service
    directories (e.g. /var/lib/aitbc/wallets).
    """
    search_dirs = wallet_search_dirs()
    if not any(d.exists() for d in search_dirs):
        error(f"No wallet directory found in any of {search_dirs}")
        error("Create a wallet first: aitbc wallet create")
        return None

    # Resolve wallet name if not explicitly given
    if not wallet_name:
        wallet_name = _default_wallet_name()

    if wallet_name:
        wallet_file = find_wallet_file(wallet_name)
        if wallet_file is None:
            error(f"Wallet '{wallet_name}' not found")
            available = sorted({f.stem for d in search_dirs if d.exists() for f in d.glob("*.json")})
            error(f"Available wallets: {', '.join(available)}")
            error("Set AITBC_DEFAULT_WALLET env var or use --wallet to specify one")
            return None
    else:
        # 3. Fall back to first wallet found across all search directories
        wallet_files = sorted({f for d in search_dirs if d.exists() for f in d.glob("*.json")})
        if not wallet_files:
            error(f"No wallets found in {search_dirs}")
            error("Create a wallet first: aitbc wallet create")
            return None
        wallet_file = wallet_files[0]
        wallet_name = wallet_file.stem

    try:
        with open(wallet_file) as f:
            data = json.load(f)
        address = data.get("address")
        if not address:
            error(f"No address field in wallet file {wallet_file}")
            return None
        success(f"Using wallet '{wallet_name}': {address}")
        return str(address)
    except (json.JSONDecodeError, OSError) as e:
        error(f"Failed to read wallet file {wallet_file}: {e}")
        return None


@click.group(
    name="agent",
    epilog="""Examples:

  aitbc agent-msg ping --agent hub-coordinator

  aitbc agent-msg send --message 'hello' --to-agent agent-2""",
)
def messaging():
    """Send and receive messages, pings, and coin requests through the Agent Coordinator."""
    pass


def _resolve_agent_id(from_agent: str | None) -> str | None:
    """Return an explicit --from value or fall back to AGENT_ID."""
    return from_agent or os.getenv("AGENT_ID")


@messaging.command(
    epilog="""Examples:

  aitbc agent-msg send --message 'hello' --to-agent agent-2

  aitbc agent-msg send --message 'urgent' --to-agent agent-2 --priority high --ttl 60"""
)
@click.argument("message")
@click.option("--from-agent", "from_agent", help="Sender agent ID (default: $AGENT_ID)")
@click.option("--to-agent", required=True, help="Target agent ID")
@click.option("--priority", default="normal", show_default=True, help="Message priority")
@click.option("--message-id", help="Client-provided message ID for idempotent sends")
@click.option("--message-type", default="direct", show_default=True, help="Message type")
@click.option("--ttl", type=int, default=300, show_default=True, help="Time to live in seconds")
@click.option("--encrypt/--no-encrypt", default=True, show_default=True, help="Encrypt the message")
@click.option(
    "--wallet",
    "wallet_name",
    default=None,
    help="Wallet signing the message envelope (default: $AITBC_DEFAULT_WALLET); must be the sender's bound identity",
)
@click.option("--password", default=None, help="Wallet password")
@click.option("--sign/--no-sign", default=True, show_default=True, help="Sign the envelope when a wallet is configured")
@click.option("--coordinator-url", default=None, help="Agent Coordinator URL (default: from config)")
@click.pass_context
def send(
    ctx,
    message: str,
    from_agent: str | None,
    to_agent: str,
    priority: str,
    message_id: str | None,
    message_type: str,
    ttl: int,
    encrypt: bool,
    wallet_name: str | None,
    password: str | None,
    sign: bool,
    coordinator_url: str | None,
):
    """Send a direct or broadcast message to another agent through the coordinator."""
    config = get_config()
    base_url = (coordinator_url or config.agent_coordinator_url or "http://localhost:8107").rstrip("/")

    signing = load_signing_wallet(ctx, wallet_name=wallet_name, password=password) if sign else None

    try:
        http_client = AITBCHTTPClient(base_url=base_url, timeout=10)
    except Exception as e:
        error(f"Error creating coordinator client: {e}")
        return

    sender = _resolve_agent_id(from_agent)
    if signing is not None:
        # The wallet must be the sender's REGISTERED identity (doc §3/§5): the
        # coordinator rejects signed envelopes whose signer is not the bound
        # identity_address. Resolve or verify the binding before posting.
        address, private_key = signing
        if sender:
            binding_error = check_registry_binding(http_client, sender, address)
            if binding_error:
                error(binding_error)
                return
        else:
            sender = find_agent_by_identity(http_client, address)
            if not sender:
                error(
                    f"No --from-agent/$AGENT_ID and no registered agent is bound to wallet {address} — "
                    "pass --from-agent or register with `aitbc agent-comm register --wallet`"
                )
                return
            info(f"Resolved signing wallet to registered agent '{sender}'")
    if not sender:
        error("--from-agent is required when AGENT_ID is not set")
        return

    try:
        message_data: dict[str, Any] = {
            "sender": sender,
            "recipient": to_agent,
            "content": {"message": message},
            "message_type": message_type,
            "encrypt": encrypt,
            "priority": priority,
            "ttl": ttl,
        }
        if message_id:
            message_data["message_id"] = message_id
        if signing is not None:
            message_data = sign_send_envelope(message_data, signing[0], signing[1])

        result = http_client.post("/api/v1/agent/messages/send", json=message_data)
        success("Message sent via Agent Coordinator")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error sending message: {e}")


@messaging.command(
    epilog="""Examples:

  aitbc agent-msg receive

  aitbc agent-msg receive --from-agent agent-1 --unread-only --limit 10"""
)
@click.option("--from-agent", "from_agent", help="Agent ID whose inbox to read (default: $AGENT_ID)")
@click.option("--limit", type=int, default=20, show_default=True, help="Number of messages to return")
@click.option("--unread-only", is_flag=True, help="Only return unread messages")
@click.option(
    "--wallet",
    "wallet_name",
    default=None,
    help="Wallet signing the inbox request headers (default: $AITBC_DEFAULT_WALLET)",
)
@click.option("--password", default=None, help="Wallet password")
@click.option("--sign/--no-sign", default=True, show_default=True, help="Sign the request when a wallet is configured")
@click.option("--coordinator-url", default=None, help="Agent Coordinator URL (default: from config)")
@click.pass_context
def receive(
    ctx,
    from_agent: str | None,
    limit: int,
    unread_only: bool,
    wallet_name: str | None,
    password: str | None,
    sign: bool,
    coordinator_url: str | None,
):
    """Receive messages from the Agent Coordinator inbox for the configured agent."""
    config = get_config()
    agent_id = _resolve_agent_id(from_agent)
    if not agent_id:
        error("--from-agent is required when AGENT_ID is not set")
        return

    signing = load_signing_wallet(ctx, wallet_name=wallet_name, password=password) if sign else None

    base_url = (coordinator_url or config.agent_coordinator_url or "http://localhost:8107").rstrip("/")

    try:
        http_client = AITBCHTTPClient(base_url=base_url, timeout=10)
        params: dict[str, Any] = {"agent_id": agent_id, "limit": limit}
        if unread_only:
            params["unread_only"] = "true"
        headers = signed_request_headers(agent_id, signing[1]) if signing else None
        messages_data = http_client.get("/api/v1/agent/messages/inbox", params=params, headers=headers)
        success("Messages:")
        output(messages_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error receiving messages: {e}")


@messaging.command(
    epilog="""Examples:

  aitbc agent-msg peers

  aitbc agent-msg peers --coordinator-url http://hub.example.net:8107"""
)
@click.option("--coordinator-url", default=None, help="Agent Coordinator URL (default: from config)")
@click.pass_context
def peers(ctx, coordinator_url: str | None):
    """List the peers currently known to the Agent Coordinator."""
    config = get_config()
    base_url = (coordinator_url or config.agent_coordinator_url or "http://localhost:8107").rstrip("/")

    try:
        http_client = AITBCHTTPClient(base_url=base_url, timeout=10)
        peers_data = http_client.get("/api/v1/agent/messages/discover")
        success("Agent Coordinator Peers:")
        output(peers_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error fetching peers: {e}")


@messaging.command(
    epilog="""Examples:

  aitbc agent-msg ping --agent hub-coordinator

  aitbc agent-msg ping --agent shop-agent --sender hub-coordinator --timeout 10"""
)
@click.option("--agent", default="hub-coordinator", show_default=True, help="Recipient agent ID to ping")
@click.option(
    "--sender",
    default="follower",
    show_default=True,
    help="Sender agent ID (your agent ID for the WebSocket connection)",
)
@click.option(
    "--coordinator-url",
    default=None,
    help="Agent Coordinator URL. Direct: http://localhost:8107. Via nginx on the hub: https://hub.aitbc.bubuit.net/agent (default: from config agent_coordinator_url)",
)
@click.option("--timeout", type=int, default=10, show_default=True, help="Seconds to wait for a PONG reply")
@click.option(
    "--wallet",
    default=None,
    envvar="AITBC_DEFAULT_WALLET",
    help="Wallet to authenticate the stream with (mints an agent JWT via the coordinator login endpoint when --sender is bound to it)",
)
@click.option("--password", default=None, help="Password for --wallet")
@click.pass_context
def ping(ctx, agent: str, sender: str, coordinator_url: str | None, timeout: int, wallet: str | None, password: str | None):
    """Ping a remote agent via WebSocket and wait for its PONG reply."""
    config = get_config()
    base_url = (coordinator_url or config.agent_coordinator_url).rstrip("/")
    # With a configured wallet the stream authenticates as the bound agent via
    # an agent JWT (?token=<jwt>); otherwise the shared API key / user JWT is
    # used. Longer term the stream binds via a signed first-frame hello —
    # see _build_ws_url.
    api_key = (ctx.obj.get("api_key") if ctx.obj else None) or config.api_key
    token = _ws_auth_token(ctx, base_url, sender, wallet, password, api_key)
    ws_endpoint = _build_ws_url(base_url, sender, token=token)

    async def _ping() -> None:
        success(f"Connecting to {ws_endpoint}")
        try:
            async with websockets.connect(ws_endpoint, open_timeout=timeout) as ws:
                if not await _consume_connection_frame(ws, timeout, ws_endpoint):
                    return

                # Send PING frame
                ping_frame = {
                    "type": "message",
                    "payload": {"content": "PING", "recipient_id": agent},
                }
                await ws.send(json.dumps(ping_frame))
                success(f"PING sent to {agent}")

                # Read frames until we get PONG
                # Order is: PONG (from ping_handler), then handler_acknowledgment
                try:
                    while True:
                        reply_data = json.loads(await _asyncio.wait_for(ws.recv(), timeout=timeout))
                        if reply_data.get("type") == "PONG":
                            content = reply_data.get("content", "")
                            pong_sender = reply_data.get("sender", agent)
                            success(f"PONG received from {pong_sender}")
                            click.echo(f"  content: {content}")
                            if reply_data.get("timestamp"):
                                click.echo(f"  timestamp: {reply_data['timestamp']}")
                            return
                except _asyncio.TimeoutError:
                    error(f"No PONG from {agent} within {timeout}s")
        except WebSocketException as e:
            error(f"WebSocket error: {e}")
        except OSError as e:
            error(f"Connection failed to {ws_endpoint}: {e}")

    _asyncio.run(_ping())


@messaging.command(
    name="request-coins",
    epilog="""Examples:

  aitbc agent-msg request-coins

  aitbc agent-msg request-coins --wallet genesis --amount 100""",
)
@click.option(
    "--wallet",
    default=None,
    help="Wallet name to send coins to (default: auto-detect first available wallet)",
)
@click.option(
    "--amount",
    type=int,
    default=100,
    show_default=True,
    help="Amount of AIT to request (first request auto-grants 100; subsequent require manual approval)",
)
@click.option(
    "--sender",
    default="follower",
    show_default=True,
    help="Sender agent ID (your agent ID for the WebSocket connection)",
)
@click.option(
    "--coordinator-url",
    default=None,
    help="Agent Coordinator URL. Direct: http://localhost:8107. Via nginx on the hub: https://hub.aitbc.bubuit.net/agent (default: from config agent_coordinator_url)",
)
@click.option("--password", default=None, help="Password for --wallet when it also authenticates the stream")
@click.option("--timeout", type=int, default=15, show_default=True, help="Seconds to wait for a response")
@click.pass_context
def request_coins(
    ctx, wallet: str | None, amount: int, sender: str, coordinator_url: str | None, timeout: int, password: str | None
):
    """Request free AIT tokens from the hub via WebSocket for the configured wallet."""
    wallet_address = _resolve_wallet_address(wallet)
    if not wallet_address:
        return

    config = get_config()
    base_url = (coordinator_url or config.agent_coordinator_url).rstrip("/")
    # With a configured wallet the stream authenticates as the bound agent via
    # an agent JWT (the same wallet receives the coins); otherwise the shared
    # API key token is used. See _ws_auth_token.
    api_key = (ctx.obj.get("api_key") if ctx.obj else None) or config.api_key
    token = _ws_auth_token(ctx, base_url, sender, wallet, password, api_key)
    ws_endpoint = _build_ws_url(base_url, sender, token=token)

    async def _request() -> None:
        success(f"Connecting to {ws_endpoint}")
        try:
            async with websockets.connect(ws_endpoint, open_timeout=timeout) as ws:
                if not await _consume_connection_frame(ws, timeout, ws_endpoint):
                    return

                # Send REQUEST_COINS frame
                content = f'REQUEST_COINS {{"amount": {amount}, "wallet_address": "{wallet_address}"}}'
                request_frame = {
                    "type": "message",
                    "payload": {"content": content, "recipient_id": "hub-coordinator"},
                }
                await ws.send(json.dumps(request_frame))
                success(f"REQUEST_COINS sent ({amount} AIT to {wallet_address})")

                # Read frames until we get COINS_TRANSFERRED or a status response
                # Two response patterns:
                #   First-time: COINS_TRANSFERRED message (via send_personal_message)
                #   Subsequent: handler_acknowledgment with result.action = coin_request_received/pending_approval
                try:
                    while True:
                        reply_data = json.loads(await _asyncio.wait_for(ws.recv(), timeout=timeout))
                        msg_type = reply_data.get("type", "")

                        # Pattern 1: COINS_TRANSFERRED (auto-transfer, sent as separate message)
                        if msg_type == "COINS_TRANSFERRED":
                            tx_hash = reply_data.get("transaction_hash", "")
                            transferred = reply_data.get("amount", amount)
                            success(f"Received {transferred} AIT!")
                            click.echo(f"  wallet: {reply_data.get('wallet_address', wallet_address)}")
                            click.echo(f"  transaction: {tx_hash}")
                            if reply_data.get("timestamp"):
                                click.echo(f"  timestamp: {reply_data['timestamp']}")
                            click.echo(f"\nCheck balance: aitbc wallet balance {wallet or ''}".strip())
                            return

                        # Pattern 2: handler_acknowledgment with embedded result
                        if msg_type == "handler_acknowledgment":
                            results = reply_data.get("handler_results", {}).get("results", [])
                            for r in results:
                                result = r.get("result", {})
                                action = result.get("action", "")

                                if action == "coins_transferred":
                                    tx_hash = result.get("transaction_hash", "")
                                    transferred = result.get("amount", amount)
                                    success(f"Received {transferred} AIT!")
                                    click.echo(f"  wallet: {result.get('wallet_address', wallet_address)}")
                                    click.echo(f"  transaction: {tx_hash}")
                                    click.echo(f"\nCheck balance: aitbc wallet balance {wallet or ''}".strip())
                                    return

                                if action == "coin_request_received" and result.get("status") == "pending_approval":
                                    request_id = result.get("request_id", "")
                                    success("Request submitted — pending manual approval")
                                    if request_id:
                                        click.echo(f"  request_id: {request_id}")
                                    click.echo(f"  message: {result.get('message', '')}")
                                    click.echo("  The hub operator must approve this request.")
                                    if request_id:
                                        click.echo(f"\n  Hub operator: aitbc coin-requests approve {request_id}")
                                    return

                                if action == "coin_request_failed":
                                    err = result.get("error", "unknown error")
                                    detail = result.get("detail", "")
                                    error(f"Coin request failed: {err}")
                                    if detail:
                                        click.echo(f"  detail: {detail}")
                                    return

                except _asyncio.TimeoutError:
                    error(f"No response within {timeout}s")
        except WebSocketException as e:
            error(f"WebSocket error: {e}")
        except OSError as e:
            error(f"Connection failed to {ws_endpoint}: {e}")

    _asyncio.run(_request())


# Tests in tests/cli/ still import this module as `agent`; the CLI registers
# the same group under the name `agent-msg` in core/main.py.
agent = messaging
