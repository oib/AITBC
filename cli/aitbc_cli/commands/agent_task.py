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
from urllib.parse import urlparse

import click

from aitbc.utils.units import ait_to_units

from ..config import get_config
from ..utils import error, info, output, success, warning
from ..utils.agent_signing import (
    check_registry_binding,
    load_signing_wallet,
    sign_send_envelope,
    signed_request_headers,
)
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
    # Every call site in this module carries its own absolute path
    # (``/v1/...``, ``/api/v1/agent/messages/...``), and nginx mounts those at
    # the origin root — so reduce the configured URL to scheme://host[:port].
    # ``get_config().agent_coordinator_url`` resolves via ``hub_agent_url()``,
    # which includes the ``/api/v1/agent`` prefix and would produce doubled
    # paths like ``/api/v1/agent/v1/agents/...`` (routed to the gateway → 401).
    parsed = urlparse(str(url))
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return str(url).rstrip("/")


def _buyer_agent_id(from_agent: str | None) -> str:
    agent_id = from_agent or os.environ.get("AGENT_ID") or f"buyer-{os.uname().nodename}"
    return agent_id


def _send_task_message(
    client: AITBCHTTPClient,
    sender: str,
    recipient: str,
    message_type: str,
    content: dict[str, Any],
    signing: tuple[str, str] | None = None,
) -> dict[str, Any] | None:
    """POST a task negotiation message, optionally as a §4 signed envelope.

    ``signing`` is ``(signer_address, private_key)`` — the buyer wallet in
    ``hire``. When it is ``None`` the message goes out unsigned, which the
    coordinator still accepts while AGENT_MSG_SIGNATURE_MODE is
    disabled/advisory.
    """
    body: dict[str, Any] = {
        "sender": sender,
        "recipient": recipient,
        "content": content,
        "message_type": message_type,
        "encrypt": False,
        "ttl": 3600,
    }
    if signing is not None:
        address, private_key = signing
        body = sign_send_envelope(body, address, private_key)
    try:
        return client.post("/api/v1/agent/messages/send", json=body)
    except Exception as e:
        warning(f"Failed to send {message_type}: {e}")
        return None


def _inbox(
    client: AITBCHTTPClient,
    agent_id: str,
    unread_only: bool = False,
    limit: int = 100,
    signing_key: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"agent_id": agent_id, "limit": limit}
    if unread_only:
        params["unread_only"] = "true"
    headers = signed_request_headers(agent_id, signing_key) if signing_key else None
    try:
        data = client.get("/api/v1/agent/messages/inbox", params=params, headers=headers)
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


def _parse_max_price(max_price: str) -> Decimal:
    """Parse --max-price as a positive AIT amount or abort."""
    try:
        max_price_ait = Decimal(str(max_price))
    except Exception:
        error(f"Invalid --max-price: {max_price}")
        raise click.Abort() from None
    if max_price_ait <= 0:
        error("--max-price must be positive")
        raise click.Abort()
    return max_price_ait


def _settlement_wallet(client: AITBCHTTPClient, config, ctx, rpc_url: str) -> str | None:
    """Resolve the escrow settlement wallet, or None when none is configured.

    The coordinator settles through its configured blockchain RPC's node
    wallet. Ask the coordinator first (correct on any node); fall back to the
    market convention — HUB_PROPOSER_ID, then the local RPC's node wallet
    (right only when buyer == hub).
    """
    settlement_wallet = None
    try:
        esc_conf = client.get("/v1/tasks/escrow-config")
        if isinstance(esc_conf, dict) and esc_conf.get("settlement_wallet"):
            settlement_wallet = str(esc_conf["settlement_wallet"])
    except Exception:
        pass
    if not settlement_wallet:
        settlement_wallet = getattr(config, "hub_proposer_id", None) or None
    if not settlement_wallet:
        from ..utils.escrow import get_node_wallet

        try:
            settlement_wallet = get_node_wallet(ctx, rpc_url)
        except Exception:
            settlement_wallet = None
    return settlement_wallet


def _buyer_signing(
    ctx,
    client: AITBCHTTPClient,
    buyer_agent: str,
    wallet_name: str | None,
    password: str | None,
    sign: bool,
) -> tuple[str, str, tuple[str, str] | None, str | None]:
    """Load the buyer wallet and derive the signing material for this hire.

    Returns (buyer_address, private_key, signing, signing_key). The same wallet
    signs every negotiation envelope (doc §4) and the X-Agent-* inbox-poll
    headers. ``--no-sign`` keeps the unsigned behaviour for coordinators still
    running with AGENT_MSG_SIGNATURE_MODE=disabled.
    """
    buyer_address, private_key, _ = load_wallet_for_payment(ctx, wallet_name=wallet_name, password=password)
    if not private_key:
        error("Escrow lock requires a buyer wallet with a private key")
        raise click.Abort()

    signing = (buyer_address, private_key) if sign else None
    signing_key = private_key if sign else None
    if signing is not None:
        # Soft check only: the coordinator still accepts while advisory, and a
        # registry lookup failure must not block the escrowed hire.
        binding_note = check_registry_binding(client, buyer_agent, buyer_address)
        if binding_note:
            warning(f"{binding_note} — signed envelopes may be rejected once the coordinator enforces")
    return buyer_address, private_key, signing, signing_key


def _submit_task(
    ctx,
    client: AITBCHTTPClient,
    rpc_url: str,
    task_id: str,
    service_type: str,
    model: str | None,
    payload_ref: str,
    to_agent: str,
    buyer_agent: str,
    buyer_address: str,
    provider_wallet: str,
    max_price_ait: Decimal,
    private_key: str,
    settlement_wallet: str,
    timeout_seconds: float,
) -> str:
    """Build the signed escrow lock and POST /v1/tasks/submit; return the escrow id."""
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
                    # Same shape market escrow uses: signature embedded in the tx.
                    "lock_tx": {**lock_tx, "signature": lock_signature},
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
    return cast(str, escrow_id)


def _wait_for_task_result(
    ctx,
    client: AITBCHTTPClient,
    buyer_agent: str,
    to_agent: str,
    task_id: str,
    escrow_id: str,
    max_price_ait: Decimal,
    signing: tuple[str, str] | None,
    signing_key: str | None,
    wait_seconds: float,
) -> None:
    """Poll the buyer inbox: auto-accept an affordable quote, then report the result."""
    deadline = time.time() + wait_seconds
    accepted = False
    while time.time() < deadline:
        found = _find_task_messages(_inbox(client, buyer_agent, signing_key=signing_key), task_id)
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
                    signing=signing,
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
@click.option(
    "--sign/--no-sign",
    default=True,
    show_default=True,
    help="Sign negotiation envelopes and inbox polls with the buyer wallet",
)
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
    sign: bool,
    coordinator_url: str | None,
):
    """Hire a provider agent: escrow locks on-chain, task runs, result returns as a CID."""
    config = get_config()
    base_url = _coordinator_url(ctx, coordinator_url)
    client = AITBCHTTPClient(base_url=base_url, timeout=30)
    buyer_agent = _buyer_agent_id(from_agent)
    max_price_ait = _parse_max_price(max_price)

    # 1. Payload → CID on the buyer's island daemon.
    payload_ref = _resolve_payload_ref(ctx, payload)
    if not payload_ref:
        raise click.Abort()

    # 2. Provider wallet from the agent registry (executor publishes it).
    provider_wallet = _resolve_provider_wallet(client, to_agent)
    if not provider_wallet:
        raise click.Abort()

    # 3. Settlement wallet: see _settlement_wallet for the lookup order.
    rpc_url = _get_blockchain_rpc_url(config)
    settlement_wallet = _settlement_wallet(client, config, ctx, rpc_url)
    if not settlement_wallet:
        error(
            "No escrow settlement wallet available — coordinator /v1/tasks/escrow-config unreachable and HUB_PROPOSER_ID unset"
        )
        raise click.Abort()

    # 4. Buyer wallet + signing material for the escrow lock and envelopes.
    buyer_address, private_key, signing, signing_key = _buyer_signing(ctx, client, buyer_agent, wallet_name, password, sign)

    task_id = f"atask_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    # 5. Submit task + payment: the coordinator locks the escrow on-chain.
    escrow_id = _submit_task(
        ctx,
        client,
        rpc_url,
        task_id,
        service_type,
        model,
        payload_ref,
        to_agent,
        buyer_agent,
        buyer_address,
        provider_wallet,
        max_price_ait,
        private_key,
        settlement_wallet,
        timeout_seconds,
    )
    success(f"Task {task_id} submitted — escrow {escrow_id} locked on-chain ({max_price_ait} AIT)")

    # 6. Send the TaskRequest negotiation message.
    request_msg = {
        "task_id": task_id,
        "service_type": service_type,
        "model": model,
        "payload_ref": payload_ref,
        "max_price": str(max_price_ait),
        "deadline": None,
        "escrow_id": escrow_id,
    }
    if not _send_task_message(client, buyer_agent, to_agent, "task_request", request_msg, signing=signing):
        error("Escrow is locked but TaskRequest delivery failed — use `agent-task status` to inspect")
        raise click.Abort()
    info(f"TaskRequest sent to {to_agent}")

    if not wait:
        output(
            {"task_id": task_id, "escrow_id": escrow_id, "payload_ref": payload_ref},
            ctx.obj.get("output_format", "table"),
        )
        return

    # 7. Wait for quote → auto-accept → result.
    _wait_for_task_result(
        ctx, client, buyer_agent, to_agent, task_id, escrow_id, max_price_ait, signing, signing_key, wait_seconds
    )


@agent_task.command()
@click.option("--task-id", "task_id", required=True, help="Task identifier")
@click.option("--from-agent", "from_agent", default=None, help="Buyer agent ID (default: $AGENT_ID or buyer-<hostname>)")
@click.option("--wallet", "wallet_name", default=None, help="Wallet signing the inbox poll (default: $AITBC_DEFAULT_WALLET)")
@click.option("--password", default=None, help="Wallet password")
@click.option("--sign/--no-sign", default=True, show_default=True, help="Sign the inbox poll when a wallet is configured")
@click.option("--coordinator-url", default=None, help="Agent coordinator URL")
@click.pass_context
def status(
    ctx,
    task_id: str,
    from_agent: str | None,
    wallet_name: str | None,
    password: str | None,
    sign: bool,
    coordinator_url: str | None,
):
    """Show escrow state and negotiation progress for a task."""
    base_url = _coordinator_url(ctx, coordinator_url)
    client = AITBCHTTPClient(base_url=base_url, timeout=15)
    buyer_agent = _buyer_agent_id(from_agent)

    signing_key = None
    if sign:
        wallet = load_signing_wallet(ctx, wallet_name=wallet_name, password=password)
        signing_key = wallet[1] if wallet else None

    escrow: dict[str, Any] | None = None
    try:
        data = client.get(f"/v1/tasks/{task_id}/escrow")
        escrow = data.get("escrow") if isinstance(data, dict) else None
    except Exception as e:
        warning(f"Escrow lookup failed: {e}")

    found = _find_task_messages(_inbox(client, buyer_agent, signing_key=signing_key), task_id)
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
@click.option("--wallet", "wallet_name", default=None, help="Wallet signing the inbox poll (default: $AITBC_DEFAULT_WALLET)")
@click.option("--password", default=None, help="Wallet password")
@click.option("--sign/--no-sign", default=True, show_default=True, help="Sign the inbox poll when a wallet is configured")
@click.option("--coordinator-url", default=None, help="Agent coordinator URL")
@click.pass_context
def result(
    ctx,
    task_id: str,
    out_path: str | None,
    from_agent: str | None,
    wallet_name: str | None,
    password: str | None,
    sign: bool,
    coordinator_url: str | None,
):
    """Fetch a finished task's result payload from island IPFS."""
    base_url = _coordinator_url(ctx, coordinator_url)
    client = AITBCHTTPClient(base_url=base_url, timeout=15)
    buyer_agent = _buyer_agent_id(from_agent)

    signing_key = None
    if sign:
        wallet = load_signing_wallet(ctx, wallet_name=wallet_name, password=password)
        signing_key = wallet[1] if wallet else None

    found = _find_task_messages(_inbox(client, buyer_agent, signing_key=signing_key), task_id)
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
