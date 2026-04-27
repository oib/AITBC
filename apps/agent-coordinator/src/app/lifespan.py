import asyncio
from contextlib import asynccontextmanager

from aitbc import get_logger
from fastapi import FastAPI

from . import state

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AITBC Agent Coordinator...")

    from .protocols.communication import CommunicationManager
    from .protocols.message_types import MessageProcessor
    from .routing.agent_discovery import AgentDiscoveryService, AgentRegistry
    from .routing.load_balancer import LoadBalancer, LoadBalancingStrategy, TaskDistributor

    state.agent_registry = AgentRegistry()
    await state.agent_registry.start()

    state.discovery_service = AgentDiscoveryService(state.agent_registry)
    state.load_balancer = LoadBalancer(state.agent_registry)
    state.load_balancer.set_strategy(LoadBalancingStrategy.LEAST_CONNECTIONS)
    state.task_distributor = TaskDistributor(state.load_balancer)
    state.communication_manager = CommunicationManager("agent-coordinator")
    state.message_processor = MessageProcessor("agent-coordinator")

    asyncio.create_task(state.task_distributor.start_distribution())
    asyncio.create_task(state.message_processor.start_processing())

    logger.info("Agent Coordinator started successfully")

    yield

    logger.info("Shutting down AITBC Agent Coordinator...")
    if state.agent_registry:
        await state.agent_registry.stop()
    logger.info("Agent Coordinator shut down")
