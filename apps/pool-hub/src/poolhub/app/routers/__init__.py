"""FastAPI routers for Pool Hub."""

from .match import router as match_router
from .health import router as health_router
from .metrics import router as metrics_router

__all__ = ["match_router", "health_router", "metrics_router"]
