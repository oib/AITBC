"""Middleware configuration for Coordinator API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aitbc.aitbc_logging import get_logger
from aitbc.security_headers import SecurityHeaders, SecurityHeadersMiddleware, create_production_security_headers

logger = get_logger(__name__)


class SecurityHeadersASGIMiddleware:
    """Apply configured security headers to every HTTP response.

    Pure ASGI rather than ``BaseHTTPMiddleware`` + ``dispatch=``: the base
    class spawns an anyio task and copies contextvars on every request.
    """

    def __init__(self, app: ASGIApp, headers: SecurityHeaders | None = None) -> None:
        self.app = app
        self.headers = SecurityHeadersMiddleware(headers).get_headers()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.headers:
            await self.app(scope, receive, send)
            return
        encoded = {k.lower().encode(): v.encode() for k, v in self.headers.items()}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() not in encoded]
                headers.extend(encoded.items())
                message = dict(message, headers=headers)
            await send(message)

        await self.app(scope, receive, send_wrapper)


def setup_middleware(app: FastAPI) -> None:
    """Setup all middleware for the application"""
    from ..config import settings

    # Security headers middleware
    if settings.environment == "production":
        security_headers = create_production_security_headers()
    else:
        security_headers = None  # Use defaults for development

    app.add_middleware(SecurityHeadersASGIMiddleware, headers=security_headers)

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
        default_limits=[f"{settings.rate_limit_market_list}/minute"],
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    logger.info("Middleware configured successfully")
