"""
Middleware configuration for Coordinator API.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# RateLimitExceeded is now defined in slowapi directly, not in slowapi.errors
try:
    from slowapi.errors import RateLimitExceeded
except ImportError:
    from slowapi import RateLimitExceeded


def setup_middleware(app: FastAPI):
    """Setup all middleware for the application"""
    from ..config import settings

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    # Rate limiting
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[settings.rate_limit_default],
        storage_uri=settings.redis_url,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    logger.info("Middleware configured successfully")
