"""
Auth middleware for AITBC services.

Consolidates:
- ``apps/coordinator-api/src/app/auth/middleware.py::AuthMiddleware``
- ``apps/agent-coordinator/src/app/auth/middleware.py`` (RateLimiter, get_current_user, etc.)

Provides:
- ``AuthMiddleware`` — route-based auth enforcement via security matrix
- ``RateLimiter`` — Redis-backed rate limiting with in-memory fallback
- ``get_current_user`` — FastAPI dependency for JWT/API-key auth
- ``SecurityHeaders`` — security response headers
- ``InputValidator`` — input sanitization utilities
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from functools import wraps
from typing import Annotated, Any, TypeVar, cast

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.types import ASGIApp, Receive, Scope, Send

from aitbc.aitbc_logging import get_logger

from .jwt import get_jwt_handler
from .security_matrix import AuthLevel, check_role_match, get_auth_level

logger = get_logger(__name__)
F = TypeVar("F", bound=Callable[..., Any])


class HTTPBearerOrApiKey(HTTPBearer):
    """``HTTPBearer`` that also parses the ``ApiKey`` authorization scheme.

    ``HTTPBearer`` only accepts the ``Bearer`` scheme, which made the
    ``credentials.scheme == "ApiKey"`` branch in ``get_current_user``
    unreachable — scoped API keys could never authenticate (#1754). Both
    schemes are matched case-insensitively; anything else yields ``None``
    (``auto_error=False``) or 403, mirroring ``HTTPBearer``. Subclassing keeps
    the OpenAPI ``HTTPBearer`` security scheme intact.
    """

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials | None:
        authorization = request.headers.get("Authorization")
        if authorization:
            scheme, _, param = authorization.strip().partition(" ")
            if scheme.lower() in ("bearer", "apikey") and param.strip():
                return HTTPAuthorizationCredentials(scheme=scheme, credentials=param.strip())
        if self.auto_error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authenticated")
        return None


# Keep the published scheme name ``HTTPBearer`` so the OpenAPI spec and any
# generated clients are unchanged — the ApiKey scheme is an additional
# accepted credential, not a new documented one.
security = HTTPBearerOrApiKey(auto_error=False, scheme_name="HTTPBearer")


class AuthenticationError(Exception):
    """Custom authentication error."""

    pass


# ---------------------------------------------------------------------------
# AuthMiddleware (coordinator-api compatible)
# ---------------------------------------------------------------------------


class AuthMiddleware:
    """Middleware to enforce auth requirements based on route security matrix.

    This middleware automatically:
    1. Extracts a Bearer token from the Authorization header, or a miner API key
       from the X-Api-Key header
    2. Verifies token/API-key validity
    3. Checks role requirements from security matrix
    4. Adds user info to request state

    Pure ASGI rather than ``BaseHTTPMiddleware``: the base class spawns an
    anyio task and copies contextvars on every request.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def _respond(self, response: Response, scope: Scope, receive: Receive, send: Send) -> None:
        await response(scope, receive, send)

    def _json_auth_response(
        self,
        status_code: int,
        detail: str,
        *,
        www_authenticate: str | None = None,
    ) -> Response:
        headers = {"WWW-Authenticate": www_authenticate} if www_authenticate else None
        return Response(
            status_code=status_code,
            content=f'{{"detail": "{detail}"}}',
            media_type="application/json",
            headers=headers,
        )

    def _attach_user_to_scope(self, scope: Scope, user: dict[str, Any], user_id: Any, user_role: Any) -> None:
        state = scope.setdefault("state", {})
        state["user"] = user
        state["user_id"] = user_id
        state["user_role"] = user_role

    async def _deny_auth(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        status_code: int,
        detail: str,
        *,
        www_authenticate: str | None = None,
    ) -> None:
        await self._respond(
            self._json_auth_response(status_code, detail, www_authenticate=www_authenticate), scope, receive, send
        )

    async def _try_bearer_auth(
        self,
        request: Request,
        scope: Scope,
        receive: Receive,
        send: Send,
        auth_level: AuthLevel,
    ) -> bool:
        """Authenticate via Bearer JWT. Returns True when the request was fully handled."""
        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            return False
        token = authorization[7:]
        try:
            from .jwt import verify_access_token

            payload = verify_access_token(token)
            user_role = payload.get("role")
            if not check_role_match(auth_level, user_role):
                await self._deny_auth(scope, receive, send, status.HTTP_403_FORBIDDEN, "Forbidden")
                return True
            self._attach_user_to_scope(scope, payload, payload.get("sub") or payload.get("user_id"), user_role)
            await self.app(scope, receive, send)
            return True
        except HTTPException as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                await self._deny_auth(scope, receive, send, status.HTTP_403_FORBIDDEN, "Forbidden")
            else:
                await self._deny_auth(
                    scope, receive, send, status.HTTP_401_UNAUTHORIZED, "Invalid token", www_authenticate="Bearer"
                )
            return True
        except (ValueError, TypeError) as e:
            logger.error("AuthMiddleware error: %s", e)
            await self._deny_auth(
                scope, receive, send, status.HTTP_401_UNAUTHORIZED, "Invalid token", www_authenticate="Bearer"
            )
            return True

    async def _try_miner_api_key_auth(
        self,
        request: Request,
        scope: Scope,
        receive: Receive,
        send: Send,
        auth_level: AuthLevel,
    ) -> bool:
        """Authenticate via X-Api-Key miner credential. Returns True when fully handled."""
        if not request.headers.get("X-Api-Key"):
            return False
        try:
            from .dependencies import require_miner_api_key

            user = require_miner_api_key(request)
            user_role = user.get("role")
            if not check_role_match(auth_level, user_role):
                await self._deny_auth(scope, receive, send, status.HTTP_403_FORBIDDEN, "Forbidden")
                return True
            self._attach_user_to_scope(scope, user, user.get("sub"), user_role)
            await self.app(scope, receive, send)
            return True
        except HTTPException as exc:
            logger.warning("X-Api-Key rejected on %s: %s", request.url.path, exc.detail)
            await self._deny_auth(scope, receive, send, status.HTTP_401_UNAUTHORIZED, "Invalid API key")
            return True
        except (ValueError, TypeError) as e:
            logger.error("AuthMiddleware API key error: %s", e)
            await self._deny_auth(scope, receive, send, status.HTTP_401_UNAUTHORIZED, "Invalid API key")
            return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path

        # Skip auth for public routes
        auth_level = get_auth_level(path, request.method)
        if auth_level == AuthLevel.NONE:
            await self.app(scope, receive, send)
            return

        # Credential boundary (#2140): this middleware intentionally recognizes
        # only ``Authorization: Bearer <jwt>`` and ``X-Api-Key`` miner keys.
        # ``Authorization: ApiKey <key>`` is an agent-coordinator scoped-key
        # credential consumed by router-level ``get_current_user`` /
        # ``agent_auth`` on services that do NOT mount AuthMiddleware
        # (coordinator-api has no ``get_current_user`` consumer). Accepting it
        # here would validate against APIKeyManager's node-shared store and
        # yield role="api", which the security matrix cannot express — a
        # privilege-surface widening the matrix never intended. Deliberate 401.
        if await self._try_bearer_auth(request, scope, receive, send, auth_level):
            return
        if await self._try_miner_api_key_auth(request, scope, receive, send, auth_level):
            return

        await self._deny_auth(
            scope,
            receive,
            send,
            status.HTTP_401_UNAUTHORIZED,
            "Authentication required",
            www_authenticate="Bearer",
        )


# ---------------------------------------------------------------------------
# RateLimiter (agent-coordinator compatible)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Distributed rate limiter using Redis with in-memory fallback."""

    def __init__(self, redis_url: str | None = None):
        from collections import deque

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        # Guards concurrent mutation of the in-memory rate-limiting cache.
        self._lock = asyncio.Lock()
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        # The import lives inside the try alongside the connection attempt: this module is
        # instantiated at import time (see `rate_limiter` below), so neither a missing redis
        # package nor an unreachable server may escape. Broad `except` is deliberate --
        # redis.exceptions.ConnectionError does not subclass the builtin ConnectionError.
        try:
            import redis

            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.warning("Redis unavailable, falling back to in-memory rate limiting: %s", e)
            self.redis_client = None

    async def is_allowed(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request."""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return await self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(key, window_seconds)
                return {
                    "allowed": True,
                    "remaining": max_requests - current_count - 1,
                    "reset_time": current_time + window_seconds,
                }
            else:
                oldest = self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return await self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    async def _is_allowed_memory(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting."""
        from collections import deque

        async with self._lock:
            if user_id not in self.memory_requests:
                self.memory_requests[user_id] = deque()
            user_requests = self.memory_requests[user_id]
            while user_requests and user_requests[0] < current_time - window_seconds:
                user_requests.popleft()
            if len(user_requests) < max_requests:
                user_requests.append(current_time)
                return {
                    "allowed": True,
                    "remaining": max_requests - len(user_requests),
                    "reset_time": current_time + window_seconds,
                }
            else:
                oldest_request = user_requests[0]
                reset_time = oldest_request + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}


rate_limiter = RateLimiter()


# ---------------------------------------------------------------------------
# get_current_user (agent-coordinator compatible)
# ---------------------------------------------------------------------------


async def _user_from_bearer_credentials(credentials: HTTPAuthorizationCredentials) -> dict[str, Any] | None:
    if credentials.scheme != "Bearer":
        return None
    validation = get_jwt_handler().validate_token(credentials.credentials)
    if not validation["valid"]:
        return None
    payload = validation["payload"]
    user_id = payload.get("user_id") or payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    import time

    rate_check = await rate_limiter.is_allowed(user_id, payload.get("role", "default"))
    if not rate_check["allowed"]:
        retry_after = max(0, int(rate_check["reset_time"] - time.time()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    return {
        "sub": payload.get("sub") or user_id,
        "user_id": user_id,
        "username": payload.get("username"),
        "role": str(payload.get("role", "default")),
        "permissions": payload.get("permissions", []),
        "auth_type": "jwt",
    }


async def _user_from_apikey_credentials(credentials: HTTPAuthorizationCredentials) -> dict[str, Any] | None:
    if credentials.scheme.lower() != "apikey":
        return None
    from .api_key import api_key_manager

    validation = api_key_manager.validate_api_key(credentials.credentials)
    if not validation["valid"]:
        return None
    user_id = validation["user_id"]
    import time

    rate_check = await rate_limiter.is_allowed(user_id, "api_key")
    if not rate_check["allowed"]:
        retry_after = max(0, int(rate_check["reset_time"] - time.time()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    return {
        "sub": user_id,
        "user_id": user_id,
        "username": f"api_user_{user_id}",
        "role": "api",
        "permissions": validation["permissions"],
        "auth_type": "api_key",
    }


async def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)]) -> dict[str, Any]:
    """Get current user from JWT token or API key.

    This is the agent-coordinator compatible version that uses the dict-style
    JWTHandler and APIKeyManager.
    """
    try:
        if credentials:
            bearer_user = await _user_from_bearer_credentials(credentials)
            if bearer_user is not None:
                return bearer_user
            api_user = await _user_from_apikey_credentials(credentials)
            if api_user is not None:
                return api_user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


# ---------------------------------------------------------------------------
# Decorators (agent-coordinator compatible)
# ---------------------------------------------------------------------------


def _enforce_permissions(current_user: dict[str, Any] | None, required_permissions: list[str]) -> None:
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user_permissions = current_user.get("permissions", [])
    missing_permissions = [perm for perm in required_permissions if perm not in user_permissions]
    if missing_permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Insufficient permissions", "missing_permissions": missing_permissions},
        )


def _enforce_role(current_user: dict[str, Any] | None, required_roles: list[str]) -> None:
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user_role = current_user.get("role", "default")
    if hasattr(user_role, "value"):
        user_role = user_role.value
    elif not isinstance(user_role, str):
        user_role = str(user_role)
    required_role_strings = [role.value if hasattr(role, "value") else str(role) for role in required_roles]
    if user_role not in required_role_strings:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Insufficient role", "required_roles": required_role_strings, "current_role": user_role},
        )


def _with_auth_gate[F: Callable[..., Any]](func: F, enforce: Callable[[dict[str, Any] | None], None]) -> F:
    """Wrap ``func`` (sync or async) so ``enforce`` sees ``current_user`` first."""
    if asyncio.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            enforce(kwargs.get("current_user"))
            return await func(*args, **kwargs)

        return cast(F, async_wrapper)

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        enforce(kwargs.get("current_user"))
        return func(*args, **kwargs)

    return cast(F, sync_wrapper)


def require_permissions(required_permissions: list[str]) -> Callable[[F], F]:
    """Decorator to require specific permissions."""

    def decorator(func: F) -> F:
        return _with_auth_gate(func, lambda user: _enforce_permissions(user, required_permissions))

    return decorator


def require_role(required_roles: list[str]) -> Callable[[F], F]:
    """Decorator to require specific role."""

    def decorator(func: F) -> F:
        return _with_auth_gate(func, lambda user: _enforce_role(user, required_roles))

    return decorator


# ---------------------------------------------------------------------------
# Security headers and input validation (agent-coordinator compatible)
# ---------------------------------------------------------------------------


class SecurityHeaders:
    """Security headers middleware."""

    @staticmethod
    def get_security_headers() -> dict[str, str]:
        """Get security headers for responses."""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
            ),
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }


class InputValidator:
    """Input validation and sanitization."""

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format."""
        import re

        pattern = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
        return re.match(pattern, email) is not None

    @staticmethod
    def validate_password(password: str) -> dict[str, Any]:
        """Validate password strength."""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def sanitize_input(input_string: str) -> str:
        """Sanitize user input by escaping HTML metacharacters."""
        import html

        return html.escape(input_string).strip()

    @staticmethod
    def validate_json_structure(data: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
        """Validate JSON structure and required fields."""
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = InputValidator.validate_json_structure(
                    value, [f"{field}.{subfield}" for subfield in required_fields if subfield.startswith(f"{field}.")]
                )
                errors.extend(nested_validation["errors"])
        return {"valid": len(errors) == 0, "errors": errors}


security_headers = SecurityHeaders()
input_validator = InputValidator()


__all__ = [
    "AuthMiddleware",
    "AuthenticationError",
    "InputValidator",
    "RateLimiter",
    "SecurityHeaders",
    "get_current_user",
    "input_validator",
    "rate_limiter",
    "require_permissions",
    "require_role",
    "security_headers",
]
