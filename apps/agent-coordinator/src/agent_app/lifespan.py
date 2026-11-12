import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import TaskRegistry
from aitbc.db import get_db_session, init_db
from aitbc.models import CoinRequest, CoinRequestStatus

from . import state

logger = get_logger(__name__)

# Expected failure surface for the best-effort handlers below: filesystem/OS
# and transport errors, JSON/data-shape decode, lazy imports, and the
# backends noted per file. Genuine BaseExceptions (incl.
# asyncio.CancelledError) still propagate (#1865).
_OPS_ERRORS: tuple[type[Exception], ...] = (
    OSError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    IndexError,
    ImportError,
    RuntimeError,
)
try:
    import httpx

    _OPS_ERRORS = _OPS_ERRORS + (httpx.HTTPError,)
except ImportError:
    pass
try:
    from redis.exceptions import RedisError as _RedisError

    _OPS_ERRORS += (_RedisError,)
except ImportError:
    pass
try:
    from sqlalchemy.exc import SQLAlchemyError

    _OPS_ERRORS += (SQLAlchemyError,)
except ImportError:
    pass

_task_registry = TaskRegistry()


def _sanitize_url(url: str) -> str:
    """Remove credentials from a URL before logging (same convention as aitbc_chain)."""
    from urllib.parse import urlparse, urlunparse

    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            netloc = f"{parsed.hostname or ''}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except _OPS_ERRORS:
        pass
    return url


def sweep_expired_coin_requests(session) -> int:
    """Expire every unexecuted request whose ``expires_at`` has passed.

    ``expires_at`` is REQUEST_TTL (24h) and bounds how long a request stays
    executable — pending rows wait for an operator, approved rows for
    ``/execute``. Rows that already carry a ``transaction_hash`` (paid or
    mid-claim) are left alone: expiry must never rewrite the record of a
    payment that happened or is reconciling (#1579). Returns the count.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    expired_requests = (
        session.query(CoinRequest)
        .filter(
            CoinRequest.status.in_([CoinRequestStatus.PENDING, CoinRequestStatus.APPROVED]),
            CoinRequest.expires_at < now,
            CoinRequest.transaction_hash.is_(None),
        )
        .all()
    )
    for req in expired_requests:
        req.status = CoinRequestStatus.EXPIRED
        existing_log = req.audit_log or ""
        req.audit_log = f"{existing_log} | Auto-expired at {now.isoformat()}"
        logger.info("Expired request %s from %s", req.id, req.sender)
    return len(expired_requests)


async def expire_old_requests() -> None:
    """Background task to expire coin requests past their ``expires_at``.

    Moved from hermes_service.main.expire_old_requests in v0.5.9 §3; the
    cutoff is the per-request TTL, not a flat 30 days (#1579).
    """
    while True:
        try:
            with get_db_session() as session:
                expired = sweep_expired_coin_requests(session)
                if expired:
                    logger.info("Expired %s coin requests past their TTL", expired)
        except _OPS_ERRORS as e:
            logger.error("Error expiring old requests: %s", e)
        await asyncio.sleep(3600)


def _escrow_refund_submitter(entry: Any) -> Any:
    """Return a chain refund submitter for escrows that locked on-chain.

    Bookkeeping-only escrows (no ``tx_hash_lock``) get no submitter so their
    refund stays off-chain.
    """
    if state.escrow_rpc is None or not entry.tx_hash_lock:
        return None
    from .services.chain_escrow import make_refund_submitter

    return make_refund_submitter(state.escrow_rpc, entry.task_id, reason="expired")


async def sweep_stale_escrows() -> None:
    """Background task: expire/refund escrows past their timeout (v0.25).

    Sleeps ``settings.task_payment_sweep_seconds`` between passes; 0 disables.
    """
    from .config import settings as _settings

    while True:
        try:
            if state.payment_escrow:
                # #1750: refund submitters are synchronous httpx (up to 15s
                # per escrow) — keep them off the event loop.
                expired = await asyncio.to_thread(
                    state.payment_escrow.expire_stale, refund_submitter_for=_escrow_refund_submitter
                )
                if expired:
                    logger.info("Expired %d stale escrow(s): %s", len(expired), [e.escrow_id for e in expired])
                    # #1749: an expired escrow means the task never completed —
                    # fail its load-balancer assignment too.
                    if state.load_balancer is not None:
                        for entry in expired:
                            state.load_balancer.fail_task(entry.task_id, error_message="escrow_expired")
        except _OPS_ERRORS as e:
            logger.error("Error sweeping stale escrows: %s", e)
        await asyncio.sleep(max(_settings.task_payment_sweep_seconds, 5.0))


async def sweep_stale_assignments() -> None:
    """Background task: fail load-balancer assignments that never reported (#1749).

    Without a reaper, ``pending_tasks`` stayed elevated forever once an agent
    stopped reporting — eventually every ``POST /tasks/submit`` failed with
    'no suitable agent found'.
    """
    while True:
        try:
            if state.load_balancer is not None:
                expired = state.load_balancer.expire_stale_assignments()
                if expired:
                    logger.info("Timed out %d stale task assignment(s): %s", len(expired), expired)
        except _OPS_ERRORS as e:
            logger.error("Error sweeping stale task assignments: %s", e)
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting AITBC Agent Coordinator...")
    from .protocols.communication import CommunicationManager
    from .protocols.message_types import MessageProcessor
    from .routing.agent_discovery import AgentDiscoveryService, AgentRegistry
    from .routing.load_balancer import LoadBalancer, LoadBalancingStrategy, TaskDistributor
    from .storage.message_storage import MessageStorage, PeerStorage

    from .config import settings

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")
    database_url = settings.database_url
    logger.info("Using Redis URL: %s", _sanitize_url(redis_url))
    state.agent_registry = AgentRegistry(redis_url=redis_url)
    await state.agent_registry.start()
    state.discovery_service = AgentDiscoveryService(state.agent_registry)
    state.load_balancer = LoadBalancer(state.agent_registry)
    state.load_balancer.set_strategy(LoadBalancingStrategy.LEAST_CONNECTIONS)
    state.task_distributor = TaskDistributor(state.load_balancer)
    state.communication_manager = CommunicationManager("agent-coordinator")
    from .protocols.communication import create_protocol

    state.communication_manager.add_protocol("broadcast", create_protocol("broadcast", "agent-coordinator"))
    state.message_processor = MessageProcessor("agent-coordinator")
    state.message_storage = MessageStorage(redis_url=redis_url, database_url=database_url)
    state.peer_storage = PeerStorage(redis_url=redis_url)
    await state.message_storage.start()
    await state.peer_storage.start()

    # Wire the WebSocket connection manager to the persisted message storage
    # so it can restore topic subscriptions on agent reconnect.
    from .websocket import get_connection_manager

    connection_manager = get_connection_manager()
    connection_manager.message_storage = state.message_storage

    _task_registry.create_task(state.task_distributor.start_distribution, name="task_distribution")
    _task_registry.create_task(state.message_processor.start_processing, name="message_processing")

    # v0.6.5: Initialize payment escrow (feature-flagged via settings)
    if settings.task_payment_escrow_enabled:
        from aitbc.crypto import PaymentEscrow

        from .services.chain_escrow import ChainEscrowClient
        from .storage.escrow_store import TaskEscrowStore

        # Durable bookkeeping: escrows persist to the shared agent DB so a
        # restart reloads LOCKED entries instead of stranding on-chain funds.
        state.payment_escrow = PaymentEscrow(
            default_timeout=settings.task_payment_timeout_seconds,
            store=TaskEscrowStore(),
        )
        # v0.25: on-chain escrow via the same /rpc/escrow/* routes the
        # market uses. The callbacks are built per call in the tasks
        # router (the four-arg EscrowCallback signature can't carry the
        # task_id/lock_tx context the chain endpoints need).
        state.escrow_rpc = ChainEscrowClient(
            settings.blockchain_rpc_url,
            api_key=settings.blockchain_rpc_api_key or None,
            settlement_api_key=settings.blockchain_rpc_settlement_api_key or None,
        )
        logger.info(
            "Payment escrow enabled (timeout=%ss, chain_rpc=%s)",
            settings.task_payment_timeout_seconds,
            _sanitize_url(settings.blockchain_rpc_url),
        )
        if settings.task_payment_sweep_seconds > 0:
            _task_registry.create_task(sweep_stale_escrows, name="escrow_expiry_sweeper")
    else:
        logger.info("Payment escrow disabled (task_payment_escrow_enabled=False)")

    # #1749: assignment reaper runs regardless of escrow config — unpaid
    # tasks have no escrow sweeper to fail them.
    _task_registry.create_task(sweep_stale_assignments, name="stale_assignment_sweeper")

    # Initialize coin requests DB and start background expiration task (v0.5.9 §3)
    init_db()
    _task_registry.create_task(expire_old_requests, name="expire_old_requests")
    logger.info("Coin requests DB initialized, expiration task started")

    logger.info("Agent Coordinator started successfully")
    yield
    logger.info("Shutting down AITBC Agent Coordinator...")
    await _task_registry.cancel_all(timeout=5.0)
    # create_task_with_logging spawns (heartbeat monitor, cleanup loops,
    # per-alert notifications, workflow runners) register with the shared
    # global registry — cancel them too so they cannot outlive shutdown
    # or keep writing to closed stores (#1602).
    from aitbc.async_tasks import get_global_registry

    await get_global_registry().cancel_all(timeout=5.0)
    if state.agent_registry:
        await state.agent_registry.stop()
    if state.message_storage:
        await state.message_storage.stop()
    if state.peer_storage:
        await state.peer_storage.stop()
    if state.escrow_rpc:
        state.escrow_rpc.close()  # noqa: unawaited-async — ChainEscrowClient.close() is synchronous
        state.escrow_rpc = None
    logger.info("Agent Coordinator shut down")
