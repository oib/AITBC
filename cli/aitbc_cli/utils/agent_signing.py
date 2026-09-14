"""Client-side signing for coordinator agent messages (v2.0 Phase B2).

Implements the CLI half of ``docs/agent-coordinator/agent-signed-envelopes.md``
on top of :mod:`aitbc.crypto.agent_envelope` (Phase A):

* **Message envelopes** (§4) — ``sign_send_envelope`` populates the
  ``signer``/``signature``/``signature_version``/``timestamp``/``nonce`` fields
  on a ``POST /api/v1/agent/messages/send`` body. The signature covers *every*
  ``SendMessageRequest`` field except ``signature`` — the coordinator verifies
  over ``model_dump(exclude={"signature"})``, which includes model defaults
  for fields the client omitted, so this module always signs (and posts) the
  complete field set.

* **Signed read requests** — ``signed_request_headers`` emits the
  ``X-Agent-Id``/``X-Agent-Signature``/``X-Agent-Timestamp``/``X-Agent-Nonce``
  headers the coordinator's read-path verifier checks (inbox/history/etc.).
  The signature covers ``keccak256("aitbc-agent-req-v1:" + canonical_json(
  {"agent_id","timestamp","nonce"}))``. Phase B1 may add a ``request_claim``
  helper to ``aitbc.crypto.agent_envelope``; the byte-level convention is
  fixed either way, so the inline construction here stays correct.

* **Registration attestation** (§3) — ``identity_attestation_fields`` fetches a
  one-time nonce from ``GET /v1/agents/nonce`` and returns the
  ``identity_address``/``identity_proof``/``identity_nonce``/``registered_at``
  fields for ``POST /v1/agents/register``.

Signing is additive: while the coordinator runs
``AGENT_MSG_SIGNATURE_MODE=disabled|advisory`` unsigned traffic still works, so
every call site signs only when the operator configured a wallet
(``--wallet``/``AITBC_DEFAULT_WALLET``) or — where a wallet is loaded anyway
(``agent-task hire``) — unless ``--no-sign`` is passed.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

from aitbc.crypto.agent_envelope import (
    AGENT_MSG_SIGNATURE_VERSION,
    AGENT_REQ_DOMAIN,
    identity_claim,
    login_claim,
    request_claim,
    sign_agent_envelope,
    sign_identity_claim,
    sign_login_claim,
    sign_request_claim,
)
from aitbc.crypto.signature_recovery import canonical_address

from .wallet_loader import load_wallet_for_payment

#: Domain prefix for signed read-request headers (X-Agent-*). Distinct from the
#: message-envelope domain so an inbox poll signature cannot be replayed as a
#: message. Alias of aitbc.crypto.agent_envelope.AGENT_REQ_DOMAIN (Phase B1).
AGENT_REQ_SIGNATURE_DOMAIN = AGENT_REQ_DOMAIN

#: Header names for signed read requests against the coordinator.
AGENT_ID_HEADER = "X-Agent-Id"
AGENT_SIGNATURE_HEADER = "X-Agent-Signature"
AGENT_TIMESTAMP_HEADER = "X-Agent-Timestamp"
AGENT_NONCE_HEADER = "X-Agent-Nonce"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def signing_wallet_name(wallet_name: str | None = None) -> str | None:
    """The wallet requested for message signing, or ``None``.

    Signing only engages when the operator opted in: an explicit ``--wallet``
    or ``AITBC_DEFAULT_WALLET`` in the environment. Unlike
    :func:`load_wallet_for_payment` there is deliberately *no* ``default``
    wallet fallback here — signing must stay opt-in so unsigned flows keep
    working while the coordinator is in disabled/advisory mode.
    """
    return wallet_name or os.environ.get("AITBC_DEFAULT_WALLET") or None


def load_signing_wallet(ctx, wallet_name: str | None = None, password: str | None = None) -> tuple[str, str] | None:
    """Load ``(address, private_key)`` for signing, or ``None`` when not configured.

    Returns ``None`` iff neither ``--wallet`` nor ``AITBC_DEFAULT_WALLET`` was
    given — the caller then sends unsigned. When a wallet *was* configured but
    cannot be loaded, :func:`load_wallet_for_payment` aborts with its usual
    diagnostics (an explicit request should fail loudly, not silently degrade
    to unsigned).
    """
    name = signing_wallet_name(wallet_name)
    if name is None:
        return None
    address, private_key, _ = load_wallet_for_payment(ctx, wallet_name=name, password=password)
    if not private_key:
        raise ValueError(f"Wallet '{name}' has no usable private key for signing")
    return address, private_key


def sign_send_envelope(body: dict[str, Any], signer_address: str, private_key: str) -> dict[str, Any]:
    """Return ``body`` with the §4 envelope signature fields populated.

    ``body`` is the ``SendMessageRequest`` payload being posted. The signed
    bytes cover the coordinator's ``signing_payload()`` —
    ``model_dump(exclude={"signature"})`` — so every model field is present in
    the signed dict with exactly the value the server model will hold: model
    defaults are filled in for absent optional fields and the returned dict is
    meant to be posted verbatim.
    """
    signed = dict(body)
    signed.setdefault("message_type", "direct")
    signed.setdefault("encrypt", True)
    signed.setdefault("priority", "normal")
    signed.setdefault("ttl", 300)
    signed.setdefault("message_id", None)
    signed["signer"] = signer_address
    signed["signature_version"] = AGENT_MSG_SIGNATURE_VERSION
    signed["timestamp"] = _iso_now()
    signed["nonce"] = uuid.uuid4().hex
    signed["signature"] = sign_agent_envelope(signed, private_key)
    return signed


def request_signature_claim(agent_id: str, timestamp: str, nonce: str) -> dict[str, Any]:
    """The canonical dict an ``X-Agent-Signature`` header signs."""
    return {"agent_id": agent_id, "nonce": nonce, "timestamp": timestamp}


def signed_request_headers(agent_id: str, private_key: str) -> dict[str, str]:
    """The four ``X-Agent-*`` headers authenticating a read request.

    The signature covers ``{"agent_id","timestamp","nonce"}`` under
    :data:`AGENT_REQ_SIGNATURE_DOMAIN` — the read-request convention the
    coordinator checks on inbox/history-style routes.
    """
    timestamp = _iso_now()
    nonce = uuid.uuid4().hex
    signature = sign_request_claim(request_claim(agent_id=agent_id, timestamp=timestamp, nonce=nonce), private_key)
    return {
        AGENT_ID_HEADER: agent_id,
        AGENT_SIGNATURE_HEADER: signature,
        AGENT_TIMESTAMP_HEADER: timestamp,
        AGENT_NONCE_HEADER: nonce,
    }


def identity_attestation_fields(
    client,
    agent_id: str,
    identity_address: str,
    chain_id: str | None,
    private_key: str,
) -> dict[str, Any]:
    """Fetch a registration nonce and build the ``identity_*`` request fields.

    ``client`` is an ``AITBCHTTPClient`` pointed at the coordinator. The claim
    mirrors what the coordinator rebuilds in ``_verify_identity_attestation``
    — including ``chain_id or ""`` when the registration request carries no
    chain.
    """
    resp = client.get("/v1/agents/nonce", params={"agent_id": agent_id})
    nonce = resp.get("nonce") if isinstance(resp, dict) else None
    if not nonce:
        raise ValueError(f"Coordinator did not issue a registration nonce for {agent_id}: {resp}")
    registered_at = _iso_now()
    claim = identity_claim(
        agent_id=agent_id,
        identity_address=identity_address,
        chain_id=chain_id or "",
        nonce=nonce,
        registered_at=registered_at,
    )
    return {
        "identity_address": identity_address,
        "identity_proof": sign_identity_claim(claim, private_key),
        "identity_nonce": nonce,
        "registered_at": registered_at,
    }


def check_registry_binding(client, agent_id: str, address: str) -> str | None:
    """Check that ``agent_id`` is registered and bound to ``address``.

    Returns an operator-facing error string on a definitive problem (agent
    unknown, unbound, or bound to a different key) and ``None`` when the
    binding matches. Returns ``None`` on lookup *failure* (coordinator
    unreachable, etc.) — the signed send then proceeds and the coordinator's
    own verification decides; a transient lookup error must not block traffic
    that advisory mode would accept.
    """
    try:
        data = client.get(f"/v1/agents/{agent_id}")
    except Exception as e:
        if "404" in str(e):
            return (
                f"Agent '{agent_id}' is not registered with the coordinator — register it first with "
                f"`aitbc agent-comm register --agent-id {agent_id} --wallet ...`, or send without --wallet "
                "while the coordinator accepts unsigned envelopes"
            )
        return None
    agent = data.get("agent") if isinstance(data, dict) else None
    if not agent:
        return f"Agent '{agent_id}' is not registered with the coordinator (empty registry record)"
    bound = agent.get("identity_address")
    if not bound:
        return (
            f"Agent '{agent_id}' is registered but has no bound identity — re-register with --wallet to bind "
            "your key, or send without --wallet"
        )
    try:
        mismatch = canonical_address(bound) != canonical_address(address)
    except Exception:
        mismatch = True
    if mismatch:
        return (
            f"Agent '{agent_id}' is bound to identity {bound} but the signing wallet is {address} — "
            "use the bound wallet (or rotate via PUT /v1/agents/{agent_id}/identity)"
        )
    return None


def find_agent_by_identity(client, address: str) -> str | None:
    """Scan the registry for an agent bound to ``address``; returns agent_id."""
    try:
        data = client.post("/v1/agents/discover", json={"limit": 1000})
    except Exception:
        return None
    agents = data.get("agents", []) if isinstance(data, dict) else []
    try:
        wanted = canonical_address(address)
    except Exception:
        return None
    for agent in agents:
        bound = agent.get("identity_address") if isinstance(agent, dict) else None
        if bound:
            try:
                if canonical_address(bound) == wanted:
                    return str(agent.get("agent_id"))
            except Exception:
                continue
    return None


def agent_login_token(
    client,
    agent_id: str,
    wallet_address: str,
    private_key: str,
    chain_id: str | None = None,
) -> str | None:
    """Run the Phase B1 wallet-login exchange; returns an agent JWT or None.

    POST /api/v1/agent/auth/nonce?agent_id=... issues a one-time nonce and
    echoes the coordinator's chain_id; the wallet then signs
    login_claim(agent_id, wallet_address, chain_id, nonce) and
    POST /api/v1/agent/auth/login exchanges it for a JWT carrying
    agent_id + wallet claims (role agent). The endpoint rejects
    agents that are not identity-bound, so agent_id must already be
    registered to wallet_address.

    Returns None on any transport/endpoint failure — callers fall back to
    the shared API-key token so older coordinators (no login endpoint) keep
    working. Raises only for a malformed 200 response.
    """
    try:
        nonce_resp = client.post(f"/api/v1/agent/auth/nonce?agent_id={agent_id}")
    except Exception:
        return None
    nonce = nonce_resp.get("nonce") if isinstance(nonce_resp, dict) else None
    if not nonce:
        return None
    effective_chain = chain_id or nonce_resp.get("chain_id") or ""
    claim = login_claim(
        agent_id=agent_id,
        wallet_address=wallet_address,
        chain_id=effective_chain,
        nonce=nonce,
    )
    try:
        login_resp = client.post(
            "/api/v1/agent/auth/login",
            json={
                "agent_id": agent_id,
                "wallet_address": wallet_address,
                "nonce": nonce,
                "signature": sign_login_claim(claim, private_key),
                "chain_id": effective_chain or None,
            },
        )
    except Exception:
        return None
    token = login_resp.get("access_token") if isinstance(login_resp, dict) else None
    return str(token) if token else None
