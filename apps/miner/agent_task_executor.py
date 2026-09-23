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

Signing (docs/agent-coordinator/agent-signed-envelopes.md, Phase A/B): when a
signing key is configured the executor binds ``AGENT_EXECUTOR_ID`` to the miner
wallet at registration (``identity_address`` + ``identity_proof``), signs every
outbound envelope (``aitbc-agent-msg-v1``), and attaches ``X-Agent-*``
signed-request headers plus a ``agent_signature`` body field on the escrow
calls (``aitbc-agent-req-v1``). Key custody: ``AGENT_SIGNING_KEY`` (hex private
key) or the established ``AGENT_EXECUTOR_SIGNING_KEY`` / ``MINER_WALLET_KEY_FILE``
miner wallet file; the derived address must equal ``MINER_WALLET_ADDRESS`` when
that env var is set. With no key configured the executor runs exactly as
before, unsigned (advisory mode).

Enablement: ``AGENT_EXECUTOR_ENABLED=true`` in the miner env.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests

from aitbc.aitbc_logging import get_logger
from aitbc.utils.units import ait_to_units

logger = get_logger(__name__)

# --- Configuration ---------------------------------------------------------

COORDINATOR_URL = os.environ.get("AGENT_COORDINATOR_URL") or os.environ.get("COORDINATOR_URL", "https://hub.example.net")
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


# --- Signing key custody -----------------------------------------------------
#
# The executor signs outbound envelopes, read requests and escrow calls with
# the miner wallet key — the operator decision is identity_address == payout
# wallet. Resolution order follows the established miner pattern:
# ``AGENT_SIGNING_KEY`` (hex private key) → ``AGENT_EXECUTOR_SIGNING_KEY``
# (same, legacy name) → ``MINER_WALLET_KEY_FILE`` (JSON wallet file with
# ``private_key``/``address``, default ``/var/lib/aitbc/wallets/default.json``).
# The material is resolved once per configuration and cached; tests change the
# env between cases, so the cache key is the resolved input tuple.

#: Domain prefix for signed *requests* (read/mutation calls carried in
#: ``X-Agent-*`` headers and the escrow-call ``agent_signature``). The
#: coordinator-side verifier for this domain lands in a later phase.
AGENT_REQ_DOMAIN = "aitbc-agent-req-v1"

_signing_cache_inputs: tuple[Any, ...] | None = None
_signing_cache_value: tuple[str | None, str | None] = (None, None)
_warned_unsigned = False


def _warn_unsigned_once() -> None:
    global _warned_unsigned
    if not _warned_unsigned:
        logger.warning(
            "No agent signing key configured (AGENT_SIGNING_KEY / AGENT_EXECUTOR_SIGNING_KEY / "
            "MINER_WALLET_KEY_FILE) — agent traffic is UNSIGNED; the coordinator accepts it in "
            "advisory mode only"
        )
        _warned_unsigned = True


def _signing_material(provider_wallet: str = "") -> tuple[str | None, str | None]:
    """Resolve ``(private_key, derived_address)`` for agent signing, or ``(None, None)``.

    When ``MINER_WALLET_ADDRESS`` is set in the environment it must equal the
    derived address — a mismatch is a misconfigured key and fails fast. A
    mismatch against the call-site ``provider_wallet`` only disables signing
    for that call (never sign as a different identity than the escrow agent).
    """
    global _signing_cache_inputs, _signing_cache_value
    env_key = (os.environ.get("AGENT_SIGNING_KEY") or os.environ.get("AGENT_EXECUTOR_SIGNING_KEY") or "").strip()
    key_file = os.environ.get("MINER_WALLET_KEY_FILE", "/var/lib/aitbc/wallets/default.json")
    wallet_env = os.environ.get("MINER_WALLET_ADDRESS", "").strip()
    inputs = (env_key, key_file, wallet_env, provider_wallet)
    if inputs == _signing_cache_inputs:
        return _signing_cache_value

    key = env_key or None
    if key is None:
        try:
            data = json.loads(Path(key_file).read_text())
            if data.get("private_key"):
                key = str(data["private_key"])
        except Exception:
            key = None

    if key is None:
        _warn_unsigned_once()
        result: tuple[str | None, str | None] = (None, None)
    else:
        from aitbc.crypto.crypto import derive_ethereum_address
        from aitbc.crypto.signature_recovery import canonical_address

        try:
            address = derive_ethereum_address(key)
        except Exception as e:
            logger.error("Configured agent signing key is invalid (%s) — running unsigned", e)
            result = (None, None)
        else:
            if wallet_env and canonical_address(wallet_env) != canonical_address(address):
                raise RuntimeError(
                    f"MINER_WALLET_ADDRESS ({wallet_env}) does not match the configured agent signing "
                    f"key, which derives {address} — refusing to run with a mismatched identity"
                )
            if provider_wallet and canonical_address(provider_wallet) != canonical_address(address):
                logger.warning(
                    "Agent signing key derives %s but the provider wallet is %s — not signing this call",
                    address,
                    provider_wallet,
                )
                result = (None, None)
            else:
                result = (key, address)
    _signing_cache_inputs = inputs
    _signing_cache_value = result
    return result


def _provider_signing_key(provider_wallet: str) -> str | None:
    """Private key proving control of the provider wallet (compat wrapper)."""
    key, _address = _signing_material(provider_wallet)
    return key


def _sign_req_payload(payload: dict[str, Any], private_key: str) -> str:
    """secp256k1 over ``keccak256("aitbc-agent-req-v1:" + canonical_json(payload))``."""
    from aitbc.crypto.agent_envelope import domain_digest
    from aitbc.crypto.crypto import sign_transaction_hash

    return "0x" + sign_transaction_hash(domain_digest(payload, AGENT_REQ_DOMAIN).hex(), private_key).removeprefix("0x")


def _agent_request_headers(agent_id: str, timestamp: str | None = None, nonce: str | None = None) -> dict[str, str]:
    """Fresh ``X-Agent-*`` signed-request headers; empty dict when unsigned.

    A new nonce + timestamp are generated per call unless supplied, so the
    sweep loop cannot replay-collide on the coordinator's ``(agent, nonce)``
    dedup. The signature covers ``{"agent_id","timestamp","nonce"}`` in the
    ``aitbc-agent-req-v1`` domain.
    """
    key, _address = _signing_material()
    if not key:
        return {}
    from aitbc.crypto import generate_nonce

    ts = timestamp or datetime.now(UTC).isoformat()
    nc = nonce or generate_nonce(16)
    return {
        "X-Agent-Id": agent_id,
        "X-Agent-Signature": _sign_req_payload({"agent_id": agent_id, "timestamp": ts, "nonce": nc}, key),
        "X-Agent-Timestamp": ts,
        "X-Agent-Nonce": nc,
    }


# --- Coordinator helpers ----------------------------------------------------


def _send_message(sender: str, recipient: str, message_type: str, content: dict[str, Any]) -> bool:
    """Send a negotiation message via the coordinator REST API (unencrypted).

    With a signing key configured the request is a Phase-A signed envelope:
    ``signature`` covers every ``SendMessageRequest`` field (the server's
    ``signing_payload()`` is ``model_dump(exclude={"signature"})``), so the
    full field set — including defaults like ``priority``/``message_id`` — is
    sent verbatim.
    """
    key, address = _signing_material()
    if key and address:
        from aitbc.crypto import generate_nonce
        from aitbc.crypto.agent_envelope import AGENT_MSG_SIGNATURE_VERSION, sign_agent_envelope

        body: dict[str, Any] = {
            "sender": sender,
            "recipient": recipient,
            "content": content,
            "message_type": message_type,
            "encrypt": False,
            "priority": "normal",
            "ttl": 3600,
            "message_id": None,
            "signer": address,
            "signature_version": AGENT_MSG_SIGNATURE_VERSION,
            "timestamp": datetime.now(UTC).isoformat(),
            "nonce": generate_nonce(16),
        }
        try:
            body["signature"] = sign_agent_envelope(body, key)
        except Exception as e:
            logger.error("Envelope signing failed (%s) — sending unsigned", e)
            body.pop("signer", None)
            body.pop("signature_version", None)
            body.pop("timestamp", None)
            body.pop("nonce", None)
            body.pop("message_id", None)
            body.pop("priority", None)
    else:
        _warn_unsigned_once()
        body = {
            "sender": sender,
            "recipient": recipient,
            "content": content,
            "message_type": message_type,
            "encrypt": False,
            "ttl": 3600,
        }
    try:
        resp = requests.post(
            f"{COORDINATOR_URL}/api/v1/agent/messages/send",
            json=body,
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
            headers=_agent_request_headers(AGENT_EXECUTOR_ID),
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException:
        pass


def _fetch_inbox(agent_id: str, limit: int = 100) -> list[dict[str, Any]]:
    try:
        resp = requests.get(
            f"{COORDINATOR_URL}/api/v1/agent/messages/inbox",
            params={"agent_id": agent_id, "limit": str(limit), "unread_only": "true"},
            headers=_agent_request_headers(agent_id),
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


def _fetch_registration_nonce(agent_id: str) -> dict[str, str] | None:
    """One-time 300 s nonce (+ chain_id) for the registration identity claim."""
    try:
        resp = requests.get(
            f"{COORDINATOR_URL}/v1/agents/nonce",
            params={"agent_id": agent_id},
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and data.get("nonce"):
                return {"nonce": str(data["nonce"]), "chain_id": str(data.get("chain_id") or "")}
    except (requests.RequestException, ValueError):
        pass
    return None


def _bound_identity(agent_id: str) -> str | None:
    """The ``identity_address`` the registry has bound to ``agent_id``, if any."""
    try:
        resp = requests.get(f"{COORDINATOR_URL}/v1/agents/{agent_id}", timeout=HTTP_TIMEOUT)
        if resp.status_code == 200:
            agent = resp.json().get("agent")
            if isinstance(agent, dict):
                bound = agent.get("identity_address")
                return str(bound) if bound else None
    except (requests.RequestException, ValueError):
        pass
    return None


def _register_agent(agent_id: str, wallet: str, services: list[str]) -> bool:
    """Register/refresh this executor's agent identity on the coordinator.

    With a signing key, the request carries the §3 identity attestation:
    ``identity_address`` (the miner wallet = payout address) plus an
    ``identity_proof`` over the canonical claim ``{"agent_id",
    "identity_address", "chain_id", "nonce", "registered_at"}`` where ``nonce``
    is the one-time value from ``GET /v1/agents/nonce``.
    """
    body: dict[str, Any] = {
        "agent_id": agent_id,
        "agent_type": "worker",
        "capabilities": ["paid_delegation"],
        "services": services,
        "endpoints": {},
        "metadata": {"wallet": wallet, "role": "provider-executor"},
    }
    key, address = _signing_material(wallet)
    if key and address:
        nonce_info = _fetch_registration_nonce(agent_id)
        if nonce_info:
            from aitbc.crypto.agent_envelope import identity_claim, sign_identity_claim

            registered_at = datetime.now(UTC).isoformat()
            claim = identity_claim(
                agent_id=agent_id,
                identity_address=address,
                chain_id=nonce_info["chain_id"],
                nonce=nonce_info["nonce"],
                registered_at=registered_at,
            )
            body.update(
                {
                    "identity_address": address,
                    "identity_proof": sign_identity_claim(claim, key),
                    "identity_nonce": nonce_info["nonce"],
                    "registered_at": registered_at,
                    "chain_id": nonce_info["chain_id"],
                }
            )
        else:
            logger.warning("No registration nonce from coordinator — registering without identity proof")
    try:
        resp = requests.post(
            f"{COORDINATOR_URL}/v1/agents/register",
            json=body,
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            return True
        if resp.status_code == 409:
            # Bound agent re-registrations must re-prove the *bound* key. The
            # registry lookup disambiguates: bound to our key/wallet is benign
            # (identity already ours); bound to a foreign key is a hijack
            # signal — rotate via PUT /v1/agents/{id}/identity instead.
            bound = _bound_identity(agent_id)
            ours = {a for a in (address, wallet) if a}
            if bound and ours:
                from aitbc.crypto.signature_recovery import canonical_address

                if canonical_address(bound) in {canonical_address(a) for a in ours}:
                    logger.info("Agent %s already bound to our identity %s — re-registration not needed", agent_id, bound)
                    return True
            logger.error(
                "Agent %s is bound to a different identity (%s) — refusing to re-register; "
                "rotate identity explicitly if this key change is intended",
                agent_id,
                bound,
            )
            return False
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


def _escrow_lock_confirmed(escrow: dict[str, Any] | None) -> bool:
    """True only when the lock is anchored on-chain.

    ``escrow_status == "locked"`` alone is not enough: a bookkeeping-only row
    (no ``tx_hash_lock`` and no ``contract_id``) has no funds behind it and
    must not drive free work.
    """
    if not escrow:
        return False
    return bool(escrow.get("tx_hash_lock") or escrow.get("contract_id"))


def _signed_body(
    action: str,
    task_id: str,
    provider_wallet: str,
    extra: dict[str, Any] | None = None,
    req_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the signed request body for escrow-bound task calls.

    Two signatures coexist while the coordinator migrates:

    * ``signature`` — the *live* check (commit 23ad910d6): ``recover_signer``
      over ``{"action","task_id","signed_at"[,"amount_units"]}``. Kept verbatim
      so today's coordinator still accepts the call.
    * ``agent_signature`` — the Phase-B signed-request field: secp256k1 over
      ``{"task_id", <amount_units|reason>, "timestamp","nonce"}`` in the
      ``aitbc-agent-req-v1`` domain. Server-side verification lands in a later
      phase; the fields are emitted now.
    """
    signed_at = int(time.time())
    signed: dict[str, Any] = {"action": action, "task_id": task_id, "signed_at": signed_at}
    if extra:
        signed.update(extra)
    body = dict(signed)
    if req_fields:
        body.update(req_fields)
    key, _address = _signing_material(provider_wallet)
    if key:
        from aitbc.crypto import generate_nonce
        from aitbc.crypto.crypto import sign_transaction_data

        body["signature"] = sign_transaction_data(signed, key)
        timestamp = datetime.now(UTC).isoformat()
        nonce = generate_nonce(16)
        req_payload: dict[str, Any] = {"task_id": task_id, "timestamp": timestamp, "nonce": nonce}
        req_payload.update(req_fields if req_fields is not None else (extra or {}))
        body["timestamp"] = timestamp
        body["nonce"] = nonce
        body["agent_signature"] = _sign_req_payload(req_payload, key)
    else:
        logger.warning("Calling %s on %s unsigned — coordinator will reject provider-bound escrows", action, task_id)
    return body


def _complete_task(task_id: str, provider_wallet: str, amount_units: int | None = None) -> dict[str, Any] | None:
    try:
        extra = {"amount_units": amount_units} if amount_units is not None else {"amount_units": 0}
        body = _signed_body("complete", task_id, provider_wallet, extra)
        headers = _agent_request_headers(
            AGENT_EXECUTOR_ID,
            timestamp=body.get("timestamp") if isinstance(body.get("timestamp"), str) else None,
            nonce=body.get("nonce") if isinstance(body.get("nonce"), str) else None,
        )
        resp = requests.post(
            f"{COORDINATOR_URL}/v1/tasks/{task_id}/complete", json=body, headers=headers, timeout=HTTP_TIMEOUT
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, dict) else None
        logger.warning("Task complete failed: %s %s", resp.status_code, resp.text[:200])
    except (requests.RequestException, ValueError) as e:
        logger.warning("Task complete error: %s", e)
    return None


def _fail_task(task_id: str, provider_wallet: str, reason: str | None = None) -> None:
    try:
        req_fields = {"reason": reason or "execution_failed"}
        body = _signed_body("fail", task_id, provider_wallet, req_fields=req_fields)
        headers = _agent_request_headers(
            AGENT_EXECUTOR_ID,
            timestamp=body.get("timestamp") if isinstance(body.get("timestamp"), str) else None,
            nonce=body.get("nonce") if isinstance(body.get("nonce"), str) else None,
        )
        requests.post(f"{COORDINATOR_URL}/v1/tasks/{task_id}/fail", json=body, headers=headers, timeout=HTTP_TIMEOUT)
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


def _offer_reject_reason(
    req: dict[str, Any],
    service_type: str,
    offer: dict[str, Any],
    max_price: Decimal,
) -> str | None:
    """Offer-side rejection reason for a TaskRequest, or None when acceptable."""
    if req.get("model") and offer.get("model") and req["model"] != offer["model"]:
        return f"unsupported model {req['model']} (offer: {offer['model']})"
    if not _service_ready(service_type):
        return f"service {service_type} unavailable"
    if max_price < Decimal(str(offer["price"])):
        return f"max_price {max_price} below offer price {offer['price']}"
    return None


def _escrow_reject_reason(task_id: str, provider_wallet: str, offer: dict[str, Any]) -> str | None:
    """Escrow-side rejection reason, or None when the lock pays this provider.

    Verifies the buyer's escrow exists, is locked on-chain, and pays this
    provider.
    """
    escrow = _task_escrow_status(task_id)
    if not escrow or escrow.get("escrow_status") != "locked":
        return "no locked escrow for task"
    if not _escrow_lock_confirmed(escrow):
        return "escrow lock not anchored on-chain (no tx_hash_lock/contract_id)"
    if provider_wallet and escrow.get("agent", "").lower() != provider_wallet.lower():
        return f"escrow pays {escrow.get('agent')}, not this provider"
    if int(escrow.get("amount", 0)) < ait_to_units(Decimal(str(offer["price"]))):
        return "escrow amount below offer price"
    return None


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

    reason = _offer_reject_reason(req, service_type, offer, max_price)
    # Verify the buyer's escrow exists, is locked on-chain, and pays this provider.
    if reason is None:
        reason = _escrow_reject_reason(task_id, provider_wallet, offer)

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

    # Verify the escrow exists, is locked on-chain, and locks payment to this
    # provider wallet — a bookkeeping-only "locked" row must not drive free work.
    escrow = _task_escrow_status(task_id)
    if not escrow or escrow.get("escrow_status") != "locked":
        logger.warning("Task %s accepted but escrow is not locked (%s) — skipping", task_id, escrow)
        return None
    if not _escrow_lock_confirmed(escrow):
        logger.warning(
            "Task %s accepted but the lock has no on-chain anchor (tx_hash_lock/contract_id empty: %s) — skipping",
            task_id,
            escrow,
        )
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
        _fail_task(task_id, provider_wallet, reason=str(e)[:200])
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


def _process_inbox_message(
    message: dict[str, Any],
    done: list[str],
    provider_wallet: str,
    price_table: dict[str, dict[str, Any]],
    state: dict[str, Any],
    stats: dict[str, int],
) -> None:
    """Handle one unread inbox envelope: dedup, signature gate, dispatch."""
    msg_id = str(message.get("message_id") or message.get("id") or "")
    if not msg_id or msg_id in done:
        return
    # Inbound envelope verification (advisory): the coordinator stamps
    # ``signature_status`` on stored records — a definitively invalid
    # signature means a spoofed/tampered sender; drop it. ``verified`` and
    # absent (unsigned / pre-Phase-A traffic) are processed as before.
    if message.get("signature_status") == "invalid":
        logger.warning("Dropping inbox message %s: signature_status=invalid", msg_id)
        done.append(msg_id)
        _mark_read(msg_id)
        return
    message_type = message.get("message_type", "")
    content = _parse_content(message)
    if content is None:
        done.append(msg_id)
        _mark_read(msg_id)
        return

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
        _process_inbox_message(message, done, provider_wallet, price_table, state, stats)

    _save_state(state)
    return stats
