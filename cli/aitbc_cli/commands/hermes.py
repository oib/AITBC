"""
Hermes training commands for AITBC CLI
"""

import asyncio as _asyncio
import datetime
import json
import os
import subprocess
import time
from pathlib import Path

import click
import websockets
from websockets.exceptions import WebSocketException

from ..config import get_config
from ..utils import error, output, success
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)

WALLET_DIR = Path.home() / ".aitbc" / "wallets"


def _build_ws_url(base_url: str, sender: str) -> str:
    """Build WebSocket endpoint URL from HTTP base URL and sender agent ID."""
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    return f"{ws_url}/api/v1/agent/messages/stream?agent_id={sender}"


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


def _resolve_wallet_address(wallet_name: str | None) -> str | None:
    """Resolve wallet address from local wallet files.

    Priority: explicit wallet_name arg > AITBC_DEFAULT_WALLET env var >
    active_wallet in ~/.aitbc/config.yaml > first wallet found.
    """
    if not WALLET_DIR.exists():
        error(f"No wallet directory found at {WALLET_DIR}")
        error("Create a wallet first: aitbc wallet create")
        return None

    # Resolve wallet name if not explicitly given
    if not wallet_name:
        # 1. Check AITBC_DEFAULT_WALLET env var
        wallet_name = os.environ.get("AITBC_DEFAULT_WALLET")
        # 2. Check config.yaml for active_wallet
        if not wallet_name:
            config_file = Path.home() / ".aitbc" / "config.yaml"
            if config_file.exists():
                try:
                    import yaml

                    with open(config_file) as f:
                        config = yaml.safe_load(f)
                        wallet_name = config.get("active_wallet") if isinstance(config, dict) else None
                except Exception:
                    pass

    if wallet_name:
        wallet_file = WALLET_DIR / f"{wallet_name}.json"
        if not wallet_file.exists():
            error(f"Wallet '{wallet_name}' not found at {wallet_file}")
            available = [f.stem for f in WALLET_DIR.glob("*.json")]
            error(f"Available wallets: {', '.join(available)}")
            error("Set AITBC_DEFAULT_WALLET env var or use --wallet to specify one")
            return None
    else:
        # 3. Fall back to first wallet found
        wallet_files = sorted(WALLET_DIR.glob("*.json"))
        if not wallet_files:
            error(f"No wallets found in {WALLET_DIR}")
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
        return address
    except (json.JSONDecodeError, OSError) as e:
        error(f"Failed to read wallet file {wallet_file}: {e}")
        return None


@click.group()
def hermes():
    """Hermes training operations commands"""
    pass


@hermes.command()
@click.option("--agent-id", required=True, help="Agent ID")
@click.option("--training-type", required=True, help="Type of training")
@click.option("--dataset", help="Dataset to use")
@click.option("--epochs", type=int, default=100, help="Number of training epochs")
@click.option("--batch-size", type=int, default=32, help="Batch size")
@click.option("--training-data", help="Path to training data JSON file")
@click.option("--stage", help="Training stage")
def train(
    agent_id: str,
    training_type: str,
    dataset: str | None,
    epochs: int,
    batch_size: int,
    training_data: str | None,
    stage: str | None,
):
    """Start Hermes training for an agent"""
    if training_data:
        if not os.path.exists(training_data):
            error(f"Training data file not found: {training_data}")
            return

        try:
            with open(training_data) as f:
                training_config = json.load(f)

            # Validate training data matches stage
            if stage and training_config.get("stage") != stage:
                error(f"Training data stage mismatch: expected {stage}, got {training_config.get('stage')}")
                return

            # Initialize logging
            log_dir = "/var/log/aitbc/agent-training"
            os.makedirs(log_dir, exist_ok=True)
            log_file = f"{log_dir}/agent_{agent_id}_{stage}_{int(time.time())}.log"

            # Execute training operations
            operations = training_config.get("training_data", {}).get("operations", [])
            completed_ops = 0
            failed_ops = 0

            success(f"Starting training for agent {agent_id}")
            success(f"Operations to execute: {len(operations)}")

            for i, op in enumerate(operations, 1):
                operation = op.get("operation")
                parameters = op.get("parameters", {})

                log_entry = {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "agent_id": agent_id,
                    "stage": stage,
                    "operation": operation,
                    "prompt": {"parameters": parameters, "expected_result": op.get("expected_result")},
                }

                # Execute training via hermes agent
                start_time = time.time()
                try:
                    prompt_message = f"Execute AITBC CLI command: {operation}"
                    if parameters:
                        prompt_message += f" with parameters: {json.dumps(parameters)}"

                    cmd = ["hermes", "agent", "--message", prompt_message, "--agent", "main"]

                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                    duration_ms = int((time.time() - start_time) * 1000)

                    if result.returncode == 0:
                        reply = {
                            "status": "completed",
                            "result": result.stdout.strip() if result.stdout else "Command executed successfully",
                            "cli_output": result.stdout.strip(),
                        }
                        log_entry["status"] = "completed"
                        completed_ops += 1
                        success(f"Operation {i}/{len(operations)}: {operation} - completed ({duration_ms}ms)")
                    else:
                        reply = {
                            "status": "error",
                            "error": result.stderr.strip() if result.stderr else "Command failed",
                            "cli_output": result.stdout.strip(),
                            "cli_error": result.stderr.strip(),
                        }
                        log_entry["status"] = "failed"
                        failed_ops += 1
                        error(f"Operation {i}/{len(operations)}: {operation} - failed")

                    log_entry["reply"] = reply
                    log_entry["duration_ms"] = duration_ms

                    # Write log entry
                    with open(log_file, "a") as f:
                        f.write(json.dumps(log_entry) + "\n")

                except subprocess.TimeoutExpired:
                    duration_ms = int((time.time() - start_time) * 1000)
                    reply = {"status": "error", "error": "Command timed out after 30 seconds"}
                    log_entry["status"] = "failed"
                    log_entry["reply"] = reply
                    log_entry["duration_ms"] = duration_ms
                    failed_ops += 1
                    error(f"Operation {i}/{len(operations)}: {operation} - timed out")

                    with open(log_file, "a") as f:
                        f.write(json.dumps(log_entry) + "\n")
                except Exception as e:
                    error(f"Operation {i}/{len(operations)}: {operation} - exception: {e}")
                    failed_ops += 1

            success(f"Training completed: {completed_ops}/{len(operations)} successful")
            success(f"Log file: {log_file}")

        except Exception as e:
            error(f"Error loading training data: {e}")
    else:
        success(f"Start {training_type} training for agent {agent_id}")
        success(f"Epochs: {epochs}, Batch size: {batch_size}")


@hermes.command()
@click.option("--agent-id", help="Agent ID")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
def status(agent_id: str | None, format: str):
    """Get Hermes training status"""
    try:
        import httpx

        config = get_config()
        coordinator_url = config.get("coordinator_url", "http://localhost:8203")
        api_key = config.get("coordinator_api_key")

        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        if agent_id:
            response = httpx.get(f"{coordinator_url}/v1/hermes/agents/{agent_id}/status", headers=headers)
        else:
            response = httpx.get(f"{coordinator_url}/v1/hermes/status", headers=headers)

        if response.status_code != 200:
            error(f"Failed to get Hermes status: {response.text}")
            return

        result = response.json()

        success(f"Get Hermes training status for agent {agent_id}")

        if format == "json":
            click.echo(json.dumps(result, indent=2))
        else:
            if agent_id:
                click.echo(f"Agent ID: {agent_id}")
                click.echo(f"Status: {result.get('status', 'Unknown')}")
                click.echo(f"Training Progress: {result.get('progress', 0)}%")
                click.echo(f"Epoch: {result.get('epoch', 0)}")
                click.echo(f"Loss: {result.get('loss', 'N/A')}")
            else:
                click.echo(f"Active Agents: {result.get('active_agents', 0)}")
                click.echo(f"Total Jobs: {result.get('total_jobs', 0)}")

    except Exception as e:
        error(f"Error getting Hermes status: {e}")


@hermes.command()
@click.option("--agent-id", help="Agent ID")
def stop(agent_id: str | None):
    """Stop Hermes training"""
    try:
        import httpx

        if not agent_id:
            error("Agent ID required")
            return

        config = get_config()
        coordinator_url = config.get("coordinator_url", "http://localhost:8203")
        api_key = config.get("coordinator_api_key")

        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        response = httpx.post(f"{coordinator_url}/v1/hermes/agents/{agent_id}/stop", headers=headers)

        if response.status_code != 200:
            error(f"Failed to stop Hermes training: {response.text}")
            return

        success(f"Stop Hermes training for agent {agent_id}")
        click.echo("Status: Stopped")

    except Exception as e:
        error(f"Error stopping Hermes training: {e}")


@hermes.command()
@click.argument("message")
@click.option("--to-agent", help="Target agent ID")
@click.option("--priority", default="normal", help="Message priority")
@click.pass_context
def send(ctx, message: str, to_agent: str | None, priority: str):
    """Send a message via hermes service"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.hermes_service_url, timeout=10)
        message_data = {"message": message, "priority": priority}
        if to_agent:
            message_data["to_agent"] = to_agent

        result = http_client.post("/hermes/send", json=message_data)
        success("Message sent via hermes")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error sending message: {e}")


@hermes.command()
@click.option("--limit", type=int, default=20, help="Number of messages to return")
@click.pass_context
def receive(ctx, limit: int):
    """Receive messages from hermes service"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.hermes_service_url, timeout=10)
        messages_data = http_client.get("/hermes/messages", params={"limit": limit})
        success("Messages:")
        output(messages_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error receiving messages: {e}")


@hermes.command()
@click.pass_context
def peers(ctx):
    """List hermes service peers"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.hermes_service_url, timeout=10)
        peers_data = http_client.get("/hermes/peers")
        success("Hermes Peers:")
        output(peers_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error fetching peers: {e}")


@hermes.command()
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
@click.pass_context
def ping(ctx, agent: str, sender: str, coordinator_url: str | None, timeout: int):
    """Ping a remote Hermes agent via WebSocket and wait for its PONG reply.

    Connects to the Agent Coordinator's WebSocket stream
    (/api/v1/agent/messages/stream?agent_id=<sender>), sends a PING message
    to the target agent, and waits for the automatic PONG response from the
    coordinator's built-in ping_handler.
    """
    config = get_config()
    base_url = (coordinator_url or config.agent_coordinator_url).rstrip("/")
    ws_endpoint = _build_ws_url(base_url, sender)

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


@hermes.command(name="request-coins")
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
@click.option("--timeout", type=int, default=15, show_default=True, help="Seconds to wait for a response")
@click.pass_context
def request_coins(ctx, wallet: str | None, amount: int, sender: str, coordinator_url: str | None, timeout: int):
    """Request free AIT tokens from the hub via WebSocket.

    Sends a REQUEST_COINS message to the hub's Agent Coordinator. First-time
    requests are auto-approved and 100 AIT is transferred immediately. Subsequent
    requests return pending_approval and require manual approval by the hub operator.

    The wallet address is auto-detected from local wallet files (~/.aitbc/wallets/).
    Use --wallet to specify a particular wallet by name.
    """
    wallet_address = _resolve_wallet_address(wallet)
    if not wallet_address:
        return

    config = get_config()
    base_url = (coordinator_url or config.agent_coordinator_url).rstrip("/")
    ws_endpoint = _build_ws_url(base_url, sender)

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
                                    success("Request submitted — pending manual approval")
                                    click.echo(f"  message: {result.get('message', '')}")
                                    click.echo("  The hub operator must approve this request.")
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
