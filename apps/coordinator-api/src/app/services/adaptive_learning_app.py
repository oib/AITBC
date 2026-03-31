from typing import Annotated

from sqlalchemy.orm import Session

"""
Adaptive Learning Service - FastAPI Entry Point
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..routers.adaptive_learning_health import router as health_router
from ..storage import get_session
from .adaptive_learning import AdaptiveLearningService, LearningAlgorithm

app = FastAPI(
    title="AITBC Adaptive Learning Service",
    version="1.0.0",
    description="Reinforcement learning frameworks for agent self-improvement",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include health check router
app.include_router(health_router, tags=["health"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "adaptive-learning"}


@app.post("/create-environment")
async def create_learning_environment(
    environment_id: str, config: dict, session: Annotated[Session, Depends(get_session)] = None
):
    """Create safe learning environment"""
    service = AdaptiveLearningService(session)
    result = await service.create_learning_environment(environment_id=environment_id, config=config)
    return result


@app.post("/create-agent")
async def create_learning_agent(
    agent_id: str, algorithm: str, config: dict, session: Annotated[Session, Depends(get_session)] = None
):
    """Create reinforcement learning agent"""
    service = AdaptiveLearningService(session)
    result = await service.create_learning_agent(agent_id=agent_id, algorithm=LearningAlgorithm(algorithm), config=config)
    return result


@app.post("/train-agent")
async def train_agent(
    agent_id: str, environment_id: str, training_config: dict, session: Annotated[Session, Depends(get_session)] = None
):
    """Train agent in environment"""
    service = AdaptiveLearningService(session)
    result = await service.train_agent(agent_id=agent_id, environment_id=environment_id, training_config=training_config)
    return result


@app.get("/agent-performance/{agent_id}")
async def get_agent_performance(agent_id: str, session: Annotated[Session, Depends(get_session)] = None):
    """Get agent performance metrics"""
    service = AdaptiveLearningService(session)
    result = await service.get_agent_performance(agent_id=agent_id)
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
