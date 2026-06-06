import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from aitbc import get_logger

from . import state

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AITBC Agent Coordinator...")

    from .protocols.communication import CommunicationManager
    from .protocols.message_types import MessageProcessor
    from .routing.agent_discovery import AgentDiscoveryService, AgentRegistry
    from .routing.load_balancer import LoadBalancer, LoadBalancingStrategy, TaskDistributor
    from .storage.message_storage import MessageStorage, PeerStorage

    # Get Redis URL from environment variable
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")
    logger.info(f"Using Redis URL: {redis_url}")

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

    logger.info("Agent Coordinator started successfully")

    yield

    logger.info("Shutting down AITBC Agent Coordinator...")
    if state.agent_registry:
        await state.agent_registry.stop()
    if state.message_storage:
        await state.message_storage.stop()
    if state.peer_storage:
        await state.peer_storage.stop()
    logger.info("Agent Coordinator shut down")
