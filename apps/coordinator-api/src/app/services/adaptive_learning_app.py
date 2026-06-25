"""
Adaptive Learning Service - FastAPI Entry Point
"""

from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import configure_logging, get_logger

configure_logging(level="INFO", service_name="adaptive-learning", to_file=True)
logger = get_logger(__name__)

from ..contexts.advanced_ai.routers.adaptive_learning_health import router as health_router
from ..contexts.analytics.services.ai_analytics.adaptive_learning import (
    AdaptiveLearningService,
    LearningAlgorithm,
)
from ..storage import get_session

app = FastAPI(
    title="AITBC Adaptive Learning Service",
    version="1.0.0",
    description="Reinforcement learning frameworks for agent self-improvement",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8001",
        "http://localhost:8203",
        "http://localhost:8016",
        "http://localhost:9001",
        "http://127.0.0.1:8001",
        "http://127.0.0.1:8203",
        "http://127.0.0.1:8016",
        "http://127.0.0.1:9001",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include health check router
app.include_router(health_router, tags=["health"])


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "adaptive-learning"}


@app.post("/create-environment")
async def create_learning_environment(
    environment_id: str,
    config: dict[str, Any],
    session: Annotated[Session, Depends(get_session)] = None,  # type: ignore[assignment]
) -> Any:
    """Create safe learning environment"""
    service = AdaptiveLearningService(session)
    result = await service.create_learning_environment(environment_id=environment_id, config=config)
    return result


@app.post("/create-agent")
async def create_learning_agent(
    agent_id: str,
    algorithm: str,
    config: dict[str, Any],
    session: Annotated[Session, Depends(get_session)] = None,  # type: ignore[assignment]
) -> Any:
    """Create reinforcement learning agent"""
    service = AdaptiveLearningService(session)
    result = await service.create_learning_agent(agent_id=agent_id, algorithm=LearningAlgorithm(algorithm), config=config)
    return result


@app.post("/train-agent")
async def train_agent(
    agent_id: str,
    environment_id: str,
    training_config: dict[str, Any],
    session: Annotated[Session, Depends(get_session)] = None,  # type: ignore[assignment]
) -> Any:
    """Train agent in environment"""
    service = AdaptiveLearningService(session)
    result = await service.train_agent(agent_id=agent_id, environment_id=environment_id, training_config=training_config)
    return result


@app.get("/agent-performance/{agent_id}")
async def get_agent_performance(agent_id: str, session: Annotated[Session, Depends(get_session)] = None) -> Any:  # type: ignore[assignment]
    """Get agent performance metrics"""
    service = AdaptiveLearningService(session)
    result = await service.get_agent_performance(agent_id=agent_id)
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8005)
