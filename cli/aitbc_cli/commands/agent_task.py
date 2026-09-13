"""Paid agent-to-agent task delegation for AITBC CLI (v0.25 Phase 3).

A buyer agent hires a provider agent through the hub agent-coordinator:

    hire   → payload to island IPFS → signed escrow lock → /v1/tasks/submit
             → TaskRequest message → provider quotes → TaskAccept
             → provider executes → TaskResult (result CID) → escrow release
    status → escrow state + negotiation messages for a task
    result → fetch the task result CID via the local island IPFS daemon

The negotiation messages ride ``/api/v1/agent/messages`` unencrypted — they
carry CIDs and prices, not secrets. Escrow settlement goes through the same
``/rpc/escrow/*`` chain routes the marketplace uses.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import click

from aitbc.utils.units import ait_to_units

from ..config import get_config
from ..utils import error, info, output, success, warning
from ..utils.http_client import AITBCHTTPClient, get_logger
from ..utils.wallet_loader import load_wallet_for_payment
from .ipfs import _daemon_available, _ipfs_add_file, _is_cid
from .market.escrow import _get_blockchain_rpc_url
from .market.host import _resolve_ipfs_api

logger = get_logger(__name__)

DEFAULT_COORDINATOR_URL = "https://hub.aitbc.bubuit.net"


def _coordinator_url(ctx, coordinator_url: str | None) -> str:
    url = coordinator_url or os.environ.get("AGENT_COORDINATOR_URL") or get_config().agent_coordinator_url
    if not url:
        url = DEFAULT_COORDINATOR_URL
    return str(url).rstrip("/")


def _buyer_agent_id(from_agent: str | None) -> str:
    agent_id = from_agent or os.environ.get("AGENT_ID") or f"buyer-{os.uname().nodename}"
    return agent_id


def _send_task_message(
    client: AITBCHTTPClient, sender: str, recipient: str, message_type: str, content: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        return client.post(
            "/api/v1/agent/messages/send",
            json={
                "sender": sender,
                "recipient": recipient,
                "content": content,
                "message_type": message_type,
                "encrypt": False,
                "ttl": 3600,
            },
        )
    except Exception as e:
        warning(f"Failed to send {message_type}: {e}")
        return None


def _inbox(client: AITBCHTTPClient, agent_id: str, unread_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"agent_id": agent_id, "limit": limit}
    if unread_only:
        params["unread_only"] = "true"
    try:
        data = client.get("/api/v1/agent/messages/inbox", params=params)
    except Exception as e:
        warning(f"Inbox poll failed: {e}")
        return []
    messages = data.get("messages", []) if isinstance(data, dict) else []
    return [m for m in messages if isinstance(m, dict)]


def _message_content(message: dict[str, Any]) -> dict[str, Any] | None:
    import json

    content = message.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return None
    return content if isinstance(content, dict) else None


def _find_task_messages(messages: list[dict[str, Any]], task_id: str) -> dict[str, dict[str, Any]]:
    """Return {message_type: content} for delegation messages about task_id."""
    found: dict[str, dict[str, Any]] = {}
    for message in messages:
        mtype = str(message.get("message_type", ""))
        if not mtype.startswith("task_"):
            continue
        content = _message_content(message)
        if content and content.get("task_id") == task_id:
            found.setdefault(mtype, content)
    return found


def _resolve_provider_wallet(client: AITBCHTTPClient, agent_id: str) -> str | None:
    try:
        data = client.get(f"/v1/agents/{agent_id}")
    except Exception as e:
        error(f"Could not look up agent {agent_id}: {e}")
        return None
    agent = data.get("agent", {}) if isinstance(data, dict) else {}
    wallet = (agent.get("metadata") or {}).get("wallet") or (agent.get("endpoints") or {}).get("wallet")
    if not wallet:
        error(f"Agent {agent_id} has no wallet in its registry metadata — cannot escrow payment")
        return None
    return cast(str, wallet)


def _resolve_payload_ref(ctx, payload: str) -> str | None:
    """Return a CID for --payload: pass-through for CIDs, `ipfs add` for files."""
    if _is_cid(payload):
        return payload
    path = Path(payload)
    if not path.is_file():
        error(f"--payload must be an IPFS CID or a local file path (got: {payload})")
        return None
    ipfs_api = _resolve_ipfs_api({})
    if not _daemon_available(ipfs_api):
        error(f"No local island IPFS daemon reachable at {ipfs_api} — cannot upload payload")
        return None
    cid = _ipfs_add_file(ipfs_api, path)
    if not cid:
        error(f"IPFS add failed for {path}")
        return None
    info(f"Payload uploaded: {cid}")
    return cid


@click.group(
    name="agent-task",
    epilog="""Examples:

  aitbc agent-task hire --to-agent aitbc-miner-1 --service-type whisper --payload ./audio.wav --max-price 0.05

  aitbc agent-task status --task-id <id>

  aitbc agent-task result --task-id <id> --out transcript.json""",
)
def agent_task():
    """Hire provider agents for paid tasks (agent-to-agent delegation)."""
    pass


@agent_task.command()
@click.option("--to-agent", "to_agent", required=True, help="Provider agent ID (registry)")
@click.option("--service-type", required=True, help="Service to run (whisper, ffmpeg, ollama, ipfs)")
@click.option("--model", default=None, help="Model/variant (e.g. base, llama3.2:3b)")
@click.option("--payload", "payload", required=True, help="Task input: IPFS CID or local file path")
@click.option("--max-price", "max_price", required=True, help="Maximum price in AIT")
@click.option("--wallet", "wallet_name", default=None, help="Buyer wallet name (signs the escrow lock)")
@click.option("--password", default=None, help="Wallet password")
@click.option("--from-agent", "from_agent", default=None, help="Buyer agent ID (default: $AGENT_ID or buyer-<hostname>)")
@click.option("--timeout", "timeout_seconds", type=float, default=1800.0, show_default=True, help="Escrow timeout in seconds")
@click.option("--wait/--no-wait", default=True, show_default=True, help="Wait for the task result")
@click.option("--wait-seconds", type=float, default=900.0, show_default=True, help="Max time to wait for a result")
@click.option("--coordinator-url", default=None, help="Agent coordinator URL (default: $AGENT_COORDINATOR_URL or hub)")
@click.pass_context
def hire(
    ctx,
    to_agent: str,
    service_type: str,
    model: str | None,
    payload: str,
    max_price: str,
    wallet_name: str | None,
    password: str | None,
    from_agent: str | None,
    timeout_seconds: float,
    wait: bool,
    wait_seconds: float,
    coordinator_url: str | None,
):
    """Hire a provider agent: escrow locks on-chain, task runs, result returns as a CID."""
    config = get_config()
    base_url = _coordinator_url(ctx, coordinator_url)
    client = AITBCHTTPClient(base_url=base_url, timeout=30)
    buyer_agent = _buyer_agent_id(from_agent)

    try:
        max_price_ait = Decimal(str(max_price))
    except Exception:
        error(f"Invalid --max-price: {max_price}")
        raise click.Abort() from None
    if max_price_ait <= 0:
        error("--max-price must be positive")
        raise click.Abort()

    # 1. Payload → CID on the buyer's island daemon.
    payload_ref = _resolve_payload_ref(ctx, payload)
    if not payload_ref:
        raise click.Abort()

    # 2. Provider wallet from the agent registry (executor publishes it).
    provider_wallet = _resolve_provider_wallet(client, to_agent)
    if not provider_wallet:
        raise click.Abort()

    # 3. Settlement wallet: the coordinator settles through its configured
    #    blockchain RPC's node wallet. Ask the coordinator first (correct on
    #    any node); fall back to the market convention — HUB_PROPOSER_ID, then
    #    the local RPC's node wallet (right only when buyer == hub).
    settlement_wallet = None
    try:
        esc_conf = client.get("/v1/tasks/escrow-config")
        if isinstance(esc_conf, dict) and esc_conf.get("settlement_wallet"):
            settlement_wallet = str(esc_conf["settlement_wallet"])
    except Exception:
        pass
    rpc_url = _get_blockchain_rpc_url(config)
    if not settlement_wallet:
        settlement_wallet = getattr(config, "hub_proposer_id", None) or None
    if not settlement_wallet:
        from ..utils.escrow import get_node_wallet

        try:
            settlement_wallet = get_node_wallet(ctx, rpc_url)
        except Exception:
            settlement_wallet = None
    if not settlement_wallet:
        error(
            "No escrow settlement wallet available — coordinator /v1/tasks/escrow-config unreachable and HUB_PROPOSER_ID unset"
        )
        raise click.Abort()

    # 4. Buyer wallet + signed escrow lock for max_price.
    buyer_address, private_key, _ = load_wallet_for_payment(ctx, wallet_name=wallet_name, password=password)
    if not private_key:
        error("Escrow lock requires a buyer wallet with a private key")
        raise click.Abort()

    task_id = f"atask_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    from ..utils.escrow import create_signed_escrow_lock

    try:
        lock_tx, lock_signature = create_signed_escrow_lock(
            ctx,
            rpc_url,
            task_id,
            buyer_address,
            provider_wallet,
            max_price_ait,
            private_key,
            node_wallet=settlement_wallet,
        )
    except Exception as e:
        error(f"Failed to build escrow lock transaction: {e}")
        raise click.Abort() from e

    # 5. Submit task + payment: the coordinator locks the escrow on-chain.
    amount_units = ait_to_units(max_price_ait)
    try:
        submission = client.post(
            "/v1/tasks/submit",
            json={
                "task_data": {
                    "task_id": task_id,
                    "service_type": service_type,
                    "model": model,
                    "payload_ref": payload_ref,
                    "to_agent": to_agent,
                    "buyer_agent": buyer_agent,
                },
                "priority": "normal",
                "payment": {
                    "requester": buyer_address,
                    "agent": provider_wallet,
                    "amount": amount_units,
                    "timeout_seconds": timeout_seconds,
                    "lock_tx": lock_tx,
                    "lock_signature": lock_signature,
                },
            },
        )
    except Exception as e:
        error(f"Task submission failed: {e}")
        raise click.Abort() from e
    escrow_id = submission.get("escrow_id") if isinstance(submission, dict) else None
    if not escrow_id:
        error(f"Task submitted but no escrow was created — is TASK_PAYMENT_ESCROW_ENABLED on the coordinator? {submission}")
        raise click.Abort()
    success(f"Task {task_id} submitted — escrow {escrow_id} locked on-chain ({max_price_ait} AIT)")

    # 5. Send the TaskRequest negotiation message.
    request_msg = {
        "task_id": task_id,
        "service_type": service_type,
        "model": model,
        "payload_ref": payload_ref,
        "max_price": str(max_price_ait),
        "deadline": None,
        "escrow_id": escrow_id,
    }
    if not _send_task_message(client, buyer_agent, to_agent, "task_request", request_msg):
        error("Escrow is locked but TaskRequest delivery failed — use `agent-task status` to inspect")
        raise click.Abort()
    info(f"TaskRequest sent to {to_agent}")

    if not wait:
        output(
            {"task_id": task_id, "escrow_id": escrow_id, "payload_ref": payload_ref},
            ctx.obj.get("output_format", "table"),
        )
        return

    # 6. Wait for quote → auto-accept → result.
    deadline = time.time() + wait_seconds
    accepted = False
    while time.time() < deadline:
        found = _find_task_messages(_inbox(client, buyer_agent), task_id)
        if "task_reject" in found:
            error(f"Provider rejected the task: {found['task_reject'].get('reason', '')}")
            return
        if not accepted and "task_quote" in found:
            quote = found["task_quote"]
            try:
                quoted = Decimal(str(quote.get("price", "0")))
            except Exception:
                quoted = max_price_ait
            if quoted <= max_price_ait:
                info(f"Quote received: {quoted} AIT — accepting")
                _send_task_message(
                    client,
                    buyer_agent,
                    to_agent,
                    "task_accept",
                    {"task_id": task_id, "escrow_id": escrow_id, "offer_id": quote.get("offer_id")},
                )
                accepted = True
            else:
                warning(f"Quote {quoted} exceeds max price — leaving escrow to expire")
                return
        if "task_result" in found:
            result = found["task_result"]
            paid = found.get("task_paid", {})
            success(f"Task {task_id} finished: {result.get('status')}")
            output(
                {
                    "task_id": task_id,
                    "status": result.get("status"),
                    "result_ref": result.get("result_ref"),
                    "result_hash": result.get("result_hash"),
                    "tx_hash": paid.get("tx_hash"),
                },
                ctx.obj.get("output_format", "table"),
            )
            return
        time.sleep(5)
    warning(f"Timed out waiting for result after {wait_seconds}s — escrow will refund on expiry")
    output({"task_id": task_id, "escrow_id": escrow_id, "status": "waiting"}, ctx.obj.get("output_format", "table"))


@agent_task.command()
@click.option("--task-id", "task_id", required=True, help="Task identifier")
@click.option("--from-agent", "from_agent", default=None, help="Buyer agent ID (default: $AGENT_ID or buyer-<hostname>)")
@click.option("--coordinator-url", default=None, help="Agent coordinator URL")
@click.pass_context
def status(ctx, task_id: str, from_agent: str | None, coordinator_url: str | None):
    """Show escrow state and negotiation progress for a task."""
    base_url = _coordinator_url(ctx, coordinator_url)
    client = AITBCHTTPClient(base_url=base_url, timeout=15)
    buyer_agent = _buyer_agent_id(from_agent)

    escrow: dict[str, Any] | None = None
    try:
        data = client.get(f"/v1/tasks/{task_id}/escrow")
        escrow = data.get("escrow") if isinstance(data, dict) else None
    except Exception as e:
        warning(f"Escrow lookup failed: {e}")

    found = _find_task_messages(_inbox(client, buyer_agent), task_id)
    output(
        {
            "task_id": task_id,
            "escrow": escrow,
            "negotiation": dict(found.items()),
        },
        ctx.obj.get("output_format", "table"),
        title=f"Agent task {task_id}",
    )


@agent_task.command()
@click.option("--task-id", "task_id", required=True, help="Task identifier")
@click.option("--out", "out_path", default=None, help="Output file path (default: print to stdout)")
@click.option("--from-agent", "from_agent", default=None, help="Buyer agent ID")
@click.option("--coordinator-url", default=None, help="Agent coordinator URL")
@click.pass_context
def result(ctx, task_id: str, out_path: str | None, from_agent: str | None, coordinator_url: str | None):
    """Fetch a finished task's result payload from island IPFS."""
    base_url = _coordinator_url(ctx, coordinator_url)
    client = AITBCHTTPClient(base_url=base_url, timeout=15)
    buyer_agent = _buyer_agent_id(from_agent)

    found = _find_task_messages(_inbox(client, buyer_agent), task_id)
    task_result = found.get("task_result")
    if not task_result or not task_result.get("result_ref"):
        error(f"No result for task {task_id} yet (status: {task_result.get('status') if task_result else 'pending'})")
        raise click.Abort()

    result_ref = task_result["result_ref"]
    ipfs_api = _resolve_ipfs_api({})
    if not _daemon_available(ipfs_api):
        error(f"No local island IPFS daemon reachable at {ipfs_api}")
        raise click.Abort()
    import requests as _requests

    try:
        resp = _requests.post(f"{ipfs_api}/api/v0/cat", params={"arg": result_ref}, timeout=120)
        resp.raise_for_status()
    except Exception as e:
        error(f"Could not fetch result {result_ref}: {e}")
        raise click.Abort() from e

    data = resp.content
    expected = task_result.get("result_hash")
    actual = hashlib.sha256(data).hexdigest()
    if expected and expected != actual:
        warning(f"Result hash mismatch: expected {expected}, got {actual}")
    if out_path:
        Path(out_path).write_bytes(data)
        success(f"Result written to {out_path} ({len(data)} bytes, sha256={actual[:16]}…)")
    else:
        try:
            click.echo(data.decode())
        except UnicodeDecodeError:
            click.echo(data.hex())


__all__ = ["agent_task"]
