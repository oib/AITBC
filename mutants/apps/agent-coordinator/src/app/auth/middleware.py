"""
Authentication Middleware for AITBC Agent Coordinator
Implements JWT and API key authentication middleware
"""

import os
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from aitbc import get_logger
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .jwt_handler import api_key_manager, jwt_handler

logger = get_logger(__name__)
F = TypeVar("F", bound=Callable[..., Any])
security = HTTPBearer(auto_error=False)


from mutmut.mutation.trampoline import MutantDict
from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated


class AuthenticationError(Exception):
    """Custom authentication error"""

    pass


mutants_xǁRateLimiterǁ__init____mutmut: MutantDict = {}  # type: ignore
mutants_xǁRateLimiterǁis_allowed__mutmut: MutantDict = {}  # type: ignore
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut: MutantDict = {}  # type: ignore


class RateLimiter:
    """Distributed rate limiter using Redis"""

    @_mutmut_mutated(mutants_xǁRateLimiterǁ__init____mutmut)
    def __init__(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_orig(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_1(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = None
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_2(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") and "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_3(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url and os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_4(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv(None, "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_5(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", None) or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_6(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_7(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = (
            redis_url
            or os.getenv(
                "REDIS_URL",
            )
            or "redis://localhost:6379/0"
        )
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_8(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("XXREDIS_URLXX", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_9(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("redis_url", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_10(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "XXredis://localhost:6379/0XX") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_11(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "REDIS://LOCALHOST:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_12(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "XXredis://localhost:6379/0XX"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_13(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "REDIS://LOCALHOST:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_14(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = ""
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_15(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = None
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_16(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = None
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_17(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "XXdefaultXX": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_18(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "DEFAULT": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_19(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"XXrequestsXX": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_20(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"REQUESTS": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_21(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 101, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_22(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "XXwindowXX": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_23(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "WINDOW": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_24(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3601},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_25(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "XXadminXX": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_26(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "ADMIN": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_27(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"XXrequestsXX": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_28(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"REQUESTS": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_29(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1001, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_30(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "XXwindowXX": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_31(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "WINDOW": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_32(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3601},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_33(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "XXapi_keyXX": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_34(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "API_KEY": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_35(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"XXrequestsXX": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_36(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"REQUESTS": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_37(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10001, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_38(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "XXwindowXX": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_39(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "WINDOW": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_40(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3601},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_41(self, redis_url: str | None = None):
        from collections import deque

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = None
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_42(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(None, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_43(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=None)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_44(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_45(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
            )
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_46(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=False)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_47(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info(None)
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_48(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("XXRateLimiter connected to RedisXX")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_49(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("ratelimiter connected to redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_50(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RATELIMITER CONNECTED TO REDIS")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_51(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error(None, e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_52(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception:
            logger.error("Failed to connect to Redis: %s", None)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_53(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error(e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_54(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception:
            logger.error(
                "Failed to connect to Redis: %s",
            )
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_55(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("XXFailed to connect to Redis: %sXX", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_56(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("failed to connect to redis: %s", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_57(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("FAILED TO CONNECT TO REDIS: %S", e)
            self.redis_client = None

    def xǁRateLimiterǁ__init____mutmut_58(self, redis_url: str | None = None):
        from collections import deque

        import redis

        self.redis_url: str = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
        self.redis_client: Any | None = None
        self.memory_requests: dict[str, deque[float]] = {}
        self.limits = {
            "default": {"requests": 100, "window": 3600},
            "admin": {"requests": 1000, "window": 3600},
            "api_key": {"requests": 10000, "window": 3600},
        }
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self.redis_client = ""

    @_mutmut_mutated(mutants_xǁRateLimiterǁis_allowed__mutmut)
    def is_allowed(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_orig(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_1(self, user_id: str, user_role: str = "XXdefaultXX") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_2(self, user_id: str, user_role: str = "DEFAULT") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_3(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""

        current_time = None
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_4(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = None
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_5(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(None, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_6(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, None)
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_7(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_8(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(
            user_role,
        )
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_9(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["XXdefaultXX"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_10(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["DEFAULT"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_11(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = None
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_12(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["XXrequestsXX"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_13(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["REQUESTS"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_14(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = None
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_15(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["XXwindowXX"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_16(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["WINDOW"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_17(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is not None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_18(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(None, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_19(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, None, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_20(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, None, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_21(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, None, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_22(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, None)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_23(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_24(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_25(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_26(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_27(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(
                user_id,
                user_role,
                current_time,
                max_requests,
            )
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_28(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = None
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_29(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(None, 0, current_time - window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_30(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, None, current_time - window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_31(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, None)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_32(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(0, current_time - window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_33(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, current_time - window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_34(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(
                key,
                0,
            )
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_35(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 1, current_time - window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_36(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time + window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_37(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = None
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_38(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(None)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_39(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count <= max_requests:
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_40(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(None, {str(current_time): current_time})
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_41(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, None)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_42(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd({str(current_time): current_time})
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_43(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(
                    key,
                )
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_44(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(None): current_time})
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_45(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(None, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_46(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(key, None)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_47(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_48(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(
                    key,
                )
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_49(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(key, window_seconds)
                return {
                    "XXallowedXX": True,
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_50(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(key, window_seconds)
                return {
                    "ALLOWED": True,
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_51(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(key, window_seconds)
                return {
                    "allowed": False,
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_52(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(key, window_seconds)
                return {
                    "allowed": True,
                    "XXremainingXX": max_requests - current_count - 1,
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_53(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(key, window_seconds)
                return {
                    "allowed": True,
                    "REMAINING": max_requests - current_count - 1,
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_54(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(key, window_seconds)
                return {
                    "allowed": True,
                    "remaining": max_requests - current_count + 1,
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_55(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(key, window_seconds)
                return {
                    "allowed": True,
                    "remaining": max_requests + current_count - 1,
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_56(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
        try:
            key = f"ratelimit:{user_id}:{user_role}"
            self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            current_count = self.redis_client.zcard(key)
            if current_count < max_requests:
                self.redis_client.zadd(key, {str(current_time): current_time})
                self.redis_client.expire(key, window_seconds)
                return {
                    "allowed": True,
                    "remaining": max_requests - current_count - 2,
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_57(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                    "XXreset_timeXX": current_time + window_seconds,
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_58(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                    "RESET_TIME": current_time + window_seconds,
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_59(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                    "reset_time": current_time - window_seconds,
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_60(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                oldest = None
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_61(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                oldest = self.redis_client.zrange(None, 0, 0, withscores=True)
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_62(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                oldest = self.redis_client.zrange(key, None, 0, withscores=True)
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_63(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                oldest = self.redis_client.zrange(key, 0, None, withscores=True)
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_64(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                oldest = self.redis_client.zrange(key, 0, 0, withscores=None)
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_65(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                oldest = self.redis_client.zrange(0, 0, withscores=True)
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_66(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                oldest = self.redis_client.zrange(key, 0, withscores=True)
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_67(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                oldest = self.redis_client.zrange(key, 0, withscores=True)
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_68(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                oldest = self.redis_client.zrange(
                    key,
                    0,
                    0,
                )
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_69(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                oldest = self.redis_client.zrange(key, 1, 0, withscores=True)
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_70(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                oldest = self.redis_client.zrange(key, 0, 1, withscores=True)
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_71(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                oldest = self.redis_client.zrange(key, 0, 0, withscores=False)
                if oldest:
                    reset_time = float(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_72(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                    reset_time = None
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_73(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                    reset_time = float(oldest[0][1]) - window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_74(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                    reset_time = float(None) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_75(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                    reset_time = float(oldest[1][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_76(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                    reset_time = float(oldest[0][2]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_77(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                    reset_time = None
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_78(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                    reset_time = current_time - window_seconds
                return {"allowed": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_79(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                return {"XXallowedXX": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_80(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                return {"ALLOWED": False, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_81(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                return {"allowed": True, "remaining": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_82(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                return {"allowed": False, "XXremainingXX": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_83(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                return {"allowed": False, "REMAINING": 0, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_84(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                return {"allowed": False, "remaining": 1, "reset_time": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_85(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                return {"allowed": False, "remaining": 0, "XXreset_timeXX": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_86(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
                return {"allowed": False, "remaining": 0, "RESET_TIME": reset_time}
        except Exception as e:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_87(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            logger.error(None, e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_88(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
        except Exception:
            logger.error("Redis rate limiting error, falling back to in-memory: %s", None)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_89(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            logger.error(e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_90(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
        except Exception:
            logger.error(
                "Redis rate limiting error, falling back to in-memory: %s",
            )
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_91(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            logger.error("XXRedis rate limiting error, falling back to in-memory: %sXX", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_92(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            logger.error("redis rate limiting error, falling back to in-memory: %s", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_93(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            logger.error("REDIS RATE LIMITING ERROR, FALLING BACK TO IN-MEMORY: %S", e)
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_94(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(None, user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_95(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, None, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_96(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, None, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_97(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, None, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_98(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, None)

    def xǁRateLimiterǁis_allowed__mutmut_99(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_role, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_100(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, current_time, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_101(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, max_requests, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_102(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(user_id, user_role, current_time, window_seconds)

    def xǁRateLimiterǁis_allowed__mutmut_103(self, user_id: str, user_role: str = "default") -> dict[str, Any]:
        """Check if user is allowed to make request"""
        import time

        current_time = time.time()
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        if self.redis_client is None:
            return self._is_allowed_memory(user_id, user_role, current_time, max_requests, window_seconds)
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
            return self._is_allowed_memory(
                user_id,
                user_role,
                current_time,
                max_requests,
            )

    @_mutmut_mutated(mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut)
    def _is_allowed_memory(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_orig(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_1(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id in self.memory_requests:
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

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_2(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = None
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

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_3(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = None
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

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_4(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests or user_requests[0] < current_time - window_seconds:
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

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_5(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests and user_requests[1] < current_time - window_seconds:
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

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_6(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests and user_requests[0] <= current_time - window_seconds:
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

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_7(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests and user_requests[0] < current_time + window_seconds:
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

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_8(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests and user_requests[0] < current_time - window_seconds:
            user_requests.popleft()
        if len(user_requests) <= max_requests:
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

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_9(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests and user_requests[0] < current_time - window_seconds:
            user_requests.popleft()
        if len(user_requests) < max_requests:
            user_requests.append(None)
            return {
                "allowed": True,
                "remaining": max_requests - len(user_requests),
                "reset_time": current_time + window_seconds,
            }
        else:
            oldest_request = user_requests[0]
            reset_time = oldest_request + window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_10(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests and user_requests[0] < current_time - window_seconds:
            user_requests.popleft()
        if len(user_requests) < max_requests:
            user_requests.append(current_time)
            return {
                "XXallowedXX": True,
                "remaining": max_requests - len(user_requests),
                "reset_time": current_time + window_seconds,
            }
        else:
            oldest_request = user_requests[0]
            reset_time = oldest_request + window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_11(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests and user_requests[0] < current_time - window_seconds:
            user_requests.popleft()
        if len(user_requests) < max_requests:
            user_requests.append(current_time)
            return {
                "ALLOWED": True,
                "remaining": max_requests - len(user_requests),
                "reset_time": current_time + window_seconds,
            }
        else:
            oldest_request = user_requests[0]
            reset_time = oldest_request + window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_12(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests and user_requests[0] < current_time - window_seconds:
            user_requests.popleft()
        if len(user_requests) < max_requests:
            user_requests.append(current_time)
            return {
                "allowed": False,
                "remaining": max_requests - len(user_requests),
                "reset_time": current_time + window_seconds,
            }
        else:
            oldest_request = user_requests[0]
            reset_time = oldest_request + window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_13(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests and user_requests[0] < current_time - window_seconds:
            user_requests.popleft()
        if len(user_requests) < max_requests:
            user_requests.append(current_time)
            return {
                "allowed": True,
                "XXremainingXX": max_requests - len(user_requests),
                "reset_time": current_time + window_seconds,
            }
        else:
            oldest_request = user_requests[0]
            reset_time = oldest_request + window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_14(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests and user_requests[0] < current_time - window_seconds:
            user_requests.popleft()
        if len(user_requests) < max_requests:
            user_requests.append(current_time)
            return {
                "allowed": True,
                "REMAINING": max_requests - len(user_requests),
                "reset_time": current_time + window_seconds,
            }
        else:
            oldest_request = user_requests[0]
            reset_time = oldest_request + window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_15(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

        if user_id not in self.memory_requests:
            self.memory_requests[user_id] = deque()
        user_requests = self.memory_requests[user_id]
        while user_requests and user_requests[0] < current_time - window_seconds:
            user_requests.popleft()
        if len(user_requests) < max_requests:
            user_requests.append(current_time)
            return {
                "allowed": True,
                "remaining": max_requests + len(user_requests),
                "reset_time": current_time + window_seconds,
            }
        else:
            oldest_request = user_requests[0]
            reset_time = oldest_request + window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_16(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
                "XXreset_timeXX": current_time + window_seconds,
            }
        else:
            oldest_request = user_requests[0]
            reset_time = oldest_request + window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_17(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
                "RESET_TIME": current_time + window_seconds,
            }
        else:
            oldest_request = user_requests[0]
            reset_time = oldest_request + window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_18(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
                "reset_time": current_time - window_seconds,
            }
        else:
            oldest_request = user_requests[0]
            reset_time = oldest_request + window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_19(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
            oldest_request = None
            reset_time = oldest_request + window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_20(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
            oldest_request = user_requests[1]
            reset_time = oldest_request + window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_21(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
            user_requests[0]
            reset_time = None
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_22(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
            reset_time = oldest_request - window_seconds
            return {"allowed": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_23(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
            return {"XXallowedXX": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_24(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
            return {"ALLOWED": False, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_25(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
            return {"allowed": True, "remaining": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_26(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
            return {"allowed": False, "XXremainingXX": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_27(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
            return {"allowed": False, "REMAINING": 0, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_28(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
            return {"allowed": False, "remaining": 1, "reset_time": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_29(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
            return {"allowed": False, "remaining": 0, "XXreset_timeXX": reset_time}

    def xǁRateLimiterǁ_is_allowed_memory__mutmut_30(
        self, user_id: str, user_role: str, current_time: float, max_requests: int, window_seconds: int
    ) -> dict[str, Any]:
        """Fallback in-memory rate limiting"""
        from collections import deque

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
            return {"allowed": False, "remaining": 0, "RESET_TIME": reset_time}


mutants_xǁRateLimiterǁ__init____mutmut["_mutmut_orig"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_orig  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_1"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_1  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_2"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_2  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_3"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_3  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_4"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_4  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_5"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_5  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_6"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_6  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_7"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_7  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_8"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_8  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_9"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_9  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_10"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_10  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_11"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_11  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_12"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_12  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_13"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_13  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_14"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_14  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_15"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_15  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_16"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_16  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_17"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_17  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_18"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_18  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_19"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_19  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_20"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_20  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_21"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_21  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_22"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_22  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_23"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_23  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_24"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_24  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_25"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_25  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_26"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_26  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_27"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_27  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_28"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_28  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_29"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_29  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_30"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_30  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_31"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_31  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_32"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_32  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_33"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_33  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_34"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_34  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_35"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_35  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_36"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_36  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_37"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_37  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_38"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_38  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_39"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_39  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_40"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_40  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_41"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_41  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_42"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_42  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_43"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_43  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_44"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_44  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_45"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_45  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_46"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_46  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_47"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_47  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_48"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_48  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_49"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_49  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_50"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_50  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_51"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_51  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_52"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_52  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_53"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_53  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_54"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_54  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_55"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_55  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_56"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_56  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_57"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_57  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut["xǁRateLimiterǁ__init____mutmut_58"] = RateLimiter.xǁRateLimiterǁ__init____mutmut_58  # type: ignore # mutmut generated

mutants_xǁRateLimiterǁis_allowed__mutmut["_mutmut_orig"] = RateLimiter.xǁRateLimiterǁis_allowed__mutmut_orig  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_1"] = RateLimiter.xǁRateLimiterǁis_allowed__mutmut_1  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_2"] = RateLimiter.xǁRateLimiterǁis_allowed__mutmut_2  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_3"] = RateLimiter.xǁRateLimiterǁis_allowed__mutmut_3  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_4"] = RateLimiter.xǁRateLimiterǁis_allowed__mutmut_4  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_5"] = RateLimiter.xǁRateLimiterǁis_allowed__mutmut_5  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_6"] = RateLimiter.xǁRateLimiterǁis_allowed__mutmut_6  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_7"] = RateLimiter.xǁRateLimiterǁis_allowed__mutmut_7  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_8"] = RateLimiter.xǁRateLimiterǁis_allowed__mutmut_8  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_9"] = RateLimiter.xǁRateLimiterǁis_allowed__mutmut_9  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_10"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_10
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_11"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_11
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_12"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_12
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_13"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_13
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_14"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_14
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_15"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_15
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_16"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_16
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_17"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_17
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_18"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_18
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_19"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_19
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_20"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_20
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_21"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_21
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_22"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_22
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_23"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_23
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_24"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_24
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_25"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_25
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_26"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_26
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_27"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_27
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_28"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_28
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_29"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_29
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_30"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_30
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_31"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_31
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_32"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_32
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_33"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_33
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_34"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_34
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_35"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_35
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_36"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_36
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_37"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_37
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_38"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_38
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_39"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_39
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_40"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_40
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_41"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_41
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_42"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_42
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_43"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_43
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_44"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_44
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_45"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_45
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_46"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_46
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_47"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_47
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_48"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_48
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_49"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_49
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_50"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_50
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_51"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_51
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_52"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_52
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_53"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_53
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_54"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_54
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_55"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_55
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_56"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_56
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_57"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_57
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_58"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_58
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_59"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_59
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_60"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_60
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_61"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_61
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_62"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_62
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_63"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_63
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_64"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_64
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_65"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_65
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_66"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_66
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_67"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_67
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_68"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_68
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_69"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_69
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_70"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_70
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_71"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_71
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_72"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_72
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_73"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_73
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_74"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_74
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_75"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_75
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_76"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_76
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_77"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_77
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_78"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_78
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_79"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_79
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_80"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_80
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_81"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_81
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_82"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_82
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_83"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_83
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_84"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_84
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_85"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_85
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_86"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_86
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_87"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_87
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_88"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_88
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_89"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_89
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_90"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_90
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_91"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_91
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_92"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_92
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_93"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_93
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_94"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_94
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_95"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_95
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_96"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_96
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_97"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_97
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_98"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_98
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_99"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_99
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_100"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_100
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_101"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_101
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_102"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_102
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁis_allowed__mutmut["xǁRateLimiterǁis_allowed__mutmut_103"] = (
    RateLimiter.xǁRateLimiterǁis_allowed__mutmut_103
)  # type: ignore # mutmut generated

mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["_mutmut_orig"] = RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_orig  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_1"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_1
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_2"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_2
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_3"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_3
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_4"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_4
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_5"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_5
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_6"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_6
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_7"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_7
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_8"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_8
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_9"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_9
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_10"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_10
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_11"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_11
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_12"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_12
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_13"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_13
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_14"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_14
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_15"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_15
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_16"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_16
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_17"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_17
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_18"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_18
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_19"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_19
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_20"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_20
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_21"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_21
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_22"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_22
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_23"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_23
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_24"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_24
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_25"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_25
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_26"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_26
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_27"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_27
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_28"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_28
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_29"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_29
)  # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ_is_allowed_memory__mutmut["xǁRateLimiterǁ_is_allowed_memory__mutmut_30"] = (
    RateLimiter.xǁRateLimiterǁ_is_allowed_memory__mutmut_30
)  # type: ignore # mutmut generated


rate_limiter = RateLimiter()
mutants_x_get_current_user__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_get_current_user__mutmut)
def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_orig(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_1(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials or credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_2(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme != "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_3(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "XXBearerXX":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_4(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_5(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "BEARER":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_6(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = None
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_7(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            validation = None
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_8(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            validation = jwt_handler.validate_token(None)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_9(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["XXvalidXX"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_10(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["VALID"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_11(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = None
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_12(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["XXpayloadXX"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_13(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["PAYLOAD"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_14(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = None
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_15(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get(None)
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_16(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("XXuser_idXX")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_17(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("USER_ID")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_18(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = None
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_19(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(None, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_20(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, None)
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_21(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_22(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(
                    user_id,
                )
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_23(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get(None, "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_24(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", None))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_25(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_26(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(
                    user_id,
                    payload.get(
                        "role",
                    ),
                )
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_27(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("XXroleXX", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_28(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("ROLE", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_29(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "XXdefaultXX"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_30(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "DEFAULT"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_31(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_32(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["XXallowedXX"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_33(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["ALLOWED"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_34(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=None,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_35(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=None,
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_36(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers=None,
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_37(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_38(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_39(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_40(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"XXerrorXX": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_41(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"ERROR": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_42(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "XXRate limit exceededXX", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_43(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_44(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "RATE LIMIT EXCEEDED", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_45(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "XXreset_timeXX": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_46(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "RESET_TIME": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_47(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["XXreset_timeXX"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_48(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["RESET_TIME"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_49(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={
                            "XXRetry-AfterXX": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))
                        },
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_50(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"retry-after": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_51(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"RETRY-AFTER": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_52(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(None)},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_53(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(None))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_54(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] + rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_55(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={
                            "Retry-After": str(int(rate_check["XXreset_timeXX"] - rate_limiter.memory_requests[user_id][0]))
                        },
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_56(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["RESET_TIME"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_57(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][1]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_58(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "XXuser_idXX": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_59(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "USER_ID": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_60(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "XXusernameXX": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_61(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "USERNAME": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_62(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get(None),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_63(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("XXusernameXX"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_64(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("USERNAME"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_65(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "XXroleXX": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_66(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "ROLE": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_67(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(None),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_68(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get(None, "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_69(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", None)),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_70(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_71(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(
                        payload.get(
                            "role",
                        )
                    ),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_72(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("XXroleXX", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_73(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("ROLE", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_74(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "XXdefaultXX")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_75(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "DEFAULT")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_76(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "XXpermissionsXX": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_77(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "PERMISSIONS": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_78(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get(None, []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_79(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", None),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_80(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get([]),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_81(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get(
                        "permissions",
                    ),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_82(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("XXpermissionsXX", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_83(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("PERMISSIONS", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_84(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "XXauth_typeXX": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_85(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "AUTH_TYPE": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_86(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "XXjwtXX",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_87(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "JWT",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_88(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = ""
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_89(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials or credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_90(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme != "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_91(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "XXApiKeyXX":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_92(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "apikey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_93(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "APIKEY":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_94(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = None
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_95(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = None
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_96(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(None)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_97(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["XXvalidXX"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_98(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["VALID"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_99(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = None
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_100(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["XXuser_idXX"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_101(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["USER_ID"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_102(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = None
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_103(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(None, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_104(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, None)
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_105(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed("api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_106(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(
                    user_id,
                )
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_107(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "XXapi_keyXX")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_108(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "API_KEY")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_109(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_110(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["XXallowedXX"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_111(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["ALLOWED"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_112(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=None,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_113(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=None,
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_114(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_115(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_116(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"XXerrorXX": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_117(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"ERROR": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_118(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "XXAPI key rate limit exceededXX", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_119(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "api key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_120(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API KEY RATE LIMIT EXCEEDED", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_121(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "XXreset_timeXX": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_122(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "RESET_TIME": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_123(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["XXreset_timeXX"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_124(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["RESET_TIME"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_125(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "XXuser_idXX": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_126(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "USER_ID": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_127(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "XXusernameXX": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_128(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "USERNAME": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_129(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "XXroleXX": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_130(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "ROLE": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_131(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "XXapiXX",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_132(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "API",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_133(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "XXpermissionsXX": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_134(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "PERMISSIONS": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_135(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["XXpermissionsXX"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_136(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["PERMISSIONS"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_137(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "XXauth_typeXX": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_138(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "AUTH_TYPE": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_139(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "XXapi_keyXX",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_140(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "API_KEY",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_141(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(status_code=None, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_142(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=None, headers={"WWW-Authenticate": "Bearer"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_143(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers=None)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_144(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_145(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Bearer"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_146(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_147(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="XXAuthentication requiredXX",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_148(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_149(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="AUTHENTICATION REQUIRED", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_150(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"XXWWW-AuthenticateXX": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_151(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"www-authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_152(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-AUTHENTICATE": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_153(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "XXBearerXX"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_154(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_155(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "BEARER"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_156(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(None, e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_157(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_158(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_159(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Authentication error: %s",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_160(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("XXAuthentication error: %sXX", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_161(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_162(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("AUTHENTICATION ERROR: %S", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


def x_get_current_user__mutmut_163(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=None, detail="Authentication failed") from e


def x_get_current_user__mutmut_164(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=None) from e


def x_get_current_user__mutmut_165(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(detail="Authentication failed") from e


def x_get_current_user__mutmut_166(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from e


def x_get_current_user__mutmut_167(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="XXAuthentication failedXX") from e


def x_get_current_user__mutmut_168(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication failed") from e


def x_get_current_user__mutmut_169(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                rate_check = rate_limiter.is_allowed(user_id, payload.get("role", "default"))
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "Rate limit exceeded", "reset_time": rate_check["reset_time"]},
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.memory_requests[user_id][0]))},
                    )
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": str(payload.get("role", "default")),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt",
                }
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            pass
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            if validation["valid"]:
                user_id = validation["user_id"]
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={"error": "API key rate limit exceeded", "reset_time": rate_check["reset_time"]},
                    )
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key",
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="AUTHENTICATION FAILED") from e


mutants_x_get_current_user__mutmut["_mutmut_orig"] = x_get_current_user__mutmut_orig  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_1"] = x_get_current_user__mutmut_1  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_2"] = x_get_current_user__mutmut_2  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_3"] = x_get_current_user__mutmut_3  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_4"] = x_get_current_user__mutmut_4  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_5"] = x_get_current_user__mutmut_5  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_6"] = x_get_current_user__mutmut_6  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_7"] = x_get_current_user__mutmut_7  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_8"] = x_get_current_user__mutmut_8  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_9"] = x_get_current_user__mutmut_9  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_10"] = x_get_current_user__mutmut_10  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_11"] = x_get_current_user__mutmut_11  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_12"] = x_get_current_user__mutmut_12  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_13"] = x_get_current_user__mutmut_13  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_14"] = x_get_current_user__mutmut_14  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_15"] = x_get_current_user__mutmut_15  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_16"] = x_get_current_user__mutmut_16  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_17"] = x_get_current_user__mutmut_17  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_18"] = x_get_current_user__mutmut_18  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_19"] = x_get_current_user__mutmut_19  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_20"] = x_get_current_user__mutmut_20  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_21"] = x_get_current_user__mutmut_21  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_22"] = x_get_current_user__mutmut_22  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_23"] = x_get_current_user__mutmut_23  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_24"] = x_get_current_user__mutmut_24  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_25"] = x_get_current_user__mutmut_25  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_26"] = x_get_current_user__mutmut_26  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_27"] = x_get_current_user__mutmut_27  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_28"] = x_get_current_user__mutmut_28  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_29"] = x_get_current_user__mutmut_29  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_30"] = x_get_current_user__mutmut_30  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_31"] = x_get_current_user__mutmut_31  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_32"] = x_get_current_user__mutmut_32  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_33"] = x_get_current_user__mutmut_33  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_34"] = x_get_current_user__mutmut_34  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_35"] = x_get_current_user__mutmut_35  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_36"] = x_get_current_user__mutmut_36  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_37"] = x_get_current_user__mutmut_37  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_38"] = x_get_current_user__mutmut_38  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_39"] = x_get_current_user__mutmut_39  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_40"] = x_get_current_user__mutmut_40  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_41"] = x_get_current_user__mutmut_41  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_42"] = x_get_current_user__mutmut_42  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_43"] = x_get_current_user__mutmut_43  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_44"] = x_get_current_user__mutmut_44  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_45"] = x_get_current_user__mutmut_45  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_46"] = x_get_current_user__mutmut_46  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_47"] = x_get_current_user__mutmut_47  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_48"] = x_get_current_user__mutmut_48  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_49"] = x_get_current_user__mutmut_49  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_50"] = x_get_current_user__mutmut_50  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_51"] = x_get_current_user__mutmut_51  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_52"] = x_get_current_user__mutmut_52  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_53"] = x_get_current_user__mutmut_53  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_54"] = x_get_current_user__mutmut_54  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_55"] = x_get_current_user__mutmut_55  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_56"] = x_get_current_user__mutmut_56  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_57"] = x_get_current_user__mutmut_57  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_58"] = x_get_current_user__mutmut_58  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_59"] = x_get_current_user__mutmut_59  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_60"] = x_get_current_user__mutmut_60  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_61"] = x_get_current_user__mutmut_61  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_62"] = x_get_current_user__mutmut_62  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_63"] = x_get_current_user__mutmut_63  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_64"] = x_get_current_user__mutmut_64  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_65"] = x_get_current_user__mutmut_65  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_66"] = x_get_current_user__mutmut_66  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_67"] = x_get_current_user__mutmut_67  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_68"] = x_get_current_user__mutmut_68  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_69"] = x_get_current_user__mutmut_69  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_70"] = x_get_current_user__mutmut_70  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_71"] = x_get_current_user__mutmut_71  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_72"] = x_get_current_user__mutmut_72  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_73"] = x_get_current_user__mutmut_73  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_74"] = x_get_current_user__mutmut_74  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_75"] = x_get_current_user__mutmut_75  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_76"] = x_get_current_user__mutmut_76  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_77"] = x_get_current_user__mutmut_77  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_78"] = x_get_current_user__mutmut_78  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_79"] = x_get_current_user__mutmut_79  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_80"] = x_get_current_user__mutmut_80  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_81"] = x_get_current_user__mutmut_81  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_82"] = x_get_current_user__mutmut_82  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_83"] = x_get_current_user__mutmut_83  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_84"] = x_get_current_user__mutmut_84  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_85"] = x_get_current_user__mutmut_85  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_86"] = x_get_current_user__mutmut_86  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_87"] = x_get_current_user__mutmut_87  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_88"] = x_get_current_user__mutmut_88  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_89"] = x_get_current_user__mutmut_89  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_90"] = x_get_current_user__mutmut_90  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_91"] = x_get_current_user__mutmut_91  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_92"] = x_get_current_user__mutmut_92  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_93"] = x_get_current_user__mutmut_93  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_94"] = x_get_current_user__mutmut_94  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_95"] = x_get_current_user__mutmut_95  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_96"] = x_get_current_user__mutmut_96  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_97"] = x_get_current_user__mutmut_97  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_98"] = x_get_current_user__mutmut_98  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_99"] = x_get_current_user__mutmut_99  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_100"] = x_get_current_user__mutmut_100  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_101"] = x_get_current_user__mutmut_101  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_102"] = x_get_current_user__mutmut_102  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_103"] = x_get_current_user__mutmut_103  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_104"] = x_get_current_user__mutmut_104  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_105"] = x_get_current_user__mutmut_105  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_106"] = x_get_current_user__mutmut_106  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_107"] = x_get_current_user__mutmut_107  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_108"] = x_get_current_user__mutmut_108  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_109"] = x_get_current_user__mutmut_109  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_110"] = x_get_current_user__mutmut_110  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_111"] = x_get_current_user__mutmut_111  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_112"] = x_get_current_user__mutmut_112  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_113"] = x_get_current_user__mutmut_113  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_114"] = x_get_current_user__mutmut_114  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_115"] = x_get_current_user__mutmut_115  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_116"] = x_get_current_user__mutmut_116  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_117"] = x_get_current_user__mutmut_117  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_118"] = x_get_current_user__mutmut_118  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_119"] = x_get_current_user__mutmut_119  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_120"] = x_get_current_user__mutmut_120  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_121"] = x_get_current_user__mutmut_121  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_122"] = x_get_current_user__mutmut_122  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_123"] = x_get_current_user__mutmut_123  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_124"] = x_get_current_user__mutmut_124  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_125"] = x_get_current_user__mutmut_125  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_126"] = x_get_current_user__mutmut_126  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_127"] = x_get_current_user__mutmut_127  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_128"] = x_get_current_user__mutmut_128  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_129"] = x_get_current_user__mutmut_129  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_130"] = x_get_current_user__mutmut_130  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_131"] = x_get_current_user__mutmut_131  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_132"] = x_get_current_user__mutmut_132  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_133"] = x_get_current_user__mutmut_133  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_134"] = x_get_current_user__mutmut_134  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_135"] = x_get_current_user__mutmut_135  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_136"] = x_get_current_user__mutmut_136  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_137"] = x_get_current_user__mutmut_137  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_138"] = x_get_current_user__mutmut_138  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_139"] = x_get_current_user__mutmut_139  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_140"] = x_get_current_user__mutmut_140  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_141"] = x_get_current_user__mutmut_141  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_142"] = x_get_current_user__mutmut_142  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_143"] = x_get_current_user__mutmut_143  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_144"] = x_get_current_user__mutmut_144  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_145"] = x_get_current_user__mutmut_145  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_146"] = x_get_current_user__mutmut_146  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_147"] = x_get_current_user__mutmut_147  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_148"] = x_get_current_user__mutmut_148  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_149"] = x_get_current_user__mutmut_149  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_150"] = x_get_current_user__mutmut_150  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_151"] = x_get_current_user__mutmut_151  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_152"] = x_get_current_user__mutmut_152  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_153"] = x_get_current_user__mutmut_153  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_154"] = x_get_current_user__mutmut_154  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_155"] = x_get_current_user__mutmut_155  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_156"] = x_get_current_user__mutmut_156  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_157"] = x_get_current_user__mutmut_157  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_158"] = x_get_current_user__mutmut_158  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_159"] = x_get_current_user__mutmut_159  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_160"] = x_get_current_user__mutmut_160  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_161"] = x_get_current_user__mutmut_161  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_162"] = x_get_current_user__mutmut_162  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_163"] = x_get_current_user__mutmut_163  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_164"] = x_get_current_user__mutmut_164  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_165"] = x_get_current_user__mutmut_165  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_166"] = x_get_current_user__mutmut_166  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_167"] = x_get_current_user__mutmut_167  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_168"] = x_get_current_user__mutmut_168  # type: ignore # mutmut generated
mutants_x_get_current_user__mutmut["x_get_current_user__mutmut_169"] = x_get_current_user__mutmut_169  # type: ignore # mutmut generated
mutants_x_require_permissions__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_require_permissions__mutmut)
def require_permissions(required_permissions: list[str]) -> Callable[[F], F]:
    """Decorator to require specific permissions"""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            user_permissions = current_user.get("permissions", [])
            missing_permissions = [perm for perm in required_permissions if perm not in user_permissions]
            if missing_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Insufficient permissions", "missing_permissions": missing_permissions},
                )
            return await func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


def x_require_permissions__mutmut_orig(required_permissions: list[str]) -> Callable[[F], F]:
    """Decorator to require specific permissions"""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            user_permissions = current_user.get("permissions", [])
            missing_permissions = [perm for perm in required_permissions if perm not in user_permissions]
            if missing_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Insufficient permissions", "missing_permissions": missing_permissions},
                )
            return await func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


def x_require_permissions__mutmut_1(required_permissions: list[str]) -> Callable[[F], F]:
    """Decorator to require specific permissions"""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            user_permissions = current_user.get("permissions", [])
            missing_permissions = [perm for perm in required_permissions if perm not in user_permissions]
            if missing_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Insufficient permissions", "missing_permissions": missing_permissions},
                )
            return await func(*args, **kwargs)

        return cast(None, wrapper)

    return decorator


def x_require_permissions__mutmut_2(required_permissions: list[str]) -> Callable[[F], F]:
    """Decorator to require specific permissions"""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            user_permissions = current_user.get("permissions", [])
            missing_permissions = [perm for perm in required_permissions if perm not in user_permissions]
            if missing_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Insufficient permissions", "missing_permissions": missing_permissions},
                )
            return await func(*args, **kwargs)

        return cast(F, None)

    return decorator


def x_require_permissions__mutmut_3(required_permissions: list[str]) -> Callable[[F], F]:
    """Decorator to require specific permissions"""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            user_permissions = current_user.get("permissions", [])
            missing_permissions = [perm for perm in required_permissions if perm not in user_permissions]
            if missing_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Insufficient permissions", "missing_permissions": missing_permissions},
                )
            return await func(*args, **kwargs)

        return cast(wrapper)

    return decorator


def x_require_permissions__mutmut_4(required_permissions: list[str]) -> Callable[[F], F]:
    """Decorator to require specific permissions"""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            user_permissions = current_user.get("permissions", [])
            missing_permissions = [perm for perm in required_permissions if perm not in user_permissions]
            if missing_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Insufficient permissions", "missing_permissions": missing_permissions},
                )
            return await func(*args, **kwargs)

        return cast(
            F,
        )

    return decorator


mutants_x_require_permissions__mutmut["_mutmut_orig"] = x_require_permissions__mutmut_orig  # type: ignore # mutmut generated
mutants_x_require_permissions__mutmut["x_require_permissions__mutmut_1"] = x_require_permissions__mutmut_1  # type: ignore # mutmut generated
mutants_x_require_permissions__mutmut["x_require_permissions__mutmut_2"] = x_require_permissions__mutmut_2  # type: ignore # mutmut generated
mutants_x_require_permissions__mutmut["x_require_permissions__mutmut_3"] = x_require_permissions__mutmut_3  # type: ignore # mutmut generated
mutants_x_require_permissions__mutmut["x_require_permissions__mutmut_4"] = x_require_permissions__mutmut_4  # type: ignore # mutmut generated
mutants_x_require_role__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_require_role__mutmut)
def require_role(required_roles: list[str]) -> Callable[[F], F]:
    """Decorator to require specific role"""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            user_role = current_user.get("role", "default")
            if hasattr(user_role, "value"):
                user_role = user_role.value
            elif not isinstance(user_role, str):
                user_role = str(user_role)
            required_role_strings = []
            for role in required_roles:
                if hasattr(role, "value"):
                    required_role_strings.append(role.value)
                else:
                    required_role_strings.append(str(role))
            if user_role not in required_role_strings:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Insufficient role", "required_roles": required_role_strings, "current_role": user_role},
                )
            return await func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


def x_require_role__mutmut_orig(required_roles: list[str]) -> Callable[[F], F]:
    """Decorator to require specific role"""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            user_role = current_user.get("role", "default")
            if hasattr(user_role, "value"):
                user_role = user_role.value
            elif not isinstance(user_role, str):
                user_role = str(user_role)
            required_role_strings = []
            for role in required_roles:
                if hasattr(role, "value"):
                    required_role_strings.append(role.value)
                else:
                    required_role_strings.append(str(role))
            if user_role not in required_role_strings:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Insufficient role", "required_roles": required_role_strings, "current_role": user_role},
                )
            return await func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


def x_require_role__mutmut_1(required_roles: list[str]) -> Callable[[F], F]:
    """Decorator to require specific role"""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            user_role = current_user.get("role", "default")
            if hasattr(user_role, "value"):
                user_role = user_role.value
            elif not isinstance(user_role, str):
                user_role = str(user_role)
            required_role_strings = []
            for role in required_roles:
                if hasattr(role, "value"):
                    required_role_strings.append(role.value)
                else:
                    required_role_strings.append(str(role))
            if user_role not in required_role_strings:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Insufficient role", "required_roles": required_role_strings, "current_role": user_role},
                )
            return await func(*args, **kwargs)

        return cast(None, wrapper)

    return decorator


def x_require_role__mutmut_2(required_roles: list[str]) -> Callable[[F], F]:
    """Decorator to require specific role"""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            user_role = current_user.get("role", "default")
            if hasattr(user_role, "value"):
                user_role = user_role.value
            elif not isinstance(user_role, str):
                user_role = str(user_role)
            required_role_strings = []
            for role in required_roles:
                if hasattr(role, "value"):
                    required_role_strings.append(role.value)
                else:
                    required_role_strings.append(str(role))
            if user_role not in required_role_strings:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Insufficient role", "required_roles": required_role_strings, "current_role": user_role},
                )
            return await func(*args, **kwargs)

        return cast(F, None)

    return decorator


def x_require_role__mutmut_3(required_roles: list[str]) -> Callable[[F], F]:
    """Decorator to require specific role"""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            user_role = current_user.get("role", "default")
            if hasattr(user_role, "value"):
                user_role = user_role.value
            elif not isinstance(user_role, str):
                user_role = str(user_role)
            required_role_strings = []
            for role in required_roles:
                if hasattr(role, "value"):
                    required_role_strings.append(role.value)
                else:
                    required_role_strings.append(str(role))
            if user_role not in required_role_strings:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Insufficient role", "required_roles": required_role_strings, "current_role": user_role},
                )
            return await func(*args, **kwargs)

        return cast(wrapper)

    return decorator


def x_require_role__mutmut_4(required_roles: list[str]) -> Callable[[F], F]:
    """Decorator to require specific role"""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            user_role = current_user.get("role", "default")
            if hasattr(user_role, "value"):
                user_role = user_role.value
            elif not isinstance(user_role, str):
                user_role = str(user_role)
            required_role_strings = []
            for role in required_roles:
                if hasattr(role, "value"):
                    required_role_strings.append(role.value)
                else:
                    required_role_strings.append(str(role))
            if user_role not in required_role_strings:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Insufficient role", "required_roles": required_role_strings, "current_role": user_role},
                )
            return await func(*args, **kwargs)

        return cast(
            F,
        )

    return decorator


mutants_x_require_role__mutmut["_mutmut_orig"] = x_require_role__mutmut_orig  # type: ignore # mutmut generated
mutants_x_require_role__mutmut["x_require_role__mutmut_1"] = x_require_role__mutmut_1  # type: ignore # mutmut generated
mutants_x_require_role__mutmut["x_require_role__mutmut_2"] = x_require_role__mutmut_2  # type: ignore # mutmut generated
mutants_x_require_role__mutmut["x_require_role__mutmut_3"] = x_require_role__mutmut_3  # type: ignore # mutmut generated
mutants_x_require_role__mutmut["x_require_role__mutmut_4"] = x_require_role__mutmut_4  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut: MutantDict = {}  # type: ignore


class SecurityHeaders:
    """Security headers middleware"""

    @staticmethod
    @_mutmut_mutated(mutants_xǁSecurityHeadersǁget_security_headers__mutmut)
    def get_security_headers() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_orig() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_1() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "XXX-Content-Type-OptionsXX": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_2() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "x-content-type-options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_3() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-CONTENT-TYPE-OPTIONS": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_4() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "XXnosniffXX",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_5() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "NOSNIFF",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_6() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "XXX-Frame-OptionsXX": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_7() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "x-frame-options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_8() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-FRAME-OPTIONS": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_9() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "XXDENYXX",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_10() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "deny",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_11() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "XXX-XSS-ProtectionXX": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_12() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "x-xss-protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_13() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-PROTECTION": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_14() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "XX1; mode=blockXX",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_15() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; MODE=BLOCK",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_16() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "XXStrict-Transport-SecurityXX": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_17() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "strict-transport-security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_18() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "STRICT-TRANSPORT-SECURITY": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_19() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "XXmax-age=31536000; includeSubDomainsXX",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_20() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includesubdomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_21() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "MAX-AGE=31536000; INCLUDESUBDOMAINS",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_22() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "XXContent-Security-PolicyXX": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_23() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "content-security-policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_24() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "CONTENT-SECURITY-POLICY": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_25() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "XXdefault-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'XX",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_26() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "DEFAULT-SRC 'SELF'; SCRIPT-SRC 'SELF' 'UNSAFE-INLINE'; STYLE-SRC 'SELF' 'UNSAFE-INLINE'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_27() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "XXReferrer-PolicyXX": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_28() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "referrer-policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_29() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "REFERRER-POLICY": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_30() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "XXstrict-origin-when-cross-originXX",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_31() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "STRICT-ORIGIN-WHEN-CROSS-ORIGIN",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_32() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "XXPermissions-PolicyXX": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_33() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "permissions-policy": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_34() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "PERMISSIONS-POLICY": "geolocation=(), microphone=(), camera=()",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_35() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "XXgeolocation=(), microphone=(), camera=()XX",
        }

    @staticmethod
    def xǁSecurityHeadersǁget_security_headers__mutmut_36() -> dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "GEOLOCATION=(), MICROPHONE=(), CAMERA=()",
        }


mutants_xǁSecurityHeadersǁget_security_headers__mutmut["_mutmut_orig"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_orig
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_1"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_1
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_2"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_2
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_3"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_3
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_4"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_4
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_5"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_5
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_6"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_6
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_7"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_7
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_8"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_8
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_9"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_9
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_10"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_10
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_11"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_11
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_12"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_12
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_13"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_13
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_14"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_14
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_15"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_15
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_16"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_16
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_17"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_17
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_18"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_18
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_19"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_19
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_20"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_20
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_21"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_21
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_22"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_22
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_23"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_23
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_24"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_24
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_25"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_25
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_26"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_26
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_27"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_27
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_28"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_28
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_29"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_29
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_30"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_30
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_31"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_31
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_32"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_32
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_33"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_33
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_34"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_34
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_35"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_35
)  # type: ignore # mutmut generated
mutants_xǁSecurityHeadersǁget_security_headers__mutmut["xǁSecurityHeadersǁget_security_headers__mutmut_36"] = (
    SecurityHeaders.xǁSecurityHeadersǁget_security_headers__mutmut_36
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_email__mutmut: MutantDict = {}  # type: ignore
mutants_xǁInputValidatorǁvalidate_password__mutmut: MutantDict = {}  # type: ignore
mutants_xǁInputValidatorǁsanitize_input__mutmut: MutantDict = {}  # type: ignore
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut: MutantDict = {}  # type: ignore


class InputValidator:
    """Input validation and sanitization"""

    @staticmethod
    @_mutmut_mutated(mutants_xǁInputValidatorǁvalidate_email__mutmut)
    def validate_email(email: str) -> bool:
        """Validate email format"""
        import re

        pattern = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
        return re.match(pattern, email) is not None

    @staticmethod
    def xǁInputValidatorǁvalidate_email__mutmut_orig(email: str) -> bool:
        """Validate email format"""
        import re

        pattern = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
        return re.match(pattern, email) is not None

    @staticmethod
    def xǁInputValidatorǁvalidate_email__mutmut_1(email: str) -> bool:
        """Validate email format"""
        import re

        pattern = None
        return re.match(pattern, email) is not None

    @staticmethod
    def xǁInputValidatorǁvalidate_email__mutmut_2(email: str) -> bool:
        """Validate email format"""
        import re

        pattern = "XX^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$XX"
        return re.match(pattern, email) is not None

    @staticmethod
    def xǁInputValidatorǁvalidate_email__mutmut_3(email: str) -> bool:
        """Validate email format"""
        import re

        pattern = "^[a-za-z0-9._%+-]+@[a-za-z0-9.-]+\\.[a-za-z]{2,}$"
        return re.match(pattern, email) is not None

    @staticmethod
    def xǁInputValidatorǁvalidate_email__mutmut_4(email: str) -> bool:
        """Validate email format"""
        import re

        pattern = "^[A-ZA-Z0-9._%+-]+@[A-ZA-Z0-9.-]+\\.[A-ZA-Z]{2,}$"
        return re.match(pattern, email) is not None

    @staticmethod
    def xǁInputValidatorǁvalidate_email__mutmut_5(email: str) -> bool:
        """Validate email format"""
        import re

        return re.match(None, email) is not None

    @staticmethod
    def xǁInputValidatorǁvalidate_email__mutmut_6(email: str) -> bool:
        """Validate email format"""
        import re

        pattern = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
        return re.match(pattern, None) is not None

    @staticmethod
    def xǁInputValidatorǁvalidate_email__mutmut_7(email: str) -> bool:
        """Validate email format"""
        import re

        return re.match(email) is not None

    @staticmethod
    def xǁInputValidatorǁvalidate_email__mutmut_8(email: str) -> bool:
        """Validate email format"""
        import re

        pattern = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
        return (
            re.match(
                pattern,
            )
            is not None
        )

    @staticmethod
    def xǁInputValidatorǁvalidate_email__mutmut_9(email: str) -> bool:
        """Validate email format"""
        import re

        pattern = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
        return re.match(pattern, email) is None

    @staticmethod
    @_mutmut_mutated(mutants_xǁInputValidatorǁvalidate_password__mutmut)
    def validate_password(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
    def xǁInputValidatorǁvalidate_password__mutmut_orig(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
    def xǁInputValidatorǁvalidate_password__mutmut_1(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = None
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
    def xǁInputValidatorǁvalidate_password__mutmut_2(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) <= 8:
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
    def xǁInputValidatorǁvalidate_password__mutmut_3(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 9:
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
    def xǁInputValidatorǁvalidate_password__mutmut_4(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append(None)
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
    def xǁInputValidatorǁvalidate_password__mutmut_5(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("XXPassword must be at least 8 characters longXX")
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
    def xǁInputValidatorǁvalidate_password__mutmut_6(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("password must be at least 8 characters long")
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
    def xǁInputValidatorǁvalidate_password__mutmut_7(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("PASSWORD MUST BE AT LEAST 8 CHARACTERS LONG")
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
    def xǁInputValidatorǁvalidate_password__mutmut_8(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_9(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search(None, password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_10(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", None):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_11(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search(password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_12(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search(
            "[A-Z]",
        ):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_13(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("XX[A-Z]XX", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_14(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_15(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append(None)
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_16(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("XXPassword must contain at least one uppercase letterXX")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_17(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_18(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("PASSWORD MUST CONTAIN AT LEAST ONE UPPERCASE LETTER")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_19(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_20(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search(None, password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_21(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", None):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_22(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search(password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_23(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search(
            "[a-z]",
        ):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_24(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("XX[a-z]XX", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_25(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_26(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append(None)
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_27(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("XXPassword must contain at least one lowercase letterXX")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_28(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_29(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("PASSWORD MUST CONTAIN AT LEAST ONE LOWERCASE LETTER")
        if not re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_30(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if re.search("\\d", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_31(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search(None, password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_32(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", None):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_33(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search(password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_34(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search(
            "\\d",
        ):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_35(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("XX\\dXX", password):
            errors.append("Password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_36(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append(None)
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_37(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("XXPassword must contain at least one digitXX")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_38(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("password must contain at least one digit")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_39(password: str) -> dict[str, Any]:
        """Validate password strength"""
        import re

        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        if not re.search("[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        if not re.search("[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        if not re.search("\\d", password):
            errors.append("PASSWORD MUST CONTAIN AT LEAST ONE DIGIT")
        if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_40(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
        if re.search('[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_41(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
        if not re.search(None, password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_42(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
        if not re.search('[!@#$%^&*(),.?":{}|<>]', None):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_43(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
        if not re.search(password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_44(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
        if not re.search(
            '[!@#$%^&*(),.?":{}|<>]',
        ):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_45(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
        if not re.search('XX[!@#$%^&*(),.?":{}|<>]XX', password):
            errors.append("Password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_46(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
            errors.append(None)
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_47(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
            errors.append("XXPassword must contain at least one special characterXX")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_48(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
            errors.append("password must contain at least one special character")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_49(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
            errors.append("PASSWORD MUST CONTAIN AT LEAST ONE SPECIAL CHARACTER")
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_50(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
        return {"XXvalidXX": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_51(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
        return {"VALID": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_52(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
        return {"valid": len(errors) != 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_53(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
        return {"valid": len(errors) == 1, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_54(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
        return {"valid": len(errors) == 0, "XXerrorsXX": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_password__mutmut_55(password: str) -> dict[str, Any]:
        """Validate password strength"""
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
        return {"valid": len(errors) == 0, "ERRORS": errors}

    @staticmethod
    @_mutmut_mutated(mutants_xǁInputValidatorǁsanitize_input__mutmut)
    def sanitize_input(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_orig(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_1(input_string: str) -> str:
        """Sanitize user input"""

        sanitized = None
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_2(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(None)
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_3(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = None
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_4(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["XX<XX", ">", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_5(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", "XX>XX", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_6(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", 'XX"XX', "'", "&", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_7(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "XX'XX", "&", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_8(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "XX&XX", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_9(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "&", "XX\x00XX", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_10(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "XX\nXX", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_11(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "XX\rXX", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_12(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "\r", "XX\tXX"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_13(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for _char in dangerous_chars:
            sanitized = None
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_14(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for _char in dangerous_chars:
            sanitized = sanitized.replace(None, "")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_15(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, None)
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_16(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for _char in dangerous_chars:
            sanitized = sanitized.replace("")
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_17(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(
                char,
            )
        return sanitized.strip()

    @staticmethod
    def xǁInputValidatorǁsanitize_input__mutmut_18(input_string: str) -> str:
        """Sanitize user input"""
        import html

        sanitized = html.escape(input_string)
        dangerous_chars = ["<", ">", '"', "'", "&", "\x00", "\n", "\r", "\t"]
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "XXXX")
        return sanitized.strip()

    @staticmethod
    @_mutmut_mutated(mutants_xǁInputValidatorǁvalidate_json_structure__mutmut)
    def validate_json_structure(data: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
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

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_orig(
        data: dict[str, Any], required_fields: list[str]
    ) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
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

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_1(data: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = None
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

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_2(data: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        for field in required_fields:
            if field in data:
                errors.append(f"Missing required field: {field}")
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = InputValidator.validate_json_structure(
                    value, [f"{field}.{subfield}" for subfield in required_fields if subfield.startswith(f"{field}.")]
                )
                errors.extend(nested_validation["errors"])
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_3(data: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(None)
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = InputValidator.validate_json_structure(
                    value, [f"{field}.{subfield}" for subfield in required_fields if subfield.startswith(f"{field}.")]
                )
                errors.extend(nested_validation["errors"])
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_4(data: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = None
                errors.extend(nested_validation["errors"])
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_5(data: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = InputValidator.validate_json_structure(
                    None, [f"{field}.{subfield}" for subfield in required_fields if subfield.startswith(f"{field}.")]
                )
                errors.extend(nested_validation["errors"])
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_6(data: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = InputValidator.validate_json_structure(value, None)
                errors.extend(nested_validation["errors"])
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_7(data: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = InputValidator.validate_json_structure(
                    [f"{field}.{subfield}" for subfield in required_fields if subfield.startswith(f"{field}.")]
                )
                errors.extend(nested_validation["errors"])
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_8(data: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = InputValidator.validate_json_structure(
                    value,
                )
                errors.extend(nested_validation["errors"])
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_9(data: dict[str, Any], required_fields: list[str]) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = InputValidator.validate_json_structure(
                    value, [f"{field}.{subfield}" for subfield in required_fields if subfield.startswith(None)]
                )
                errors.extend(nested_validation["errors"])
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_10(
        data: dict[str, Any], required_fields: list[str]
    ) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        for field, value in data.items():
            if isinstance(value, dict):
                InputValidator.validate_json_structure(
                    value, [f"{field}.{subfield}" for subfield in required_fields if subfield.startswith(f"{field}.")]
                )
                errors.extend(None)
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_11(
        data: dict[str, Any], required_fields: list[str]
    ) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = InputValidator.validate_json_structure(
                    value, [f"{field}.{subfield}" for subfield in required_fields if subfield.startswith(f"{field}.")]
                )
                errors.extend(nested_validation["XXerrorsXX"])
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_12(
        data: dict[str, Any], required_fields: list[str]
    ) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = InputValidator.validate_json_structure(
                    value, [f"{field}.{subfield}" for subfield in required_fields if subfield.startswith(f"{field}.")]
                )
                errors.extend(nested_validation["ERRORS"])
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_13(
        data: dict[str, Any], required_fields: list[str]
    ) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
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
        return {"XXvalidXX": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_14(
        data: dict[str, Any], required_fields: list[str]
    ) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
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
        return {"VALID": len(errors) == 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_15(
        data: dict[str, Any], required_fields: list[str]
    ) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
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
        return {"valid": len(errors) != 0, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_16(
        data: dict[str, Any], required_fields: list[str]
    ) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
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
        return {"valid": len(errors) == 1, "errors": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_17(
        data: dict[str, Any], required_fields: list[str]
    ) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
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
        return {"valid": len(errors) == 0, "XXerrorsXX": errors}

    @staticmethod
    def xǁInputValidatorǁvalidate_json_structure__mutmut_18(
        data: dict[str, Any], required_fields: list[str]
    ) -> dict[str, Any]:
        """Validate JSON structure and required fields"""
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
        return {"valid": len(errors) == 0, "ERRORS": errors}


mutants_xǁInputValidatorǁvalidate_email__mutmut["_mutmut_orig"] = InputValidator.xǁInputValidatorǁvalidate_email__mutmut_orig  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_email__mutmut["xǁInputValidatorǁvalidate_email__mutmut_1"] = (
    InputValidator.xǁInputValidatorǁvalidate_email__mutmut_1
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_email__mutmut["xǁInputValidatorǁvalidate_email__mutmut_2"] = (
    InputValidator.xǁInputValidatorǁvalidate_email__mutmut_2
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_email__mutmut["xǁInputValidatorǁvalidate_email__mutmut_3"] = (
    InputValidator.xǁInputValidatorǁvalidate_email__mutmut_3
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_email__mutmut["xǁInputValidatorǁvalidate_email__mutmut_4"] = (
    InputValidator.xǁInputValidatorǁvalidate_email__mutmut_4
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_email__mutmut["xǁInputValidatorǁvalidate_email__mutmut_5"] = (
    InputValidator.xǁInputValidatorǁvalidate_email__mutmut_5
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_email__mutmut["xǁInputValidatorǁvalidate_email__mutmut_6"] = (
    InputValidator.xǁInputValidatorǁvalidate_email__mutmut_6
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_email__mutmut["xǁInputValidatorǁvalidate_email__mutmut_7"] = (
    InputValidator.xǁInputValidatorǁvalidate_email__mutmut_7
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_email__mutmut["xǁInputValidatorǁvalidate_email__mutmut_8"] = (
    InputValidator.xǁInputValidatorǁvalidate_email__mutmut_8
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_email__mutmut["xǁInputValidatorǁvalidate_email__mutmut_9"] = (
    InputValidator.xǁInputValidatorǁvalidate_email__mutmut_9
)  # type: ignore # mutmut generated

mutants_xǁInputValidatorǁvalidate_password__mutmut["_mutmut_orig"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_orig
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_1"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_1
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_2"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_2
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_3"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_3
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_4"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_4
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_5"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_5
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_6"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_6
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_7"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_7
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_8"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_8
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_9"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_9
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_10"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_10
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_11"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_11
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_12"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_12
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_13"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_13
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_14"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_14
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_15"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_15
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_16"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_16
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_17"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_17
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_18"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_18
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_19"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_19
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_20"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_20
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_21"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_21
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_22"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_22
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_23"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_23
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_24"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_24
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_25"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_25
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_26"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_26
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_27"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_27
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_28"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_28
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_29"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_29
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_30"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_30
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_31"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_31
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_32"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_32
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_33"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_33
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_34"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_34
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_35"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_35
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_36"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_36
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_37"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_37
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_38"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_38
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_39"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_39
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_40"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_40
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_41"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_41
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_42"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_42
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_43"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_43
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_44"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_44
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_45"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_45
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_46"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_46
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_47"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_47
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_48"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_48
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_49"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_49
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_50"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_50
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_51"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_51
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_52"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_52
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_53"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_53
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_54"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_54
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_password__mutmut["xǁInputValidatorǁvalidate_password__mutmut_55"] = (
    InputValidator.xǁInputValidatorǁvalidate_password__mutmut_55
)  # type: ignore # mutmut generated

mutants_xǁInputValidatorǁsanitize_input__mutmut["_mutmut_orig"] = InputValidator.xǁInputValidatorǁsanitize_input__mutmut_orig  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_1"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_1
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_2"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_2
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_3"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_3
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_4"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_4
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_5"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_5
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_6"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_6
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_7"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_7
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_8"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_8
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_9"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_9
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_10"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_10
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_11"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_11
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_12"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_12
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_13"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_13
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_14"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_14
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_15"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_15
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_16"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_16
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_17"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_17
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁsanitize_input__mutmut["xǁInputValidatorǁsanitize_input__mutmut_18"] = (
    InputValidator.xǁInputValidatorǁsanitize_input__mutmut_18
)  # type: ignore # mutmut generated

mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["_mutmut_orig"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_orig
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_1"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_1
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_2"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_2
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_3"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_3
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_4"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_4
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_5"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_5
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_6"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_6
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_7"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_7
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_8"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_8
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_9"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_9
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_10"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_10
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_11"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_11
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_12"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_12
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_13"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_13
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_14"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_14
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_15"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_15
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_16"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_16
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_17"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_17
)  # type: ignore # mutmut generated
mutants_xǁInputValidatorǁvalidate_json_structure__mutmut["xǁInputValidatorǁvalidate_json_structure__mutmut_18"] = (
    InputValidator.xǁInputValidatorǁvalidate_json_structure__mutmut_18
)  # type: ignore # mutmut generated


security_headers = SecurityHeaders()
input_validator = InputValidator()
