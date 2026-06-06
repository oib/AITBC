from typing import Annotated, Any

from sqlalchemy.orm import Session

"""
Multi-Modal Agent Service - FastAPI Entry Point
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..contexts.multimodal.routers.multimodal_health import router as health_router
from ..contexts.multimodal.services.multimodal_agent import MultiModalAgentService
from ..storage import get_session

app = FastAPI(
    title="AITBC Multi-Modal Agent Service",
    version="1.0.0",
    description="Multi-modal AI agent processing service with GPU acceleration",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8001",
        "http://localhost:8011",
        "http://localhost:8016",
        "http://localhost:9001",
        "http://127.0.0.1:8001",
        "http://127.0.0.1:8011",
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
    return {"status": "ok", "service": "multimodal-agent"}


@app.post("/process")
async def process_multimodal(
    agent_id: str, inputs: dict[str, Any], processing_mode: str = "fusion", session: Annotated[Session | None, Depends(get_session)] = None
) -> dict[str, Any]:
    """Process multi-modal input"""
    assert session is not None, "DB session required"
    from ..contexts.multimodal.services.multimodal_agent import ProcessingMode
    service = MultiModalAgentService(session)
    result = await service.process_multimodal_input(agent_id=agent_id, inputs=inputs, processing_mode=ProcessingMode(processing_mode))
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
