from typing import Annotated, Any

from sqlalchemy.orm import Session

"""
Modality Optimization Service - FastAPI Entry Point
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..contexts.multimodal.routers.modality_optimization_health import router as health_router
from ..contexts.multimodal.services.modality_optimization import (
    ModalityOptimizationManager,
    ModalityType,
    OptimizationStrategy,
)
from ..storage import get_session

app = FastAPI(
    title="AITBC Modality Optimization Service",
    version="1.0.0",
    description="Specialized optimization strategies for different data modalities",
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
    return {"status": "ok", "service": "modality-optimization"}


@app.post("/optimize")
async def optimize_modality(
    modality: str, data: dict[str, Any], strategy: str = "balanced", session: Annotated[Session | None, Depends(get_session)] = None
) -> dict[str, Any]:
    """Optimize specific modality"""
    assert session is not None, "DB session required"
    manager = ModalityOptimizationManager(session)
    result = await manager.optimize_modality(
        modality=ModalityType(modality), data=data, strategy=OptimizationStrategy(strategy)
    )
    return result


@app.post("/optimize-multimodal")
async def optimize_multimodal(
    multimodal_data: dict[str, Any], strategy: str = "balanced", session: Annotated[Session | None, Depends(get_session)] = None
) -> dict[str, Any]:
    """Optimize multiple modalities"""
    assert session is not None, "DB session required"
    manager = ModalityOptimizationManager(session)

    # Convert string keys to ModalityType enum
    optimized_data = {}
    for key, value in multimodal_data.items():
        try:
            optimized_data[ModalityType(key)] = value
        except ValueError:
            continue

    result = await manager.optimize_multimodal(multimodal_data=optimized_data, strategy=OptimizationStrategy(strategy))
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
