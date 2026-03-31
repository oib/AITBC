from typing import Annotated

from sqlalchemy.orm import Session

"""
GPU Multi-Modal Service - FastAPI Entry Point
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..routers.gpu_multimodal_health import router as health_router
from ..storage import get_session
from .gpu_multimodal import GPUAcceleratedMultiModal

app = FastAPI(
    title="AITBC GPU Multi-Modal Service",
    version="1.0.0",
    description="GPU-accelerated multi-modal processing with CUDA optimization",
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
    return {"status": "ok", "service": "gpu-multimodal", "cuda_available": True}


@app.post("/attention")
async def cross_modal_attention(
    modality_features: dict, attention_config: dict = None, session: Annotated[Session, Depends(get_session)] = None
):
    """GPU-accelerated cross-modal attention"""
    service = GPUAcceleratedMultiModal(session)
    result = await service.accelerated_cross_modal_attention(
        modality_features=modality_features, attention_config=attention_config
    )
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
