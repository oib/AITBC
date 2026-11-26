"""Paid agent-to-agent task delegation for AITBC CLI (v0.25 Phase 3).

A buyer agent hires a provider agent through the hub agent-coordinator:

    hire   → payload to island IPFS → signed escrow lock → /v1/tasks/submit
             → TaskRequest message → provider quotes → TaskAccept
             → provider executes → TaskResult (result CID) → escrow release
    status → escrow state + negotiation messages for a task
    result → fetch the task result CID via the local island IPFS daemon

The negotiation messages ride ``/api/v1/agent/messages`` unencrypted — they
carry CIDs and prices, not secrets. Escrow settlement goes through the same
``/rpc/escrow/*`` chain routes the market uses.
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
import httpx

from aitbc.utils.units import ait_to_units

from aitbc.exceptions import AITBCError
from ..config import get_config
from ..utils.wallet_secret import wallet_password_options
from ..utils import error, info, output, success, warning
from aitbc.crypto.signature_recovery import canonical_address
from ..utils.agent_signing import (
    identity_attestation_fields,
    load_signing_wallet,
    scan_agents_for_identity,
    sign_send_envelope,
    signed_request_headers,
)
from ..utils.http_client import (
    AITBCHTTPClient,
    auth_client_kwargs,
    get_logger,
    http_error_detail,
    http_response_status,
    origin_base_url,
)
from ..utils.wallet_loader import load_wallet_for_payment
from .ipfs import _daemon_available, _ipfs_add_file, _is_cid
from .market.escrow import _get_blockchain_rpc_url
from .market.host import _resolve_ipfs_api
from ..utils.error_handling import CLIError, abort

# Expected failure surface for the command handlers below: filesystem/JSON,
# data-shape, runtime, optional-dependency imports, HTTP-client errors and
# both error hierarchies (CLIError, aitbc_errors.AITBCError). RuntimeError
# covers generic runtime failures; abort() raises CLIError (already listed),
# preserving the previous re-abort behaviour. BaseExceptions still propagate
# (#1864).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
    CLIError,
    AITBCError,
    httpx.HTTPError,
)

logger = get_logger(__name__)

DEFAULT_COORDINATOR_URL = "https://hub.aitbc.invalid"


def _coordinator_url(ctx, coordinator_url: str | None) -> str:
    url = coordinator_url or os.environ.get("AGENT_COORDINATOR_URL") or get_config().agent_coordinator_url
    # Every call site in this module carries its own absolute path
    # (``/v1/...``, ``/api/v1/agent/messages/...``), and nginx mounts those at
    # the origin root — so reduce the configured URL to scheme://host[:port].
    # ``get_config().agent_coordinator_url`` resolves via ``hub_agent_url()``
    # to the ``/agent`` mount; appending absolute paths onto it would produce
    # ``/agent/v1/agents/...`` (registry mount, wrong surface) instead of the
    # root-mounted ``/api/v1/agent/...`` route.
    return origin_base_url(url, DEFAULT_COORDINATOR_URL)


def _explicit_buyer_agent(from_agent: str | None) -> str | None:
    """The operator-chosen buyer agent id, or ``None`` when unset."""
    return from_agent or os.environ.get("AGENT_ID") or None


def _resolve_buyer_agent(
    client: AITBCHTTPClient,
    from_agent: str | None,
    wallet_address: str | None,
) -> str:
    """Buyer agent id for inbox polls and negotiation envelopes.

    Explicit ``--from-agent``/``$AGENT_ID`` wins. Otherwise, when a signing
    wallet is loaded, prefer the agent bound to that wallet's identity
    address: the hostname default (``buyer-<host>``) mismatches the
    wallet-bound principal under ``AGENT_MSG_SIGNATURE_MODE=enforce`` and
    produced the round-3 ``agent_mismatch`` inbox-poll failure (#2271).
    Registry lookup failures fall back to the hostname default.
    """
    explicit = _explicit_buyer_agent(from_agent)
    if explicit:
        return explicit
    if wallet_address:
        bound, scan_error = scan_agents_for_identity(client, wallet_address)
        if bound:
            return bound
        if scan_error is not None:
            # #2732: the discover scan needs an authenticated principal; a
            # silent fallback to buyer-<host> produces a guaranteed 401 at
            # the provider lookup under advisory/enforce modes.
            warning(
                f"Agent registry scan failed ({scan_error}) — cannot resolve the agent "
                f"bound to wallet {wallet_address}; falling back to buyer-{os.uname().nodename}. "
                "Pass --from-agent or authenticate with --api-key/`aitbc auth login` if the "
                "coordinator enforces agent auth."
            )
    return f"buyer-{os.uname().nodename}"


def _register_buyer_agent(client: AITBCHTTPClient, agent_id: str, address: str, private_key: str) -> str | None:
    """Self-register ``agent_id`` bound to ``address``; ``None`` on success.

    Only reached for *implicit* buyer agents (see ``_ensure_buyer_agent_binding``)
    — the fallback ``buyer-<host>`` identity is CLI-owned, so a minimal payload
    has no operator metadata to preserve. Returns an operator-facing note on
    failure; the downstream signed read then produces the authoritative error.
    """
    try:
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "agent_type": "worker",
            "capabilities": [],
            "services": [],
            "endpoints": {},
            "metadata": {"name": agent_id, "reputation": 0.5, "version": "1.0.0", "wallet": address},
            "chain_id": None,
            "island_id": "",
        }
        payload.update(identity_attestation_fields(client, agent_id, address, None, private_key))
        result = client.post("/v1/agents/register", json=payload)
    except _OPS_ERRORS as e:
        return f"buyer agent auto-registration failed: {e}"
    if isinstance(result, dict) and result.get("status") == "success":
        info(f"Registered buyer agent {agent_id} bound to wallet {address}")
        return None
    return f"buyer agent auto-registration rejected: {result}"


def _ensure_buyer_agent_binding(
    client: AITBCHTTPClient,
    agent_id: str,
    address: str,
    private_key: str,
    *,
    auto_register: bool,
) -> str | None:
    """``None`` when ``agent_id`` authenticates as ``address``; else a note.

    The signed ``GET /v1/agents/{id}`` resolves a principal only when the
    agent is registered *and* bound to the signing wallet — the precondition
    every later signed read (provider lookup, escrow, inbox, submit) needs.
    On auth failure an implicit buyer agent (``auto_register``) is
    self-registered bound to the wallet: ``POST /v1/agents/register`` is
    unauthenticated and the identity attestation proves key ownership, so
    hire no longer dead-ends on "register first" (#2983/#2979). Explicit
    ``--from-agent`` identities are never auto-registered — the operator
    named them, and a foreign binding must surface as guidance, not a
    silent rebind attempt. Transient lookup failures stay soft: advisory
    coordinators still accept unsigned traffic.
    """
    headers = signed_request_headers(agent_id, private_key)
    try:
        data = client.get(f"/v1/agents/{agent_id}", headers=headers)
    except _OPS_ERRORS as e:
        status = http_response_status(e)
        if status in (401, 403, 404):
            if auto_register:
                return _register_buyer_agent(client, agent_id, address, private_key)
            if status == 404:
                return (
                    f"Agent '{agent_id}' is not registered with the coordinator — register it first with "
                    f"`aitbc agent-comm register --agent-id {agent_id} --wallet ...`, or pass --from-agent "
                    "for an already-registered buyer agent"
                )
        return None
    agent = data.get("agent", {}) if isinstance(data, dict) else {}
    bound = agent.get("identity_address")
    if not bound:
        if auto_register:
            return _register_buyer_agent(client, agent_id, address, private_key)
        return (
            f"Agent '{agent_id}' is registered but has no bound identity — it cannot authenticate "
            "signed requests; bind a wallet via `aitbc agent-comm register --update --wallet ...`"
        )
    try:
        if canonical_address(bound) == canonical_address(address):
            return None
    except (AttributeError, TypeError, ValueError, ImportError):
        pass
    return (
        f"Agent '{agent_id}' is bound to identity {bound} but the signing wallet is {address} — "
        "use the bound wallet (or rotate via PUT /v1/agents/{agent_id}/identity)"
    )


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
    except _OPS_ERRORS as e:
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
    except _OPS_ERRORS as e:
        warning(f"Inbox poll failed: {e}")
        return []
    messages = data.get("messages", []) if isinstance(data, dict) else []
    return [m for m in messages if isinstance(m, dict)]


def _task_escrow(
    client: AITBCHTTPClient,
    task_id: str,
    agent_id: str,
    signing_key: str | None = None,
) -> dict[str, Any] | None:
    """GET the task escrow as ``agent_id``; signed when a buyer key exists.

    ``/v1/tasks/{task_id}/escrow`` is principal-gated and party-scoped, so the
    read must carry the same ``X-Agent-*`` headers as the inbox poll whenever
    signing is configured. Unsigned stays unsigned — the coordinator still
    answers 401 under enabled auth rather than exposing escrow metadata.
    """
    headers = signed_request_headers(agent_id, signing_key) if signing_key else None
    data = client.get(f"/v1/tasks/{task_id}/escrow", headers=headers)
    escrow = data.get("escrow") if isinstance(data, dict) else None
    return escrow if isinstance(escrow, dict) else None


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


def _resolve_provider_wallet(
    client: AITBCHTTPClient,
    agent_id: str,
    signing_agent_id: str | None = None,
    signing_key: str | None = None,
) -> str | None:
    """Provider wallet from the agent registry (executor publishes it).

    ``GET /v1/agents/{id}`` is principal-gated (#2212): under
    AGENT_MSG_SIGNATURE_MODE=enforce an unsigned read 401s before the
    escrow lock is ever built (#2431). When the buyer's signing material
    is at hand the read authenticates as ``signing_agent_id`` — the
    buyer's own registered agent — via ``X-Agent-*`` headers; without it
    the call stays unsigned for disabled/advisory coordinators.
    """
    headers = signed_request_headers(signing_agent_id, signing_key) if signing_agent_id and signing_key else None
    try:
        data = client.get(f"/v1/agents/{agent_id}", headers=headers)
    except _OPS_ERRORS as e:
        if http_response_status(e) in (401, 403):
            # #2732: the read authenticates as the *buyer* agent — a 401 here
            # means that agent is unregistered, unbound to the signing
            # wallet, or the request carried no valid principal at all.
            abort(
                None,
                f"Agent registry rejected the lookup for '{agent_id}' "
                f"(buyer agent: {signing_agent_id or 'unsigned'}). The buyer agent must be "
                "registered and bound to the signing wallet — run `aitbc agent-comm register "
                "--agent-id <id> --wallet ...`, pass --from-agent, or authenticate with "
                "--api-key/`aitbc auth login`.",
            )
        abort(None, f"Could not look up agent {agent_id}: {e}")
        return None
    agent = data.get("agent", {}) if isinstance(data, dict) else {}
    wallet = (agent.get("metadata") or {}).get("wallet") or (agent.get("endpoints") or {}).get("wallet")
    if not wallet:
        abort(None, f"Agent {agent_id} has no wallet in its registry metadata — cannot escrow payment")
        return None
    return cast(str, wallet)


def _resolve_payload_ref(ctx, payload: str) -> str | None:
    """Return a CID for --payload: pass-through for CIDs, `ipfs add` for files."""
    if _is_cid(payload):
        return payload
    path = Path(payload)
    if not path.is_file():
        abort(None, f"--payload must be an IPFS CID or a local file path (got: {payload})")
        return None
    ipfs_api = _resolve_ipfs_api({})
    if not _daemon_available(ipfs_api):
        abort(None, f"No local island IPFS daemon reachable at {ipfs_api} — cannot upload payload")
        return None
    cid = _ipfs_add_file(ipfs_api, path)
    if not cid:
        abort(None, f"IPFS add failed for {path}")
        return None
    info(f"Payload uploaded: {cid}")
    return cid


def _parse_max_price(max_price: str) -> Decimal:
    """Parse --max-price as a positive AIT amount or abort."""
    try:
        max_price_ait = Decimal(str(max_price))
    except (ArithmeticError, TypeError, ValueError):
        error(f"Invalid --max-price: {max_price}")
        raise click.Abort() from None
    if max_price_ait <= 0:
        error("--max-price must be positive")
        raise click.Abort()
    return max_price_ait


def _settlement_wallet(client: AITBCHTTPClient, config, ctx, rpc_url: str) -> str | None:
    """Resolve the escrow settlement wallet, or None when none is configured.

    The coordinator settles through its configured blockchain RPC's node
    wallet. Ask the coordinator first (correct on any node); then the local
    RPC's /health node_wallet (the custody address the chain validates the
    lock `to` against). HUB_PROPOSER_ID — the consensus proposer id, a
    different account — is only a warned last resort (#455).
    """
    settlement_wallet = None
    try:
        esc_conf = client.get("/v1/tasks/escrow-config")
        if isinstance(esc_conf, dict) and esc_conf.get("settlement_wallet"):
            settlement_wallet = str(esc_conf["settlement_wallet"])
    except Exception as e:  # noqa: BLE001 - coordinator probe is best-effort; local fallbacks follow
        logger.debug("escrow-config probe failed: %s", type(e).__name__)
    if not settlement_wallet:
        from ..utils.escrow import get_node_wallet

        try:
            settlement_wallet = get_node_wallet(ctx, rpc_url)
        except Exception as e:  # noqa: BLE001 - get_node_wallet may abort(); fail-open to proposer fallback
            logger.debug("node wallet lookup failed, using fallback: %s", type(e).__name__)
            settlement_wallet = None
    if not settlement_wallet:
        settlement_wallet = getattr(config, "hub_proposer_id", None) or None
        if settlement_wallet:
            warning(
                "Using HUB_PROPOSER_ID as escrow destination — it is the consensus proposer, "
                "not the node wallet; the settlement chain may reject the lock"
            )
    return settlement_wallet


def _buyer_signing(
    ctx,
    client: AITBCHTTPClient,
    buyer_agent: str | None,
    wallet_name: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    sign: bool,
) -> tuple[str, str, tuple[str, str] | None, str | None, str]:
    """Load the buyer wallet and derive the signing material for this hire.

    Returns (buyer_address, private_key, signing, signing_key, buyer_agent).
    ``buyer_agent=None`` resolves the agent bound to the signing wallet (see
    :func:`_resolve_buyer_agent`). The same wallet signs every negotiation
    envelope (doc §4) and the X-Agent-* inbox-poll headers. ``--no-sign``
    keeps the unsigned behaviour for coordinators still running with
    AGENT_MSG_SIGNATURE_MODE=disabled.
    """
    buyer_address, private_key, _ = load_wallet_for_payment(
        ctx, wallet_name=wallet_name, password=password, password_file=password_file, password_stdin=password_stdin
    )
    if not private_key:
        error("Escrow lock requires a buyer wallet with a private key")
        raise click.Abort()

    signing = (buyer_address, private_key) if sign else None
    signing_key = private_key if sign else None
    explicit_agent = buyer_agent
    buyer_agent = _resolve_buyer_agent(client, buyer_agent, buyer_address)
    if signing is not None:
        # Soft check only: the coordinator still accepts while advisory, and a
        # registry lookup failure must not block the escrowed hire. Implicit
        # buyer agents self-register when unauthenticated (#2983/#2979).
        binding_note = _ensure_buyer_agent_binding(
            client, buyer_agent, buyer_address, private_key, auto_register=explicit_agent is None
        )
        if binding_note:
            warning(f"{binding_note} — signed requests may be rejected once the coordinator enforces")
    return buyer_address, private_key, signing, signing_key, buyer_agent


# service_types whose provider-side endpoints sit behind the paid shop gate
# (#803): whisper ``/transcribe`` and ffmpeg ``/process`` require the
# X-Access-Key/X-Access-Secret/X-Job-Id triple verified against a market job
# token. ollama/ipfs handlers do not.
_SHOP_GATED_SERVICE_TYPES = frozenset({"whisper", "ffmpeg"})


def _agent_task_shop_token(service_type: str) -> dict[str, str]:
    """Mint the shop-gate credential triple for gated service types (#2743).

    Paid shop endpoints verify ``X-Access-Key``/``X-Access-Secret`` against
    ``GET /v1/market/access/{key}`` and bind ``X-Job-Id`` to that market job
    — a token only the buyer-side CLI can register (``POST /v1/market/jobs``).
    ``ai submit`` does the same for ``type=transcribe`` (#2316/#2322); the
    agent-task TaskRequest needs the identical triple in its content or the
    provider's whisper/ffmpeg call 401s and the paid task fails.

    The market job id must be minted *before* the ESCROW_LOCK is signed:
    the #2326 alias binding requires the lock payload to name the market
    job (``payload.market_job_id``), so the id is generated here and
    threaded into ``create_signed_escrow_lock`` — the same ordering
    ``ai submit`` uses (#2322). Returns ``{}`` for ungated types.
    """
    if service_type not in _SHOP_GATED_SERVICE_TYPES:
        return {}
    import secrets

    return {
        "market_job_id": f"ataskmkt_{uuid.uuid4().hex[:16]}",
        "access_key": secrets.token_urlsafe(16),
        "access_secret": secrets.token_urlsafe(32),
    }


def _register_agent_task_shop_token(
    ctx: click.Context,
    token: dict[str, str],
    service_type: str,
    task_id: str,
    buyer_address: str,
    provider_wallet: str,
    amount: Decimal,
    model: str | None,
    private_key: str,
) -> dict[str, str]:
    """Register the minted token as a market job bound to the task escrow (#2743).

    The market job id stays distinct from ``task_id`` (the on-chain
    ESCROW_LOCK key) exactly like ``ai submit``: it is a pure token record
    whose ``payload.escrow_job_id`` alias binds it to the atask escrow —
    the #2326 buyer-wallet signature covers that binding. Returns the
    content fields to merge into the TaskRequest, or ``{}`` when ``token``
    is empty / registration fails (the shop's own 401 remains the refusal).
    """
    if not token:
        return {}
    from .market.jobs import _register_paid_market_job

    registered = _register_paid_market_job(
        ctx,
        token["market_job_id"],
        {"model": model or ""},
        buyer_address,
        provider_wallet,
        service_type,
        amount,
        access_key=token["access_key"],
        access_secret=token["access_secret"],
        escrow_job_id=task_id,
        signer_key=private_key,
    )
    if registered is None:
        return {}
    return {
        "access_key": token["access_key"],
        "access_secret": token["access_secret"],
        "access_job_id": token["market_job_id"],
    }


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
    signing_key: str | None = None,
    market_job_id: str | None = None,
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
            market_job_id=market_job_id,
        )
    except _OPS_ERRORS as e:
        error(f"Failed to build escrow lock transaction: {e}")
        raise click.Abort() from e

    amount_units = ait_to_units(max_price_ait)
    # Enforce mode requires a resolvable principal; the buyer's X-Agent-* signed
    # headers carry the same wallet that signs the escrow lock and envelopes.
    headers = signed_request_headers(buyer_agent, signing_key) if signing_key else None
    try:
        submission = client.post(
            "/v1/tasks/submit",
            headers=headers,
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
    except _OPS_ERRORS as e:
        # #2738: a 502 here can still leave a persisted escrow (and sometimes a
        # sealed on-chain lock) behind. Look the task up before aborting so the
        # operator sees the real state instead of "nothing happened".
        escrow_state = None
        try:
            escrow_state = _task_escrow(client, task_id, buyer_agent, signing_key)
        except _OPS_ERRORS:
            escrow_state = None
        detail = http_error_detail(e) or str(e)
        status = http_response_status(e)
        answered = f"HTTP {status}" if status is not None else "a network error"
        if escrow_state:
            warning(
                f"Submit for task {task_id} failed ({answered}) but an escrow already exists "
                f"(escrow_id={escrow_state.get('escrow_id')} status={escrow_state.get('escrow_status')}). "
                "Do not re-hire blindly — inspect with `agent-task status` and resubmit the same "
                "task_id only if the escrow is still unresolved."
            )
        error(f"Task submission failed for {task_id}: {detail}")
        raise click.Abort() from e
    escrow_id = submission.get("escrow_id") if isinstance(submission, dict) else None
    if not escrow_id:
        error(f"Task submitted but no escrow was created — is TASK_PAYMENT_ESCROW_ENABLED on the coordinator? {submission}")
        raise click.Abort()
    return cast(str, escrow_id)


_RESULT_MAX_BYTES = 64 * 1024 * 1024


def _valid_result_ref(result_ref: object) -> str:
    """Bare-CID gate shared by both result fetch paths (#1971/#1939)."""
    import re as _re

    if not isinstance(result_ref, str) or not _re.fullmatch(r"[A-Za-z0-9]{1,256}", result_ref):
        error(f"Refusing malformed result_ref from provider: {result_ref!r}")
        raise click.Abort()
    return result_ref


# #2967: the local swarm read is the fast path when the buyer↔provider
# bitswap leg works — but when it is broken the read hangs to whatever
# timeout we set, so the fuse is short and the control-plane fallback
# takes over. 20s mirrors the miner executor's payload fuse (#2955).
_RESULT_LOCAL_FUSE_SECONDS = 20


def _fetch_result_capped(ipfs_api: str, result_ref: object, fuse: int = _RESULT_LOCAL_FUSE_SECONDS) -> bytes:
    """Fetch a provider-named result from the local Kubo daemon (#1971).

    result_ref is provider-controlled and Kubo resolves cat args as IPFS
    *paths*, so only a bare alphanumeric CID may reach the daemon (same gate as
    the miner's payload_ref check, #1939); the read is streamed and size-capped.
    Raises on failure — callers decide whether a fallback path exists.
    """
    import requests as _requests

    cid = _valid_result_ref(result_ref)
    with _requests.post(f"{ipfs_api}/api/v0/cat", params={"arg": cid}, timeout=(5, fuse), stream=True) as resp:
        resp.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > _RESULT_MAX_BYTES:
                raise ValueError(f"result exceeds {_RESULT_MAX_BYTES} bytes")
            chunks.append(chunk)
    return b"".join(chunks)


def _fetch_result_via_coordinator(
    client: AITBCHTTPClient,
    task_id: str,
    agent_id: str,
    signing_key: str | None,
) -> bytes:
    """Fetch the result through the coordinator's party-scoped proxy (#2967).

    The proxy streams the task's recorded result CID from the hub island
    daemon — the propagation-independent path when the direct buyer↔provider
    bitswap leg is broken. Signed with the same ``X-Agent-*`` headers as the
    inbox poll; the read is streamed and capped exactly like the local cat.
    """
    import requests as _requests

    headers = dict(client.headers or {})
    if signing_key:
        headers.update(signed_request_headers(agent_id, signing_key))
    url = f"{client.base_url}/v1/tasks/{task_id}/result"
    with _requests.get(url, headers=headers, timeout=(5, 120), stream=True) as resp:
        resp.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > _RESULT_MAX_BYTES:
                raise ValueError(f"result exceeds {_RESULT_MAX_BYTES} bytes")
            chunks.append(chunk)
    return b"".join(chunks)


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
            abort(ctx, f"Provider rejected the task: {found['task_reject'].get('reason', '')}")
        if not accepted and "task_quote" in found:
            quote = found["task_quote"]
            try:
                quoted = Decimal(str(quote.get("price", "0")))
            except (ArithmeticError, TypeError, ValueError):
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
            # #2955: a failed task refunds through the provider-signed fail
            # path (or the timeout sweeper as a backstop) — surface the
            # escrow state so the buyer sees where the money is without a
            # separate `agent-task status` call.
            escrow_state: dict[str, Any] = {}
            try:
                escrow = _task_escrow(client, task_id, buyer_agent, signing_key)
                if escrow:
                    escrow_state = {
                        "escrow_status": escrow.get("escrow_status"),
                        "tx_hash_refund": escrow.get("tx_hash_refund"),
                        "tx_hash_release": escrow.get("tx_hash_release"),
                    }
            except _OPS_ERRORS:
                escrow_state = {}
            output(
                {
                    "task_id": task_id,
                    "status": result.get("status"),
                    "result_ref": result.get("result_ref"),
                    "result_hash": result.get("result_hash"),
                    "tx_hash": paid.get("tx_hash"),
                    **escrow_state,
                },
                ctx.obj.get("output_format", "table"),
            )
            return
        time.sleep(5)
    warning(f"Timed out waiting for result after {wait_seconds}s — escrow will refund on expiry")
    output({"task_id": task_id, "escrow_id": escrow_id, "status": "waiting"}, ctx.obj.get("output_format", "table"))


def _retrieve_result_bytes(
    client: AITBCHTTPClient,
    task_id: str,
    buyer_agent: str,
    signing_key: str | None,
    result_ref: str,
) -> tuple[bytes, str]:
    """Fetch result bytes: local swarm fast path, coordinator-proxy fallback (#2967).

    The local swarm read is the fast path when the buyer↔provider bitswap
    leg works; when it is broken (or no local daemon runs at all) the
    coordinator's party-scoped proxy serves the same bytes over the
    authenticated control plane after a short fuse. result_hash verification
    at the call site is path-independent. Returns ``(data, served_by)``;
    aborts when both paths fail.
    """
    ipfs_api = _resolve_ipfs_api({})
    data: bytes | None = None
    served_by = ""
    local_error: Exception | None = None
    if _daemon_available(ipfs_api):
        try:
            data = _fetch_result_capped(ipfs_api, result_ref)
            served_by = "local-swarm"
        except _OPS_ERRORS as e:
            local_error = e
            warning(f"Local swarm read failed ({e}) — falling back to the coordinator proxy")
    try:
        if data is None:
            data = _fetch_result_via_coordinator(client, task_id, buyer_agent, signing_key)
            served_by = "coordinator-proxy"
    except _OPS_ERRORS as e:
        if local_error is not None:
            error(f"Could not fetch result {result_ref}: local swarm failed ({local_error}); proxy failed ({e})")
        else:
            error(f"Could not fetch result {result_ref} via coordinator proxy: {e}")
        raise click.Abort() from e
    return data, served_by


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
@wallet_password_options
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
    password_file: str | None,
    password_stdin: bool,
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
    client = AITBCHTTPClient(
        base_url=base_url,
        timeout=30,
        **auth_client_kwargs(ctx.obj.get("api_key") if ctx.obj else None, get_config().api_key),
    )
    max_price_ait = _parse_max_price(max_price)

    # 1. Payload → CID on the buyer's island daemon.
    payload_ref = _resolve_payload_ref(ctx, payload)
    if not payload_ref:
        raise click.Abort()

    # 2. Buyer wallet + signing material — resolved before the provider
    #    lookup because the registry read is principal-gated (#2431) and
    #    the X-Agent-* headers need the buyer agent + key.
    buyer_address, private_key, signing, signing_key, buyer_agent = _buyer_signing(
        ctx, client, _explicit_buyer_agent(from_agent), wallet_name, password, password_file, password_stdin, sign
    )

    # 3. Provider wallet from the agent registry, read as the buyer agent.
    provider_wallet = _resolve_provider_wallet(client, to_agent, signing_agent_id=buyer_agent, signing_key=signing_key)
    if not provider_wallet:
        raise click.Abort()

    # 4. Settlement wallet: see _settlement_wallet for the lookup order.
    rpc_url = _get_blockchain_rpc_url(config)
    settlement_wallet = _settlement_wallet(client, config, ctx, rpc_url)
    if not settlement_wallet:
        error(
            "No escrow settlement wallet available — coordinator /v1/tasks/escrow-config unreachable and HUB_PROPOSER_ID unset"
        )
        raise click.Abort()

    task_id = f"atask_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    # 5a. Shop-gate token for gated service types (#2743): the market job id
    # must be minted before the ESCROW_LOCK is signed — the #2326 alias
    # binding requires the lock payload to name it (``payload.market_job_id``),
    # same ordering ``ai submit`` uses (#2322). Registration happens after the
    # escrow locks; a failure degrades to the shop's own 401.
    shop_token = _agent_task_shop_token(service_type)

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
        signing_key,
        market_job_id=shop_token.get("market_job_id"),
    )
    success(f"Task {task_id} submitted — escrow {escrow_id} locked on-chain ({max_price_ait} AIT)")

    # 5b. Register the market job token bound to this task's on-chain escrow
    # (``payload.escrow_job_id`` alias + #2326 buyer signature) and carry the
    # credential triple in the TaskRequest content.
    shop_access = _register_agent_task_shop_token(
        ctx,
        shop_token,
        service_type,
        task_id,
        buyer_address,
        provider_wallet,
        max_price_ait,
        model,
        private_key,
    )

    # 6. Send the TaskRequest negotiation message.
    request_msg = {
        "task_id": task_id,
        "service_type": service_type,
        "model": model,
        "payload_ref": payload_ref,
        "max_price": str(max_price_ait),
        "deadline": None,
        "escrow_id": escrow_id,
        **shop_access,
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
@wallet_password_options
@click.option("--sign/--no-sign", default=True, show_default=True, help="Sign the inbox poll when a wallet is configured")
@click.option("--coordinator-url", default=None, help="Agent coordinator URL")
@click.pass_context
def status(
    ctx,
    task_id: str,
    from_agent: str | None,
    wallet_name: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    sign: bool,
    coordinator_url: str | None,
):
    """Show escrow state and negotiation progress for a task."""
    base_url = _coordinator_url(ctx, coordinator_url)
    client = AITBCHTTPClient(
        base_url=base_url,
        timeout=15,
        **auth_client_kwargs(ctx.obj.get("api_key") if ctx.obj else None, get_config().api_key),
    )
    signing_key = None
    wallet_address = None
    if sign:
        wallet = load_signing_wallet(
            ctx, wallet_name=wallet_name, password=password, password_file=password_file, password_stdin=password_stdin
        )
        if wallet:
            wallet_address, signing_key = wallet
    buyer_agent = _resolve_buyer_agent(client, from_agent, wallet_address)

    escrow: dict[str, Any] | None = None
    try:
        escrow = _task_escrow(client, task_id, buyer_agent, signing_key)
    except _OPS_ERRORS as e:
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
@wallet_password_options
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
    password_file: str | None,
    password_stdin: bool,
    sign: bool,
    coordinator_url: str | None,
):
    """Fetch a finished task's result payload from island IPFS."""
    base_url = _coordinator_url(ctx, coordinator_url)
    client = AITBCHTTPClient(
        base_url=base_url,
        timeout=15,
        **auth_client_kwargs(ctx.obj.get("api_key") if ctx.obj else None, get_config().api_key),
    )
    signing_key = None
    wallet_address = None
    if sign:
        wallet = load_signing_wallet(
            ctx, wallet_name=wallet_name, password=password, password_file=password_file, password_stdin=password_stdin
        )
        if wallet:
            wallet_address, signing_key = wallet
    buyer_agent = _resolve_buyer_agent(client, from_agent, wallet_address)

    found = _find_task_messages(_inbox(client, buyer_agent, signing_key=signing_key), task_id)
    task_result = found.get("task_result")
    if not task_result or not task_result.get("result_ref"):
        error(f"No result for task {task_id} yet (status: {task_result.get('status') if task_result else 'pending'})")
        raise click.Abort()

    result_ref = task_result["result_ref"]
    _valid_result_ref(result_ref)
    data, served_by = _retrieve_result_bytes(client, task_id, buyer_agent, signing_key, result_ref)
    if served_by == "coordinator-proxy":
        info("Result served by the coordinator proxy (local swarm path unavailable)")
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
