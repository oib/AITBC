"""
Middleware configuration for Coordinator API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler  # type: ignore[import-not-found]
from slowapi.errors import RateLimitExceeded  # type: ignore[import-not-found]
from slowapi.util import get_remote_address  # type: ignore[import-not-found]

from aitbc import get_logger

logger = get_logger(__name__)


def setup_middleware(app: FastAPI) -> None:
    """Setup all middleware for the application"""
    from ..config import settings

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[f"{settings.rate_limit_requests}/minute"],
        storage_uri=settings.redis_url,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    logger.info("Middleware configured successfully")
