# mypy: ignore-errors
"""
Authentication Middleware for AITBC Agent Coordinator
Implements JWT and API key authentication middleware
"""
import os
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from aitbc import get_logger

from .jwt_handler import api_key_manager, jwt_handler

logger = get_logger(__name__)
F = TypeVar('F', bound=Callable[..., Any])
security = HTTPBearer(auto_error=False)

class AuthenticationError(Exception):
    """Custom authentication error"""
    pass

class RateLimiter:
    """Distributed rate limiter using Redis"""

    def __init__(self, redis_url: str | None = None):
        from collections import deque

        import redis
        self.redis_url: str = redis_url or os.getenv('REDIS_URL', 'redis://localhost:6379/0') or 'redis://localhost:6379/0'
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {'default': {'requests': 100, 'window': 3600}, 'admin': {'requests': 1000, 'window': 3600}, 'api_key': {'requests': 10000, 'window': 3600}}
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info('RateLimiter connected to Redis')
        except Exception as e:
            logger.error('Failed to connect to Redis: %s', e)
            self.redis_client = None

    def is_allowed(self, user_id: str, user_role: str='default') -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time
        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits['default'])
        max_requests = limit_config['requests']
        window_seconds = limit_config['window']
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f'ratelimit:{user_id}:{user_role}'
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(key, window_seconds)
                return {'allowed': True, 'remaining': max_requests - current_count - 1, 'reset_time': current_time + window_seconds}
            else:
                oldest = self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {'allowed': False, 'remaining': 0, 'reset_time': reset_time}
        except Exception as e:
            logger.error('Redis rate limiting error, falling back to in-memory: %s', e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def _is_allowed_memory(self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque
        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests and user_requests[0] < current_time - window_seconds:
            user_requests.popleft()
        if len(user_requests) < max_requests:
            user_requests.append(current_time)
            return {'allowed': True, 'remaining': max_requests - len(user_requests), 'reset_time': current_time + window_seconds}
        else:
            oldest_request = user_requests[0]
            reset_time = oldest_request + window_seconds
            return {'allowed': False, 'remaining': 0, 'reset_time': reset_time}
rate_limiter = RateLimiter()

def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == 'Bearer':
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation['valid']:
                payload = validation['payload']
                user_id = payload.get('user_id')
                rate_check = rate_limiter.is_allowed(user_id, payload.get('role', 'default'))
                if not rate_check['allowed']:
                    raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={'error': 'Rate limit exceeded', 'reset_time': rate_check['reset_time']}, headers={'Retry-After': str(int(rate_check['reset_time'] - rate_limiter.requests[user_id][0]))})
                return {'user_id': user_id, 'username': payload.get('username'), 'role': str(payload.get('role', 'default')), 'permissions': payload.get('permissions', []), 'auth_type': 'jwt'}
        api_key = None
        if credentials and credentials.scheme == 'ApiKey':
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation['valid']:
                user_id = validation['user_id']
                rate_check = rate_limiter.is_allowed(user_id, 'api_key')
                if not rate_check['allowed']:
                    raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={'error': 'API key rate limit exceeded', 'reset_time': rate_check['reset_time']})
                return {'user_id': user_id, 'username': f'api_user_{user_id}', 'role': 'api', 'permissions': validation['permissions'], 'auth_type': 'api_key'}
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required', headers={'WWW-Authenticate': 'Bearer'})
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Authentication error: %s', e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication failed') from e

def require_permissions(required_permissions: list[str]) -> Callable[[F], F]:
    """Decorator to require specific permissions"""

    def decorator(func: F) -> F:

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required')
            user_permissions = current_user.get('permissions', [])
            missing_permissions = [perm for perm in required_permissions if perm not in user_permissions]
            if missing_permissions:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={'error': 'Insufficient permissions', 'missing_permissions': missing_permissions})
            return await func(*args, **kwargs)
        return cast(F, wrapper)
    return decorator

def require_role(required_roles: list[str]) -> Callable[[F], F]:
    """Decorator to require specific role"""

    def decorator(func: F) -> F:

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required')
            user_role = current_user.get('role', 'default')
            if hasattr(user_role, 'value'):
                user_role = user_role.value
            elif not isinstance(user_role, str):
                user_role = str(user_role)
            required_role_strings = []
            for role in required_roles:
                if hasattr(role, 'value'):
                    required_role_strings.append(role.value)
                else:
                    required_role_strings.append(str(role))
            if user_role not in required_role_strings:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={'error': 'Insufficient role', 'required_roles': required_role_strings, 'current_role': user_role})
            return await func(*args, **kwargs)
        return cast(F, wrapper)
    return decorator

class SecurityHeaders:
    """Security headers middleware"""

    @staticmethod
    def get_security_headers() -> dict[str, str]:
        """Get security headers for responses"""
        return {'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'X-XSS-Protection': '1; mode=block', 'Strict-Transport-Security': 'max-age=31536000; includeSubDomains', 'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'", 'Referrer-Policy': 'strict-origin-when-cross-origin', 'Permissions-Policy': 'geolocation=(), microphone=(), camera=()'}

class InputValidator:
    """Input validation and sanitization"""

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        import re
        pattern = '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

    @staticmethod
    def validate_password(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re
        errors = []
        if len(password) < 8:
            errors.append('Password must be at least 8 characters long')
        if not re.search('[A-Z]', password):
            errors.append('Password must contain at least one uppercase letter')
        if not re.search('[a-z]', password):
            errors.append('Password must contain at least one lowercase letter')
        if not re.search('\\d', password):
            errors.append('Password must contain at least one digit')
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append('Password must contain at least one special character')
        return {'valid': len(errors) == 0, 'errors': errors}

    @staticmethod
    def sanitize_input(input_string: str) -> str:
        """Sanitize user input"""
        import html
        sanitized = html.escape(input_string)
        dangerous_chars = ['<', '>', '"', "'", '&', '\x00', '\n', '\r', '\t']
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '')
        return sanitized.strip()

    @staticmethod
    def validate_json_structure(data: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f'Missing required field: {field}')
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = InputValidator.validate_json_structure(value, [f'{field}.{subfield}' for subfield in required_fields if subfield.startswith(f'{field}.')])
                errors.extend(nested_validation['errors'])
        return {'valid': len(errors) == 0, 'errors': errors}
security_headers = SecurityHeaders()
input_validator = InputValidator()
