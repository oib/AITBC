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


def _escrow_sweep_once(mgr: Any) -> list[Any]:
    """One expire/refund pass, preceded by the #2744 lock reconcile.

    Runs in a worker thread (#1750): the reconcile probe and refund submitters
    are synchronous httpx and must stay off the event loop.
    """
    from .services.chain_escrow import (
        reconcile_rejected_lock,
        reconcile_rejected_refund,
        reconcile_rejected_release,
    )

    if state.escrow_rpc is not None:
        for esc in mgr.get_all_escrows():
            # #2926: settle txs admitted to the mempool can still be
            # apply-rejected — a falsely-RELEASED/REFUNDED row strands the
            # escrowed funds outside every worklist. Settle reconciles run
            # first: a reverted row lands back on LOCKED, where the lock
            # reconcile below can resolve a dead lock in the same pass.
            for reconcile, reason_key in (
                (reconcile_rejected_release, "release_rejected_reason"),
                (reconcile_rejected_refund, "refund_rejected_reason"),
            ):
                if reconcile(state.escrow_rpc, esc):
                    mgr.persist_entry(esc)
                    logger.warning(
                        "Escrow %s %s rejected on-chain for task %s: %s",
                        esc.escrow_id,
                        reason_key.removesuffix("_rejected_reason"),
                        esc.task_id,
                        esc.metadata.get(reason_key),
                    )
            if reconcile_rejected_lock(state.escrow_rpc, esc):
                mgr.persist_entry(esc)
                logger.warning(
                    "Escrow %s lock rejected on-chain for task %s: %s",
                    esc.escrow_id,
                    esc.task_id,
                    esc.metadata.get("lock_rejected_reason"),
                )
    expired: list[Any] = mgr.expire_stale(refund_submitter_for=_escrow_refund_submitter)
    return expired


async def sweep_stale_escrows() -> None:
    """Background task: expire/refund escrows past their timeout (v0.25).

    Sleeps ``settings.task_payment_sweep_seconds`` between passes; 0 disables.
    """
    from .config import settings as _settings

    while True:
        try:
            if state.payment_escrow:
                expired = await asyncio.to_thread(_escrow_sweep_once, state.payment_escrow)
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


def _orphan_sweep_once() -> dict[str, int]:
    """One orphaned-escrow reconcile pass (#2998), run in a worker thread.

    The chain point-reads and refund submits are synchronous httpx — same
    off-loop rule as ``_escrow_sweep_once`` (#1750).
    """
    from .config import settings as _settings
    from .services.orphan_escrow_sweeper import OrphanedTaskEscrowSweeper

    sweeper = OrphanedTaskEscrowSweeper(
        payment_escrow=state.payment_escrow,
        escrow_rpc=state.escrow_rpc,
        load_balancer=state.load_balancer,
        grace_seconds=_settings.task_payment_orphan_grace_seconds,
        batch_size=_settings.task_payment_orphan_sweep_batch_size,
        dry_run=_settings.task_payment_orphan_sweep_dry_run,
    )
    return sweeper.run_once()


async def sweep_orphaned_task_escrows() -> None:
    """Background task: reconcile escrows whose chain lock outlived the local row (#2998).

    Sleeps ``settings.task_payment_orphan_sweep_seconds`` between passes;
    0 disables. Registered only when task-payment escrow is enabled.
    """
    from .config import settings as _settings

    while True:
        try:
            counts = await asyncio.to_thread(_orphan_sweep_once)
            if counts["candidates"]:
                logger.info(
                    "Orphaned escrow sweep: candidates=%s adopted=%s refunded=%s failed=%s deferred=%s skipped=%s",
                    counts["candidates"],
                    counts["adopted"],
                    counts["refunded"],
                    counts["failed"],
                    counts["deferred"],
                    counts["skipped"],
                )
        except _OPS_ERRORS as e:
            logger.error("Error sweeping orphaned escrows: %s", e)
        await asyncio.sleep(max(_settings.task_payment_orphan_sweep_seconds, 5.0))


def _terminal_sweep_once() -> dict[str, int]:
    """One terminal-settle reconcile pass (#3026), run in a worker thread.

    The chain probes are synchronous httpx — same off-loop rule as
    ``_escrow_sweep_once`` (#1750).
    """
    from .config import settings as _settings
    from .services.terminal_settle_sweeper import TerminalSettleSweeper

    sweeper = TerminalSettleSweeper(
        payment_escrow=state.payment_escrow,
        escrow_rpc=state.escrow_rpc,
        grace_seconds=_settings.task_payment_terminal_grace_seconds,
        batch_size=_settings.task_payment_terminal_sweep_batch_size,
        dry_run=_settings.task_payment_terminal_sweep_dry_run,
    )
    return sweeper.run_once()


async def sweep_terminal_settles() -> None:
    """Background task: demote terminal escrows whose settle tx never sealed (#3026).

    Sleeps ``settings.task_payment_terminal_sweep_seconds`` between passes;
    0 disables. Registered only when task-payment escrow is enabled.
    """
    from .config import settings as _settings

    while True:
        try:
            counts = await asyncio.to_thread(_terminal_sweep_once)
            if counts["candidates"]:
                logger.info(
                    "Terminal settle sweep: candidates=%s confirmed=%s demoted=%s failed=%s skipped=%s",
                    counts["candidates"],
                    counts["confirmed"],
                    counts["demoted"],
                    counts["failed"],
                    counts["skipped"],
                )
        except _OPS_ERRORS as e:
            logger.error("Error sweeping terminal escrows: %s", e)
        await asyncio.sleep(max(_settings.task_payment_terminal_sweep_seconds, 5.0))


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


async def _start_workflow_orchestrator(redis_url: str) -> None:
    """#2014: construct the shared orchestrator singleton with the service
    Redis URL and start() it so workflow definitions/executions persist.
    Extracted so the lifespan wiring itself is pinned by test."""
    from .workflow import get_orchestrator

    state.workflow_orchestrator = get_orchestrator(redis_url=redis_url)
    await state.workflow_orchestrator.start()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting AITBC Agent Coordinator...")
    from .protocols.communication import CommunicationManager
    from .protocols.message_types import MessageProcessor
    from .routing.agent_discovery import AgentDiscoveryService, AgentRegistry
    from .routing.load_balancer import LoadBalancer, LoadBalancingStrategy, TaskDistributor
    from .storage.assignment_store import TaskAssignmentStore
    from .storage.message_storage import MessageStorage, PeerStorage

    from .config import settings

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")
    database_url = settings.database_url
    logger.info("Using Redis URL: %s", _sanitize_url(redis_url))
    state.agent_registry = AgentRegistry(redis_url=redis_url)
    await state.agent_registry.start()
    state.discovery_service = AgentDiscoveryService(state.agent_registry)
    # #2163: assignments persist to the shared agent DB (same write-through
    # convention as the escrow store) so a restart cannot strand escrowed
    # tasks whose task -> agent mapping lived only in memory.
    state.load_balancer = LoadBalancer(state.agent_registry, assignment_store=TaskAssignmentStore())
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

    # #2014: start the workflow orchestrator. The routers resolve the same
    # get_orchestrator() singleton; without start() its redis client stayed
    # None, so create_workflow returned 200 but persisted nothing — list
    # read empty and execute 404'd (S10 paid-leg blocker).
    await _start_workflow_orchestrator(redis_url)

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
        # #2998: reconcile escrows whose chain lock outlived a PENDING/REJECTED
        # local row — the expire sweep only sees LOCKED entries.
        if settings.task_payment_orphan_sweep_enabled and settings.task_payment_orphan_sweep_seconds > 0:
            _task_registry.create_task(sweep_orphaned_task_escrows, name="orphaned_escrow_sweeper")
        # #3026: RELEASED/REFUNDED rows are recorded at mempool admission — a
        # settle tx evicted before sealing must be demoted back to LOCKED or
        # the escrowed funds strand outside every worklist.
        if settings.task_payment_terminal_sweep_enabled and settings.task_payment_terminal_sweep_seconds > 0:
            _task_registry.create_task(sweep_terminal_settles, name="terminal_settle_sweeper")
    else:
        logger.info("Payment escrow disabled (task_payment_escrow_enabled=False)")

    # #3027: escrow init runs after the distributor is built — wire it now so
    # each created assignment tombstones the task's escrow rows. The orphan
    # sweeper's distributed-check must survive the balancer evicting the
    # assignment record; without this the tombstone only lands on the
    # sweeper's first observation, leaving an eviction-before-probe gap.
    if state.task_distributor is not None:
        state.task_distributor.payment_escrow = state.payment_escrow

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
    if state.workflow_orchestrator:
        await state.workflow_orchestrator.stop()
        state.workflow_orchestrator = None
    logger.info("Agent Coordinator shut down")
