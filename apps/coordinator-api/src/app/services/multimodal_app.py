from sqlalchemy.orm import Session
from typing import Annotated
"""
Multi-Modal Agent Service - FastAPI Entry Point
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from .multimodal_agent import MultiModalAgentService
from ..storage import Annotated[Session, Depends(get_session)], get_session
from ..routers.multimodal_health import router as health_router

app = FastAPI(
    title="AITBC Multi-Modal Agent Service",
    version="1.0.0",
    description="Multi-modal AI agent processing service with GPU acceleration"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"]
)

# Include health check router
app.include_router(health_router, tags=["health"])

@app.get("/health")
async def health():
    return {"status": "ok", "service": "multimodal-agent"}

@app.post("/process")
async def process_multimodal(
    agent_id: str,
    inputs: dict,
    processing_mode: str = "fusion",
    session: Annotated[Session, Depends(get_session)] = Depends() = None
):
    """Process multi-modal input"""
    service = MultiModalAgentService(session)
    result = await service.process_multimodal_input(
        agent_id=agent_id,
        inputs=inputs,
        processing_mode=processing_mode
    )
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
