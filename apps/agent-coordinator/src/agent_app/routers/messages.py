import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.agent_envelope import AGENT_MSG_SIGNATURE_VERSION, recover_agent_envelope_signer
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.rate_limiting import rate_limit

from .. import state
from ..config import settings
from ..encryption import get_encryptor
from ..models import BroadcastRequest
from ..protocols.communication import MessageType
from ..routing.load_balancer import LoadBalancingStrategy
from ..services.agent_auth import AgentPrincipal, authorize_admin_scope, authorize_agent_scope, optional_agent
from ..services.nonce_store import get_nonce_store
from ..websocket import get_connection_manager

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/agent/messages", tags=["agent-messaging"])

# FastAPI dependency alias used across the read/subscribe endpoints below:
# resolves the caller's principal if credentials are present, ``None``
# otherwise. Scope enforcement is flag-driven via agent_msg_signature_mode.
OptionalAgent = Annotated[AgentPrincipal | None, Depends(optional_agent)]


def _message_parties(message: dict[str, Any]) -> tuple[str | None, str | None]:
    """``(sender, receiver)`` across the two record spellings (``sender`` /
    ``sender_id``, ``recipient`` / ``receiver_id``) — same convention as
    ``MessageStorage._extract_*``."""
    return message.get("sender") or message.get("sender_id"), message.get("recipient") or message.get("receiver_id")


def _authorize_message_party(principal: AgentPrincipal | None, message: dict[str, Any], action: str) -> None:
    """Enforce-mode party check for message-id routes that carry no agent_id.

    ``enforce``: the principal must be a party to the message — sender or
    receiver for reads, receiver only for ``mark_read`` (the read flag is the
    receiver's state). ``advisory``: mismatches log and pass. ``disabled`` and
    admin principals are untouched.
    """
    mode = settings.agent_msg_signature_mode
    if mode == "disabled":
        return
    if principal is None:
        if mode == "enforce":
            raise HTTPException(
                status_code=401, detail="agent authentication required", headers={"WWW-Authenticate": "Bearer"}
            )
        return
    if principal.is_admin:
        return
    sender, receiver = _message_parties(message)
    allowed = principal.agent_id in (sender, receiver)
    if action == "mark_read":
        allowed = principal.agent_id == receiver
    if not allowed:
        if mode == "enforce":
            raise HTTPException(status_code=403, detail="agent_mismatch")
        logger.warning(
            "agent_authz_mismatch action=%s principal=%s sender=%s receiver=%s mode=%s",
            action,
            principal.agent_id,
            sender,
            receiver,
            mode,
        )


async def _agent_own_history(agent_id: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    """``(page, known_total)`` of messages where ``agent_id`` is sender OR
    receiver — the enforce-mode ``/history`` view for non-admin principals,
    which must never widen to ``get_all_messages``."""
    storage = state.message_storage
    if storage is None:
        raise HTTPException(status_code=503, detail="Message storage not available")
    fetch = limit + offset
    sent = await storage.get_messages_by_sender(agent_id, fetch, 0)
    received = await storage.get_messages_by_receiver(agent_id, fetch, 0)
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for message in sorted(sent + received, key=lambda m: str(m.get("timestamp", "")), reverse=True):
        key = str(message.get("message_id") or message.get("id") or id(message))
        if key in seen:
            continue
        seen.add(key)
        merged.append(message)
    return merged[offset : offset + limit], len(merged)


def _resolve_history_scope(
    principal: AgentPrincipal | None,
    sender_id: str | None,
    receiver_id: str | None,
    mode: str,
) -> str | None:
    """Resolve which agent_id a ``/history`` caller is scoped to, if any.

    Enforce/advisory modes scope an authenticated non-admin principal to its
    own records: mismatched ``sender_id``/``receiver_id`` filters go through
    ``authorize_agent_scope`` (403 in enforce, logged in advisory) and an
    unfiltered advisory query logs ``agent_authz_unscoped``. ``enforce`` with
    no principal delegates to ``authorize_agent_scope`` for the 401. Returns
    the principal's agent_id when scoped, ``None`` otherwise.
    """
    if mode != "disabled" and principal is not None and not principal.is_admin:
        scoped_agent = principal.agent_id
        if sender_id is not None and sender_id != scoped_agent:
            authorize_agent_scope(principal, sender_id, "history")
        if receiver_id is not None and receiver_id != scoped_agent:
            authorize_agent_scope(principal, receiver_id, "history")
        if sender_id is None and receiver_id is None and mode == "advisory":
            logger.warning(
                "agent_authz_unscoped action=history principal=%s mode=%s — enforce would restrict to own records",
                scoped_agent,
                mode,
            )
        return scoped_agent
    if mode == "enforce" and principal is None:
        authorize_agent_scope(principal, "", "history")
    return None


class SendMessageRequest(BaseModel):
    """Request to send encrypted message"""

    sender: str = Field(..., description="Sender agent ID")
    recipient: str = Field(..., description="Recipient agent ID")
    content: dict[str, Any] = Field(..., description="Message content")
    message_type: str = Field(default="direct", description="Message type")
    encrypt: bool = Field(default=True, description="Whether to encrypt message")
    priority: str = Field(default="normal", description="Message priority")
    ttl: int = Field(default=300, description="Time to live in seconds")
    message_id: str | None = Field(default=None, description="Client-provided message ID for idempotency")
    # v2.0 phase A signed-envelope fields
    # (docs/agent-coordinator/agent-signed-envelopes.md §4). ``signature`` is
    # secp256k1 over keccak256("aitbc-agent-msg-v1:" + canonical_json(
    # signing_payload())) — i.e. it covers every field here, not just content.
    signer: str | None = Field(default=None, description="secp256k1 address that signed the envelope")
    signature: str | None = Field(default=None, description="0x-prefixed signature over signing_payload()")
    signature_version: str = Field(default=AGENT_MSG_SIGNATURE_VERSION, description="Envelope signature scheme")
    timestamp: str | None = Field(default=None, description="Client ISO-8601 timestamp covered by the signature")
    nonce: str | None = Field(default=None, description="Client nonce for (sender, nonce) replay dedup")

    def signing_payload(self) -> dict[str, Any]:
        """Canonical signed dict — every request field except ``signature``."""
        return self.model_dump(exclude={"signature"})


class SubscribeRequest(BaseModel):
    """Request to subscribe to topic"""

    agent_id: str = Field(..., description="Agent ID")
    topic: str = Field(..., description="Topic to subscribe to")
    filter: dict[str, Any] = Field(default_factory=dict, description="Filter criteria")


def _coerce_bool(value: Any) -> bool:
    """Coerce a stored string/bool value back to bool."""
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes")


async def _sender_bound_identity(sender: str, recovered: str) -> str | None:
    """Check the sender's registry-bound identity against the recovered signer.

    Returns the failure reason (``unbound_sender`` | ``identity_mismatch``)
    or ``None`` when the recovered key matches the bound identity.
    """
    agent = None
    if state.agent_registry:
        try:
            agent = await state.agent_registry.get_agent_by_id(sender)
        except Exception as e:
            logger.warning("Registry lookup for sender %s failed: %s", sender, e)
    if agent is None or not agent.identity_address:
        return "unbound_sender"
    if canonical_address(agent.identity_address) != canonical_address(recovered):
        return "identity_mismatch"
    return None


async def _check_envelope_freshness(req: SendMessageRequest) -> str | None:
    """Check the envelope timestamp skew and nonce replay.

    Returns the failure reason (``missing_timestamp`` | ``stale_timestamp`` |
    ``nonce_replayed``) or ``None`` when the envelope is fresh.
    """
    if not req.timestamp:
        return "missing_timestamp"
    try:
        sent_at = datetime.fromisoformat(req.timestamp)
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=UTC)
    except ValueError:
        return "stale_timestamp"
    window = max(settings.agent_msg_max_skew_seconds, req.ttl)
    if abs((datetime.now(UTC) - sent_at).total_seconds()) > window:
        return "stale_timestamp"
    if req.nonce and not await get_nonce_store().check_message_nonce(req.sender, req.nonce, window):
        return "nonce_replayed"
    return None


async def _verify_message_signature(req: SendMessageRequest) -> tuple[str, str | None]:
    """Verify an envelope signature per agent-signed-envelopes.md §5.

    Returns ``(signature_status, failure_reason)``. ``signature_status`` —
    ``verified`` | ``invalid`` | ``unsigned`` — is stamped on the stored
    record; the reason feeds the ``msg_sig_verify=fail`` log line and becomes
    the 403 detail in enforce mode.
    """
    if not req.signature or not req.signer:
        return "unsigned", "missing_signature"
    if req.signature_version != AGENT_MSG_SIGNATURE_VERSION:
        return "invalid", "unknown_signature_version"
    recovered = recover_agent_envelope_signer(req.signing_payload(), req.signature)
    if recovered is None or canonical_address(recovered) != canonical_address(req.signer):
        return "invalid", "invalid_signature"
    identity_failure = await _sender_bound_identity(req.sender, recovered)
    if identity_failure is not None:
        return "invalid", identity_failure
    freshness_failure = await _check_envelope_freshness(req)
    if freshness_failure is not None:
        return "invalid", freshness_failure
    return "verified", None


def _stamp_envelope_fields(message_data: dict[str, Any], req: SendMessageRequest, signature_status: str | None) -> None:
    """Persist the signed-envelope fields on the stored/delivered record.

    The RSA-encrypted record already owns the flat ``signature``/``nonce``
    keys, so there the envelope values go under ``envelope_*``; the plaintext
    path uses the doc's flat names. ``signature_status`` is coordinator-stamped
    (never signed) and ``client_timestamp`` keeps the signed timestamp distinct
    from the record's own ``timestamp``.
    """
    rsa_owned = "signature" in message_data

    def _put(key: str, value: Any) -> None:
        if value is not None:
            message_data[key] = value

    _put("signer", req.signer)
    _put("signature_version", req.signature_version)
    _put("client_timestamp", req.timestamp)
    _put("ttl", req.ttl)
    if rsa_owned:
        _put("envelope_signature", req.signature)
        _put("envelope_nonce", req.nonce)
    else:
        _put("signature", req.signature)
        _put("nonce", req.nonce)
    if signature_status is not None:
        message_data["signature_status"] = signature_status


@router.post("/send")
@rate_limit(rate=50, per=60)
async def send_encrypted_message(request: Request, req: SendMessageRequest) -> dict[str, Any]:
    """Send encrypted message to agent, trying WebSocket first then storage.

    A client-provided ``message_id`` makes the call idempotent: if a message
    with that ID already exists, the existing record is returned without
    re-sending.  After the first call the message status is ``pending`` until
    the WebSocket layer confirms delivery (``delivered``).
    """
    try:
        message_id = req.message_id or f"msg_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

        # Idempotency check: return the existing record if present.
        if state.message_storage:
            try:
                existing = await state.message_storage.get_message(message_id)
                if existing:
                    return {
                        "status": "success",
                        "message_id": message_id,
                        "sender": existing.get("sender", req.sender),
                        "recipient": existing.get("recipient", req.recipient),
                        "encrypted": _coerce_bool(existing.get("encrypted", "False")),
                        "ws_delivered": _coerce_bool(existing.get("ws_delivered", "False")),
                        "message_status": existing.get("status", "unknown"),
                        "signature_status": existing.get("signature_status"),
                        "sent_at": existing.get("sent_at", ""),
                    }
            except Exception as e:
                logger.warning("Could not check idempotency for %s: %s", message_id, e)

        # Phase A envelope verification (agent-signed-envelopes.md §5):
        # advisory verifies-and-logs and stamps ``signature_status``; enforce
        # rejects. ``disabled`` (the in-code default) changes nothing.
        signature_mode = settings.agent_msg_signature_mode
        signature_status: str | None = None
        if signature_mode != "disabled":
            signature_status, sig_fail_reason = await _verify_message_signature(req)
            if signature_status != "verified":
                logger.warning(
                    "msg_sig_verify=fail sender=%s reason=%s message_id=%s mode=%s",
                    req.sender,
                    sig_fail_reason,
                    message_id,
                    signature_mode,
                )
                if signature_mode == "enforce":
                    raise HTTPException(status_code=403, detail=sig_fail_reason or "invalid_signature")

        encryptor = get_encryptor()
        message_content = {
            "content": req.content,
            "message_type": req.message_type,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if req.encrypt:
            encrypted_msg = encryptor.encrypt_message(
                message=message_content, sender_id=req.sender, recipient_id=req.recipient
            )
            if not encrypted_msg:
                raise HTTPException(status_code=500, detail="Failed to encrypt message")
            message_data = encrypted_msg.to_dict()
            message_data["encrypted"] = True
        else:
            message_data = {
                "sender": req.sender,
                "recipient": req.recipient,
                "content": json.dumps(req.content),
                "message_type": req.message_type,
                "encrypted": False,
                "priority": req.priority,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        # Ensure encrypted payloads also carry the index/forwarding keys
        # used by the WebSocket layer and MessageStorage.
        message_data.setdefault("sender", req.sender)
        message_data.setdefault("recipient", req.recipient)
        message_data.setdefault("message_type", req.message_type)
        message_data.setdefault("priority", req.priority)

        _stamp_envelope_fields(message_data, req, signature_status)

        # Try real-time WebSocket delivery first; fall back to storage.
        ws_delivered = False
        if req.recipient:
            try:
                connection_manager = get_connection_manager()
                ws_delivered = await connection_manager.send_personal_message(message_data, req.recipient)
            except Exception as e:
                logger.warning("Could not deliver message to %s over WebSocket: %s", req.recipient, e)

        status = "delivered" if ws_delivered else "pending"
        sent_at = datetime.now(UTC).isoformat()

        message_data["ws_delivered"] = ws_delivered
        message_data["status"] = status
        message_data["sent_at"] = sent_at

        if state.message_storage:
            redis_message_data = {k: str(v) if not isinstance(v, str) else v for k, v in message_data.items()}
            redis_message_data["message_id"] = message_id
            await state.message_storage.store_message(message_id, redis_message_data)
            # Update to delivered explicitly so the record reflects the actual outcome.
            if ws_delivered:
                await state.message_storage.update_message_status(message_id, "delivered")

        return {
            "status": "success",
            "message_id": message_id,
            "sender": req.sender,
            "recipient": req.recipient,
            "encrypted": req.encrypt,
            "ws_delivered": ws_delivered,
            "message_status": status,
            "signature_status": signature_status,
            "sent_at": sent_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error sending encrypted message: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/inbox")
@rate_limit(rate=200, per=60)
async def get_inbox(
    request: Request,
    principal: OptionalAgent,
    agent_id: str = Query(..., description="Agent ID"),
    limit: int = Query(100, description="Maximum messages"),
    unread_only: bool = Query(False, description="Only unread messages"),
) -> dict[str, Any]:
    """Get agent's inbox. Enforce mode: only the bound principal (or an admin)
    may read an agent's inbox; advisory/disabled keep the open read."""
    authorize_agent_scope(principal, agent_id, "inbox")
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "messages": [], "count": 0, "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, limit, 0)
        if unread_only:
            messages = [m for m in messages if not m.get("read", False) and m.get("status", "pending") != "read"]
        return {"agent_id": agent_id, "messages": messages, "count": len(messages), "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting inbox: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/history")
@rate_limit(rate=200, per=60)
async def get_message_history(
    request: Request,
    principal: OptionalAgent,
    sender_id: str | None = Query(None, description="Filter by sender ID"),
    receiver_id: str | None = Query(None, description="Filter by receiver ID"),
    limit: int = Query(100, description="Maximum number of messages"),
    offset: int = Query(0, description="Offset for pagination"),
) -> dict[str, Any]:
    """Get message history with optional filters.

    Enforce mode: an authenticated non-admin principal may only read its own
    records — ``sender_id``/``receiver_id`` filters must equal its agent_id,
    and an unfiltered query returns only messages it is a party to (never
    ``get_all_messages``). Admin principals keep the full view. Advisory and
    disabled keep the historical open behaviour (mismatches are logged).
    """
    mode = settings.agent_msg_signature_mode
    scoped_agent = _resolve_history_scope(principal, sender_id, receiver_id, mode)
    try:
        if not state.message_storage:
            raise HTTPException(status_code=503, detail="Message storage not available")
        if scoped_agent is not None and sender_id is None and receiver_id is None and mode == "enforce":
            messages, total = await _agent_own_history(scoped_agent, limit, offset)
        elif sender_id:
            messages = await state.message_storage.get_messages_by_sender(sender_id, limit, offset)
            total = await state.message_storage.get_message_count()
        elif receiver_id:
            messages = await state.message_storage.get_messages_by_receiver(receiver_id, limit, offset)
            total = await state.message_storage.get_message_count()
        else:
            messages = await state.message_storage.get_all_messages(limit, offset)
            total = await state.message_storage.get_message_count()
        return {
            "status": "success",
            "messages": messages,
            "count": len(messages),
            "total": total,
            "limit": limit,
            "offset": offset,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving message history: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/discover")
@rate_limit(rate=200, per=60)
async def discover_agents(
    request: Request,
    capability: str | None = Query(None, description="Filter by capability"),
    agent_type: str | None = Query(None, description="Filter by agent type"),
    min_health_score: float = Query(0.0, description="Minimum health score"),
    limit: int = Query(50, description="Maximum results"),
) -> dict[str, Any]:
    """Discover agents by criteria"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        query: dict[str, Any] = {}
        if capability:
            query["capabilities"] = [capability]
        if agent_type:
            query["agent_type"] = agent_type
        if min_health_score > 0:
            query["min_health_score"] = min_health_score
        if limit:
            query["limit"] = limit
        agents = await state.agent_registry.discover_agents(query)
        return {
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "query": query,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error discovering agents: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/subscribe")
@rate_limit(rate=50, per=60)
async def subscribe_to_topic(request: Request, req: SubscribeRequest, principal: OptionalAgent) -> dict[str, Any]:
    """Subscribe agent to topic and persist the subscription.

    Enforce mode: only the bound principal (or an admin) may subscribe an
    agent; advisory/disabled keep the open behaviour."""
    authorize_agent_scope(principal, req.agent_id, "subscribe")
    try:
        if not state.message_storage:
            raise HTTPException(status_code=503, detail="Message storage not available")
        success = await state.message_storage.add_subscription(req.agent_id, req.topic, req.filter)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to persist subscription")

        # If the agent is currently connected, also activate the subscription in memory.
        try:
            connection_manager = get_connection_manager()
            if req.agent_id in connection_manager.active_connections:
                await connection_manager.subscribe(req.agent_id, req.topic)
        except Exception as e:
            logger.warning("Could not activate online subscription for %s: %s", req.agent_id, e)

        return {
            "status": "success",
            "agent_id": req.agent_id,
            "topic": req.topic,
            "subscribed_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error subscribing to topic: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/unsubscribe")
@rate_limit(rate=50, per=60)
async def unsubscribe_from_topic(request: Request, req: SubscribeRequest, principal: OptionalAgent) -> dict[str, Any]:
    """Unsubscribe agent from topic and remove the persisted subscription.

    Enforce mode: only the bound principal (or an admin) may unsubscribe an
    agent; advisory/disabled keep the open behaviour."""
    authorize_agent_scope(principal, req.agent_id, "unsubscribe")
    try:
        if not state.message_storage:
            raise HTTPException(status_code=503, detail="Message storage not available")
        success = await state.message_storage.remove_subscription(req.agent_id, req.topic)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to remove subscription")

        # If the agent is currently connected, also deactivate the subscription in memory.
        try:
            connection_manager = get_connection_manager()
            if req.agent_id in connection_manager.active_connections:
                await connection_manager.unsubscribe(req.agent_id, req.topic)
        except Exception as e:
            logger.warning("Could not deactivate online subscription for %s: %s", req.agent_id, e)

        return {
            "status": "success",
            "agent_id": req.agent_id,
            "topic": req.topic,
            "unsubscribed_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error unsubscribing from topic: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/subscriptions/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_agent_subscriptions(request: Request, agent_id: str, principal: OptionalAgent) -> dict[str, Any]:
    """Get persisted topic subscriptions for an agent.

    Enforce mode: only the bound principal (or an admin) may read an agent's
    subscriptions; advisory/disabled keep the open behaviour."""
    authorize_agent_scope(principal, agent_id, "subscriptions")
    try:
        if not state.message_storage:
            raise HTTPException(status_code=503, detail="Message storage not available")
        subscriptions = await state.message_storage.get_subscriptions(agent_id)
        return {
            "status": "success",
            "agent_id": agent_id,
            "subscriptions": subscriptions,
            "count": len(subscriptions),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving subscriptions for %s: %s", agent_id, e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/broadcast")
@rate_limit(rate=50, per=60)
async def broadcast_message(request_http: Request, request: BroadcastRequest, principal: OptionalAgent) -> dict[str, Any]:
    """Broadcast message to multiple agents.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a
    no-op. The stored sender stays the derived ``agent-coordinator`` — the
    broadcast speaks as the coordinator, never as the caller.
    """
    authorize_admin_scope(principal, "broadcast")
    try:
        if not state.communication_manager:
            raise HTTPException(status_code=503, detail="Communication manager not available")
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        from ..protocols.communication import AgentMessage, Priority

        try:
            message_type = MessageType(request.message_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid message type: {request.message_type}") from None
        try:
            priority = Priority(request.priority.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {request.priority}") from None
        query: dict[str, Any] = {}
        if request.agent_type:
            query["agent_type"] = request.agent_type
        if request.capabilities:
            query["capabilities"] = request.capabilities
        agents = await state.agent_registry.discover_agents(query)
        if not agents:
            return {
                "status": "success",
                "message": "No matching agents found",
                "recipients": [],
                "count": 0,
                "broadcast_at": datetime.now(UTC).isoformat(),
            }
        recipients = []
        for agent in agents:
            message = AgentMessage(
                sender_id="agent-coordinator",
                receiver_id=agent.agent_id,
                message_type=message_type,
                priority=priority,
                payload=request.payload,
            )
            message_data = {
                "sender_id": message.sender_id,
                "receiver_id": message.receiver_id,
                "message_type": message.message_type.value,
                "priority": message.priority.value,
                "payload": json.dumps(message.payload),
                "protocol": "broadcast",
                "timestamp": datetime.now(UTC).isoformat(),
            }
            if state.message_storage:
                await state.message_storage.store_message(message.id, message_data)
                recipients.append(agent.agent_id)
            if state.communication_manager:
                await state.communication_manager.send_message("broadcast", message)
        return {
            "status": "success",
            "message": f"Broadcast sent to {len(recipients)} agents",
            "recipients": recipients,
            "count": len(recipients),
            "broadcast_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error broadcasting message: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/id/{message_id}")
@rate_limit(rate=200, per=60)
async def get_message(request: Request, message_id: str, principal: OptionalAgent) -> dict[str, Any]:
    """Get a specific message by ID.

    Enforce mode: only a party to the message (sender or receiver — or an
    admin) may read it; advisory/disabled keep the open read."""
    try:
        if not state.message_storage:
            raise HTTPException(status_code=503, detail="Message storage not available")
        message = await state.message_storage.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail=f"Message {message_id} not found")
        _authorize_message_party(principal, message, "get_message")
        return {"status": "success", "message": message, "timestamp": datetime.now(UTC).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving message %s: %s", message_id, e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/id/{message_id}/read")
@rate_limit(rate=50, per=60)
async def mark_message_read(request: Request, message_id: str, principal: OptionalAgent) -> dict[str, Any]:
    """Mark a specific message as read.

    Enforce mode: only the message's receiver (or an admin) may mark it read —
    the read flag is the receiver's state, so the sender may not flip it;
    advisory/disabled keep the open behaviour."""
    try:
        if not state.message_storage:
            raise HTTPException(status_code=503, detail="Message storage not available")
        message = await state.message_storage.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail=f"Message {message_id} not found")
        _authorize_message_party(principal, message, "mark_read")
        await state.message_storage.update_message_status(message_id, "read")
        return {
            "status": "success",
            "message_id": message_id,
            "message_status": "read",
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error marking message %s as read: %s", message_id, e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/load-balancer/stats")
@rate_limit(rate=200, per=60)
async def get_load_balancer_stats(request: Request, principal: OptionalAgent) -> dict[str, Any]:
    """Get load balancer statistics.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "load_balancer_stats")
    try:
        if not state.load_balancer:
            raise HTTPException(status_code=503, detail="Load balancer not available")
        stats = state.load_balancer.get_load_balancing_stats()
        return {"status": "success", "stats": stats, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting load balancer stats: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/registry/stats")
@rate_limit(rate=200, per=60)
async def get_registry_stats(request: Request, principal: OptionalAgent) -> dict[str, Any]:
    """Get agent registry statistics.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "registry_stats")
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        stats = await state.agent_registry.get_registry_stats()
        return {"status": "success", "stats": stats, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting registry stats: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/agents/service/{service}")
@rate_limit(rate=200, per=60)
async def get_agents_by_service(request: Request, service: str) -> dict[str, Any]:
    """Get agents that provide a specific service"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        agents = await state.agent_registry.get_agents_by_service(service)
        return {
            "status": "success",
            "service": service,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting agents by service: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/agents/capability/{capability}")
@rate_limit(rate=200, per=60)
async def get_agents_by_capability(request: Request, capability: str) -> dict[str, Any]:
    """Get agents that have a specific capability"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        agents = await state.agent_registry.get_agents_by_capability(capability)
        return {
            "status": "success",
            "capability": capability,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error getting agents by capability: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put("/load-balancer/strategy")
@rate_limit(rate=50, per=60)
async def set_load_balancing_strategy(
    request: Request, principal: OptionalAgent, strategy: str = Query(..., description="Load balancing strategy")
) -> dict[str, Any]:
    """Set load balancing strategy.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "load_balancer_strategy")
    try:
        if not state.load_balancer:
            raise HTTPException(status_code=503, detail="Load balancer not available")
        try:
            load_balancing_strategy = LoadBalancingStrategy(strategy.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid strategy: {strategy}") from None
        state.load_balancer.set_strategy(load_balancing_strategy)
        return {
            "status": "success",
            "message": f"Load balancing strategy set to {strategy}",
            "strategy": strategy,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error setting load balancing strategy: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/peers/add")
@rate_limit(rate=50, per=60)
async def add_peer(
    request: Request,
    principal: OptionalAgent,
    agent_id: str = Query(..., description="Agent ID"),
    peer_id: str = Query(..., description="Peer agent ID"),
) -> dict[str, Any]:
    """Add a peer connection for an agent.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "peers_add")
    try:
        if not state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")
        success = await state.peer_storage.add_peer(agent_id, peer_id, {"connected_at": datetime.now(UTC).isoformat()})
        if success:
            return {
                "status": "success",
                "message": f"Peer {peer_id} added for agent {agent_id}",
                "agent_id": agent_id,
                "peer_id": peer_id,
                "connected_at": datetime.now(UTC).isoformat(),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to add peer")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error adding peer: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/peers/remove")
@rate_limit(rate=50, per=60)
async def remove_peer(
    request: Request,
    principal: OptionalAgent,
    agent_id: str = Query(..., description="Agent ID"),
    peer_id: str = Query(..., description="Peer agent ID"),
) -> dict[str, Any]:
    """Remove a peer connection for an agent.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "peers_remove")
    try:
        if not state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")
        success = await state.peer_storage.remove_peer(agent_id, peer_id)
        if success:
            return {
                "status": "success",
                "message": f"Peer {peer_id} removed for agent {agent_id}",
                "agent_id": agent_id,
                "peer_id": peer_id,
                "removed_at": datetime.now(UTC).isoformat(),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to remove peer")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error removing peer: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/peers/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_agent_peers(request: Request, agent_id: str, principal: OptionalAgent) -> dict[str, Any]:
    """Get all peers for a specific agent.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "peers_get")
    try:
        if not state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")
        peers = await state.peer_storage.get_agent_peers(agent_id)
        return {
            "status": "success",
            "agent_id": agent_id,
            "peers": peers,
            "count": len(peers),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving peers for agent %s: %s", agent_id, e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/peers")
@rate_limit(rate=200, per=60)
async def get_all_peers(request: Request, principal: OptionalAgent) -> dict[str, Any]:
    """Get all peer connections in the system.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "peers_list")
    try:
        if not state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")
        connections = await state.peer_storage.get_all_peer_connections()
        total_peers = sum(len(peers) for peers in connections.values())
        return {
            "status": "success",
            "connections": connections,
            "total_agents": len(connections),
            "total_peers": total_peers,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving all peer connections: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_messages_for_agent_compatibility(request: Request, agent_id: str, principal: OptionalAgent) -> dict[str, Any]:
    """Get messages for agent - AgentDaemon compatibility route.

    Enforce mode: only the bound principal (or an admin) may read the agent's
    messages; advisory/disabled keep the open read."""
    return await get_messages_for_agent(request, agent_id, principal)


async def get_messages_for_agent(request: Request, agent_id: str, principal: AgentPrincipal | None = None) -> dict[str, Any]:
    authorize_agent_scope(principal, agent_id, "inbox_compat")
    try:
        if not state.message_storage:
            return {"agent_id": agent_id, "count": 0, "messages": [], "timestamp": datetime.now(UTC).isoformat()}
        messages = await state.message_storage.get_messages_by_receiver(agent_id, 100, 0)
        return {"agent_id": agent_id, "count": len(messages), "messages": messages, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting messages for agent %s: %s", agent_id, e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
