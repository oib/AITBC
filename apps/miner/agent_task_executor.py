"""Agent task executor — provider side of the paid A2A delegation loop.

Polls this node's agent inbox on the hub agent-coordinator for TaskRequest /
TaskAccept envelopes (``/api/v1/agent/messages/inbox``), auto-quotes from the
miner's software-offer price table, executes accepted tasks against the local
services, stores results on the island IPFS daemon, and drives escrow
completion via ``/v1/tasks/{task_id}/complete``.

Message flow (all envelopes travel as ``content`` dicts in
``/api/v1/agent/messages/send`` with ``encrypt=false`` — the payloads are
negotiation metadata, not secrets):

    buyer  → TaskRequest {task_id, service_type, model, payload_ref, max_price, escrow_id}
    agent  → TaskQuote {task_id, price, eta, offer_id}   (or TaskReject)
    buyer  → TaskAccept {task_id}
    agent  → TaskResult {task_id, status, result_ref, result_hash}
    agent  → POST /v1/tasks/{task_id}/complete  (escrow release on-chain)
    agent  → TaskPaid {task_id, tx_hash}

Enablement: ``AGENT_EXECUTOR_ENABLED=true`` in the miner env.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests

from aitbc.aitbc_logging import get_logger
from aitbc.utils.units import ait_to_units

logger = get_logger(__name__)

# --- Configuration ---------------------------------------------------------

COORDINATOR_URL = os.environ.get("AGENT_COORDINATOR_URL") or os.environ.get("COORDINATOR_URL", "https://hub.aitbc.bubuit.net")
AGENT_EXECUTOR_ID = os.environ.get("AGENT_EXECUTOR_ID") or os.environ.get("MINER_ID", "aitbc-miner-1")
STATE_PATH = Path(os.environ.get("AGENT_EXECUTOR_STATE", "/var/lib/aitbc/data/agent_executor_state.json"))
HTTP_TIMEOUT = int(os.environ.get("AGENT_EXECUTOR_HTTP_TIMEOUT", "30"))

# Local service endpoints (provider-side execution)
ISLAND_IPFS_API = os.environ.get("ISLAND_IPFS_API", "http://127.0.0.1:5002")
WHISPER_URL = os.environ.get("AGENT_EXECUTOR_WHISPER_URL", "http://127.0.0.1:8110")
FFMPEG_URL = os.environ.get("AGENT_EXECUTOR_FFMPEG_URL", "http://127.0.0.1:8230")
OLLAMA_URL = os.environ.get("AGENT_EXECUTOR_OLLAMA_URL", "http://127.0.0.1:11434")

# Per-service health probes used for the capacity check.
_SERVICE_HEALTH = {
    "whisper": f"{WHISPER_URL}/health",
    "ffmpeg": f"{FFMPEG_URL}/health",
    "ollama": f"{OLLAMA_URL}/api/tags",
    "ipfs": f"{ISLAND_IPFS_API}/api/v0/id",
}

_MAX_DONE = 2000


# --- State file -------------------------------------------------------------


def _load_state() -> dict[str, Any]:
    try:
        data = json.loads(STATE_PATH.read_text())
        if isinstance(data, dict):
            data.setdefault("done", [])
            data.setdefault("quotes", {})
            return data
    except Exception:
        pass
    return {"done": [], "quotes": {}}


def _save_state(state: dict[str, Any]) -> None:
    state["done"] = state.get("done", [])[-_MAX_DONE:]
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.warning("Could not persist executor state: %s", e)


# --- Coordinator helpers ----------------------------------------------------


def _send_message(sender: str, recipient: str, message_type: str, content: dict[str, Any]) -> bool:
    """Send a negotiation message via the coordinator REST API (unencrypted)."""
    try:
        resp = requests.post(
            f"{COORDINATOR_URL}/api/v1/agent/messages/send",
            json={
                "sender": sender,
                "recipient": recipient,
                "content": content,
                "message_type": message_type,
                "encrypt": False,
                "ttl": 3600,
            },
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("Message send to %s failed: %s %s", recipient, resp.status_code, resp.text[:200])
            return False
        return True
    except requests.RequestException as e:
        logger.warning("Message send to %s unreachable: %s", recipient, e)
        return False


def _mark_read(message_id: str) -> None:
    try:
        requests.post(
            f"{COORDINATOR_URL}/api/v1/agent/messages/id/{message_id}/read",
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException:
        pass


def _fetch_inbox(agent_id: str, limit: int = 100) -> list[dict[str, Any]]:
    try:
        resp = requests.get(
            f"{COORDINATOR_URL}/api/v1/agent/messages/inbox",
            params={"agent_id": agent_id, "limit": str(limit), "unread_only": "true"},
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("Inbox poll failed: %s %s", resp.status_code, resp.text[:200])
            return []
        data = resp.json()
        return [m for m in data.get("messages", []) if isinstance(m, dict)]
    except (requests.RequestException, ValueError) as e:
        logger.warning("Inbox poll error: %s", e)
        return []


def _register_agent(agent_id: str, wallet: str, services: list[str]) -> bool:
    """Register/refresh this executor's agent identity on the coordinator."""
    try:
        resp = requests.post(
            f"{COORDINATOR_URL}/v1/agents/register",
            json={
                "agent_id": agent_id,
                "agent_type": "worker",
                "capabilities": ["paid_delegation"],
                "services": services,
                "endpoints": {},
                "metadata": {"wallet": wallet, "role": "provider-executor"},
            },
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            return True
        logger.warning("Agent registration failed: %s %s", resp.status_code, resp.text[:200])
    except requests.RequestException as e:
        logger.warning("Agent registration unreachable: %s", e)
    return False


def _task_escrow_status(task_id: str) -> dict[str, Any] | None:
    try:
        resp = requests.get(f"{COORDINATOR_URL}/v1/tasks/{task_id}/escrow", timeout=HTTP_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("escrow") if isinstance(data, dict) else None
    except (requests.RequestException, ValueError):
        pass
    return None


def _provider_signing_key(provider_wallet: str) -> str | None:
    """Resolve the private key that proves control of the provider wallet.

    The coordinator binds ``complete``/``fail`` to the escrow's ``agent``
    address, so the signature must come from the provider wallet key. Sources,
    in order: ``AGENT_EXECUTOR_SIGNING_KEY`` (hex private key), then
    ``MINER_WALLET_KEY_FILE`` (default ``/var/lib/aitbc/wallets/default.json``)
    whose stored address must match ``provider_wallet``.
    """
    key = os.environ.get("AGENT_EXECUTOR_SIGNING_KEY")
    if key:
        return key
    key_file = os.environ.get("MINER_WALLET_KEY_FILE", "/var/lib/aitbc/wallets/default.json")
    try:
        data = json.loads(Path(key_file).read_text())
        pk = data.get("private_key")
        if not pk:
            return None
        from aitbc.crypto.crypto import derive_ethereum_address

        if derive_ethereum_address(pk).lower() != provider_wallet.lower():
            logger.warning("Signing key file %s does not match provider wallet %s", key_file, provider_wallet)
            return None
        return str(pk)
    except Exception as e:
        logger.warning("No provider signing key available: %s", e)
        return None


def _signed_body(action: str, task_id: str, provider_wallet: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the signed request body for escrow-bound task calls."""
    signed_at = int(time.time())
    signed: dict[str, Any] = {"action": action, "task_id": task_id, "signed_at": signed_at}
    if extra:
        signed.update(extra)
    body = dict(signed)
    key = _provider_signing_key(provider_wallet)
    if key:
        from aitbc.crypto.crypto import sign_transaction_data

        body["signature"] = sign_transaction_data(signed, key)
    else:
        logger.warning("Calling %s on %s unsigned — coordinator will reject provider-bound escrows", action, task_id)
    return body


def _complete_task(task_id: str, provider_wallet: str, amount_units: int | None = None) -> dict[str, Any] | None:
    try:
        extra = {"amount_units": amount_units} if amount_units is not None else {"amount_units": 0}
        body = _signed_body("complete", task_id, provider_wallet, extra)
        resp = requests.post(f"{COORDINATOR_URL}/v1/tasks/{task_id}/complete", json=body, timeout=HTTP_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, dict) else None
        logger.warning("Task complete failed: %s %s", resp.status_code, resp.text[:200])
    except (requests.RequestException, ValueError) as e:
        logger.warning("Task complete error: %s", e)
    return None


def _fail_task(task_id: str, provider_wallet: str) -> None:
    try:
        body = _signed_body("fail", task_id, provider_wallet)
        requests.post(f"{COORDINATOR_URL}/v1/tasks/{task_id}/fail", json=body, timeout=HTTP_TIMEOUT)
    except requests.RequestException as e:
        logger.warning("Task fail call error: %s", e)


# --- IPFS helpers (island daemon) --------------------------------------------


def _ipfs_cat(cid: str, timeout: int = 120) -> bytes:
    resp = requests.post(f"{ISLAND_IPFS_API}/api/v0/cat", params={"arg": cid}, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def _ipfs_add(data: bytes, filename: str = "result.bin") -> str:
    resp = requests.post(
        f"{ISLAND_IPFS_API}/api/v0/add",
        files={"file": (filename, data)},
        timeout=120,
    )
    resp.raise_for_status()
    return str(resp.json().get("Hash"))


# --- Service handlers ---------------------------------------------------------
#
# Each handler receives the task request dict and returns (result_bytes,
# result_hash). Handlers raise on failure — the sweep catches and reports.


def _exec_whisper(req: dict[str, Any], payload: bytes) -> bytes:
    resp = requests.post(
        f"{WHISPER_URL}/transcribe",
        files={"file": ("audio", payload)},
        data={"task": "transcribe"},
        timeout=600,
    )
    resp.raise_for_status()
    return resp.content


def _exec_ffmpeg(req: dict[str, Any], payload: bytes) -> bytes:
    resp = requests.post(
        f"{FFMPEG_URL}/process",
        files={"file": ("input", payload)},
        data={"output_format": "mp4", "codec": "h264"},
        timeout=1800,
    )
    resp.raise_for_status()
    return resp.content


def _exec_ollama(req: dict[str, Any], payload: bytes) -> bytes:
    try:
        spec = json.loads(payload.decode())
    except (ValueError, UnicodeDecodeError):
        spec = {"prompt": payload.decode(errors="replace")}
    model = req.get("model") or spec.get("model") or "llama3.2:3b"
    prompt = spec.get("prompt", "")
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=600,
    )
    resp.raise_for_status()
    return resp.content


def _exec_ipfs(req: dict[str, Any], payload: bytes) -> bytes:
    """IPFS "hosting" task: pin the request's payload CID on the island daemon."""
    cid = req.get("payload_ref", "")
    resp = requests.post(f"{ISLAND_IPFS_API}/api/v0/pin/add", params={"arg": cid}, timeout=120)
    resp.raise_for_status()
    return json.dumps({"pinned": cid}).encode()


SERVICE_HANDLERS = {
    "whisper": _exec_whisper,
    "ffmpeg": _exec_ffmpeg,
    "ollama": _exec_ollama,
    "ipfs": _exec_ipfs,
}


def _service_ready(service_type: str) -> bool:
    url = _SERVICE_HEALTH.get(service_type)
    if not url:
        return False
    try:
        if service_type in ("ipfs",):
            resp = requests.post(url, timeout=5)
        else:
            resp = requests.get(url, timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False


# --- Message parsing ----------------------------------------------------------


def _parse_content(message: dict[str, Any]) -> dict[str, Any] | None:
    content = message.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return None
    return content if isinstance(content, dict) else None


def _handle_task_request(
    message: dict[str, Any],
    req: dict[str, Any],
    agent_id: str,
    provider_wallet: str,
    price_table: dict[str, dict[str, Any]],
    state: dict[str, Any],
) -> str:
    """Quote or reject a TaskRequest. Returns "quoted" or "rejected"."""
    task_id = req.get("task_id", "")
    service_type = req.get("service_type", "")
    buyer = message.get("sender", "")
    try:
        max_price = Decimal(str(req.get("max_price", "0")))
    except Exception:
        max_price = Decimal(0)

    offer = price_table.get(service_type)
    if offer is None:
        _send_message(
            agent_id, buyer, "task_reject", {"task_id": task_id, "reason": f"unsupported service_type {service_type}"}
        )
        return "rejected"

    reason = None
    if req.get("model") and offer.get("model") and req["model"] != offer["model"]:
        reason = f"unsupported model {req['model']} (offer: {offer['model']})"
    elif not _service_ready(service_type):
        reason = f"service {service_type} unavailable"
    elif max_price < Decimal(str(offer["price"])):
        reason = f"max_price {max_price} below offer price {offer['price']}"

    # Verify the buyer's escrow exists, is locked, and pays this provider.
    if reason is None:
        escrow = _task_escrow_status(task_id)
        if not escrow or escrow.get("escrow_status") != "locked":
            reason = "no locked escrow for task"
        elif provider_wallet and escrow.get("agent", "").lower() != provider_wallet.lower():
            reason = f"escrow pays {escrow.get('agent')}, not this provider"
        elif int(escrow.get("amount", 0)) < ait_to_units(Decimal(str(offer["price"]))):
            reason = "escrow amount below offer price"

    if reason:
        logger.info("Rejecting task %s: %s", task_id, reason)
        _send_message(agent_id, buyer, "task_reject", {"task_id": task_id, "reason": reason})
        return "rejected"

    quote = {
        "task_id": task_id,
        "price": str(offer["price"]),
        "eta": None,
        "offer_id": offer.get("offer_id") or f"{service_type}-{offer.get('model', '')}",
    }
    if _send_message(agent_id, buyer, "task_quote", quote):
        state["quotes"][task_id] = {
            "buyer": buyer,
            "price": str(offer["price"]),
            "offer_id": quote["offer_id"],
            "request": req,
            "quoted_at": time.time(),
        }
        logger.info("Quoted task %s (%s) at %s AIT to %s", task_id, service_type, offer["price"], buyer)
        return "quoted"
    return "rejected"


def _handle_task_accept(
    message: dict[str, Any],
    acc: dict[str, Any],
    agent_id: str,
    provider_wallet: str,
    state: dict[str, Any],
) -> str | None:
    """Execute an accepted task end-to-end. Returns "executed" or "failed"."""
    task_id = acc.get("task_id", "")
    buyer = message.get("sender", "")
    quote = state["quotes"].get(task_id)
    if not quote:
        logger.warning("TaskAccept for unknown/unquoted task %s — ignored", task_id)
        return None

    req = quote["request"]
    service_type = req.get("service_type", "")
    handler = SERVICE_HANDLERS.get(service_type)

    # Verify the escrow exists and locks payment to this provider wallet.
    escrow = _task_escrow_status(task_id)
    if not escrow or escrow.get("escrow_status") != "locked":
        logger.warning("Task %s accepted but escrow is not locked (%s) — skipping", task_id, escrow)
        return None
    if provider_wallet and escrow.get("agent", "").lower() != provider_wallet.lower():
        logger.warning("Task %s escrow agent %s != our wallet %s — skipping", task_id, escrow.get("agent"), provider_wallet)
        return None

    try:
        payload = b"" if service_type == "ipfs" else _ipfs_cat(req["payload_ref"])
        result_bytes = handler(req, payload) if handler else b"{}"
        result_hash = hashlib.sha256(result_bytes).hexdigest()
        result_ref = _ipfs_add(result_bytes, filename=f"{task_id}.json")
    except Exception as e:
        logger.error("Task %s execution failed: %s", task_id, e)
        _send_message(
            agent_id,
            buyer,
            "task_result",
            {"task_id": task_id, "status": "failed", "result_ref": None, "result_hash": None, "error": str(e)[:300]},
        )
        _fail_task(task_id, provider_wallet)
        return "failed"

    _send_message(
        agent_id,
        buyer,
        "task_result",
        {"task_id": task_id, "status": "success", "result_ref": result_ref, "result_hash": result_hash},
    )
    # Bill the quoted price, not the whole lock — the chain refunds the rest.
    quote_units = None
    try:
        quote_units = ait_to_units(Decimal(str(quote["price"])))
    except Exception:
        pass
    complete = _complete_task(task_id, provider_wallet, amount_units=quote_units)
    if complete:
        tx_hash = complete.get("tx_hash_release")
        _send_message(agent_id, buyer, "task_paid", {"task_id": task_id, "tx_hash": tx_hash})
        logger.info("Task %s complete — escrow released (tx=%s), result at %s", task_id, tx_hash, result_ref)
    else:
        logger.error("Task %s executed (result %s) but escrow release call failed", task_id, result_ref)
    state["quotes"].pop(task_id, None)
    return "executed"


def sweep_once(provider_wallet: str, price_table: dict[str, dict[str, Any]] | None = None) -> dict[str, int]:
    """One executor pass: register, poll inbox, handle pending messages.

    ``price_table`` maps ``service_type`` → offer dict with at least ``price``
    and ``model`` keys (production_miner passes its DEFAULT_SOFTWARE_OFFERS
    keyed by service type).
    """
    stats = {"quoted": 0, "rejected": 0, "executed": 0, "failed": 0}
    if price_table is None:
        price_table = {}
    state = _load_state()
    done: list[str] = state["done"]

    if not _register_agent(AGENT_EXECUTOR_ID, provider_wallet, list(price_table.keys() or SERVICE_HANDLERS.keys())):
        logger.warning("Agent registration failed — continuing anyway")

    for message in _fetch_inbox(AGENT_EXECUTOR_ID):
        msg_id = str(message.get("message_id") or message.get("id") or "")
        if not msg_id or msg_id in done:
            continue
        message_type = message.get("message_type", "")
        content = _parse_content(message)
        if content is None:
            done.append(msg_id)
            _mark_read(msg_id)
            continue

        outcome = None
        if message_type == "task_request":
            outcome = _handle_task_request(message, content, AGENT_EXECUTOR_ID, provider_wallet, price_table, state)
        elif message_type == "task_accept":
            outcome = _handle_task_accept(message, content, AGENT_EXECUTOR_ID, provider_wallet, state)
        elif message_type == "task_reject":
            state["quotes"].pop(content.get("task_id", ""), None)
        if outcome in stats:
            stats[outcome] += 1
        done.append(msg_id)
        _mark_read(msg_id)

    _save_state(state)
    return stats
