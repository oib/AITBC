from sqlalchemy.orm import Session
from typing import Annotated
"""
Modality Optimization Service - FastAPI Entry Point
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from .modality_optimization import ModalityOptimizationManager, OptimizationStrategy, ModalityType
from ..storage import Annotated[Session, Depends(get_session)], get_session
from ..routers.modality_optimization_health import router as health_router

app = FastAPI(
    title="AITBC Modality Optimization Service",
    version="1.0.0",
    description="Specialized optimization strategies for different data modalities"
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
    return {"status": "ok", "service": "modality-optimization"}

@app.post("/optimize")
async def optimize_modality(
    modality: str,
    data: dict,
    strategy: str = "balanced",
    session: Annotated[Session, Depends(get_session)] = Depends() = None
):
    """Optimize specific modality"""
    manager = ModalityOptimizationManager(session)
    result = await manager.optimize_modality(
        modality=ModalityType(modality),
        data=data,
        strategy=OptimizationStrategy(strategy)
    )
    return result

@app.post("/optimize-multimodal")
async def optimize_multimodal(
    multimodal_data: dict,
    strategy: str = "balanced",
    session: Annotated[Session, Depends(get_session)] = Depends() = None
):
    """Optimize multiple modalities"""
    manager = ModalityOptimizationManager(session)
    
    # Convert string keys to ModalityType enum
    optimized_data = {}
    for key, value in multimodal_data.items():
        try:
            optimized_data[ModalityType(key)] = value
        except ValueError:
            continue
    
    result = await manager.optimize_multimodal(
        multimodal_data=optimized_data,
        strategy=OptimizationStrategy(strategy)
    )
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
