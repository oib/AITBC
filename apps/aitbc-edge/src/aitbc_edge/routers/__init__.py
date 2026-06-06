"""Routers for Edge API Service"""

from .database import router as database_router
from .gpu import router as gpu_router
from .islands import router as islands_router
from .metrics import router as metrics_router
from .serve import router as serve_router

__all__ = [
    "islands_router",
    "gpu_router",
    "database_router",
    "serve_router",
    "metrics_router",
]
