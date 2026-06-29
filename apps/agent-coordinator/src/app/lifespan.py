import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import TaskRegistry
from aitbc.db import get_db_session, init_db
from aitbc.models import CoinRequest, CoinRequestStatus

from . import state

logger = get_logger(__name__)

_task_registry = TaskRegistry()


async def expire_old_requests() -> None:
    """Background task to expire coin requests older than 30 days.

    Moved from hermes_service.main.expire_old_requests in v0.5.9 §3.
    """
    while True:
        try:
            with get_db_session() as session:
                cutoff = datetime.now(UTC) - timedelta(days=30)
                expired_requests = (
                    session.query(CoinRequest)
                    .filter(CoinRequest.status == CoinRequestStatus.PENDING, CoinRequest.expires_at < cutoff)
                    .all()
                )
                for req in expired_requests:
                    req.status = CoinRequestStatus.EXPIRED
                    req.audit_log += f" | Auto-expired at {datetime.now(UTC).isoformat()}"
                    logger.info("Expired request %s from %s", req.id, req.sender)
                if expired_requests:
                    logger.info("Expired %s old coin requests", len(expired_requests))
        except Exception as e:
            logger.error("Error expiring old requests: %s", e)
        await asyncio.sleep(3600)


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
    logger.info("Using Redis URL: %s", redis_url)
    state.agent_registry = AgentRegistry(redis_url=redis_url)
    await state.agent_registry.start()
    state.discovery_service = AgentDiscoveryService(state.agent_registry)
    state.load_balancer = LoadBalancer(state.agent_registry)
    state.load_balancer.set_strategy(LoadBalancingStrategy.LEAST_CONNECTIONS)
    state.task_distributor = TaskDistributor(state.load_balancer)
    state.communication_manager = CommunicationManager("agent-coordinator")
    state.message_processor = MessageProcessor("agent-coordinator")
    state.message_storage = MessageStorage(redis_url=redis_url)
    state.peer_storage = PeerStorage(redis_url=redis_url)
    await state.message_storage.start()
    await state.peer_storage.start()
    asyncio.create_task(state.task_distributor.start_distribution())
    asyncio.create_task(state.message_processor.start_processing())

    # v0.6.5: Initialize payment escrow (feature-flagged via settings)
    if settings.task_payment_escrow_enabled:
        from aitbc.crypto import PaymentEscrow

        state.payment_escrow = PaymentEscrow(
            default_timeout=settings.task_payment_timeout_seconds,
        )
        logger.info("Payment escrow enabled (timeout=%ss)", settings.task_payment_timeout_seconds)
    else:
        logger.info("Payment escrow disabled (task_payment_escrow_enabled=False)")

    # Initialize coin requests DB and start background expiration task (v0.5.9 §3)
    init_db()
    _task_registry.create_task(expire_old_requests, name="expire_old_requests")
    logger.info("Coin requests DB initialized, expiration task started")

    logger.info("Agent Coordinator started successfully")
    yield
    logger.info("Shutting down AITBC Agent Coordinator...")
    await _task_registry.cancel_all(timeout=5.0)
    if state.agent_registry:
        await state.agent_registry.stop()
    if state.message_storage:
        await state.message_storage.stop()
    if state.peer_storage:
        await state.peer_storage.stop()
    logger.info("Agent Coordinator shut down")
