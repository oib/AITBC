"""Middleware configuration for Coordinator API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from aitbc.aitbc_logging import get_logger
from aitbc.security_headers import SecurityHeadersMiddleware, create_production_security_headers

logger = get_logger(__name__)


def setup_middleware(app: FastAPI) -> None:
    """Setup all middleware for the application"""
    from ..config import settings

    # Security headers middleware
    if settings.environment == "production":
        security_headers = create_production_security_headers()
    else:
        security_headers = None  # Use defaults for development

    app.add_middleware(BaseHTTPMiddleware, dispatch=SecurityHeadersMiddleware(security_headers))

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
        default_limits=[f"{settings.rate_limit_marketplace_list}/minute"],
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    logger.info("Middleware configured successfully")
