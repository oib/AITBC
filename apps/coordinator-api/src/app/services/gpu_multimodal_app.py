from typing import Annotated, Any

from sqlalchemy.orm import Session

"""
GPU Multi-Modal Service - FastAPI Entry Point
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..contexts.gpu_multimodal.routers.gpu_multimodal_health import router as health_router
from ..storage import get_session
from .gpu_multimodal import GPUAcceleratedMultiModal

app = FastAPI(
    title="AITBC GPU Multi-Modal Service",
    version="1.0.0",
    description="GPU-accelerated multi-modal processing with CUDA optimization",
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
    return {"status": "ok", "service": "gpu-multimodal", "cuda_available": True}


@app.post("/attention")
async def cross_modal_attention(
    modality_features: dict[str, Any],
    attention_config: dict[str, Any] | None = None,
    session: Annotated[Session | None, Depends(get_session)] = None,
) -> dict[str, Any]:
    """GPU-accelerated cross-modal attention"""
    assert session is not None, "DB session required"
    service = GPUAcceleratedMultiModal(session)
    result = await service.accelerated_cross_modal_attention(
        modality_features=modality_features, attention_config=attention_config
    )
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
