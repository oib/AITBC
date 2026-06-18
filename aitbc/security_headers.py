"""
Security headers and CORS utilities for AITBC web services
Provides security headers and CORS policies configuration
"""

from dataclasses import dataclass

from .aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass
class SecurityHeaders:
    """Security headers configuration"""

    X_Content_Type_Options: str = "nosniff"
    X_Frame_Options: str = "DENY"
    X_XSS_Protection: str = "1; mode=block"
    Strict_Transport_Security: str = "max-age=31536000; includeSubDomains"
    Content_Security_Policy: str = "default-src 'self'"
    Referrer_Policy: str = "strict-origin-when-cross-origin"
    Permissions_Policy: str = ""
    Cache_Control: str = "no-cache, no-store, must-revalidate"
    Pragma: str = "no-cache"


@dataclass
class CORSConfig:
    """CORS configuration"""

    allow_origins: list[str]
    allow_methods: list[str]
    allow_headers: list[str]
    allow_credentials: bool = False
    expose_headers: list[str] = None
    max_age: int = 3600


class SecurityHeadersMiddleware:
    """
    Security headers middleware for web services.
    Adds security headers to HTTP responses.
    """

    def __init__(self, headers: SecurityHeaders | None = None):
        """
        Initialize security headers middleware

        Args:
            headers: Security headers configuration
        """
        self.headers = headers or SecurityHeaders()

    def get_headers(self) -> dict[str, str]:
        """
        Get security headers dictionary

        Returns:
            Dictionary of security headers
        """
        return {
            "X-Content-Type-Options": self.headers.X_Content_Type_Options,
            "X-Frame-Options": self.headers.X_Frame_Options,
            "X-XSS-Protection": self.headers.X_XSS_Protection,
            "Strict-Transport-Security": self.headers.Strict_Transport_Security,
            "Content-Security-Policy": self.headers.Content_Security_Policy,
            "Referrer-Policy": self.headers.Referrer_Policy,
            "Permissions-Policy": self.headers.Permissions_Policy,
            "Cache-Control": self.headers.Cache_Control,
            "Pragma": self.headers.Pragma,
        }

    def apply_to_response(self, response_headers: dict[str, str]) -> dict[str, str]:
        """
        Apply security headers to response

        Args:
            response_headers: Existing response headers

        Returns:
            Response headers with security headers added
        """
        security_headers = self.get_headers()
        response_headers.update(security_headers)
        return response_headers

    async def __call__(self, request, call_next):
        """
        ASGI middleware entry point

        Args:
            request: ASGI request
            call_next: Next middleware or route handler

        Returns:
            Response with security headers
        """
        response = await call_next(request)
        if self.headers:
            security_headers = self.get_headers()
            for key, value in security_headers.items():
                response.headers[key] = value
        return response


class CORSMiddleware:
    """
    CORS middleware for web services.
    Handles Cross-Origin Resource Sharing policies.
    """

    def __init__(self, config: CORSConfig):
        """
        Initialize CORS middleware

        Args:
            config: CORS configuration
        """
        self.config = config

    def get_cors_headers(self, origin: str) -> dict[str, str]:
        """
        Get CORS headers for a request

        Args:
            origin: Request origin

        Returns:
            Dictionary of CORS headers
        """
        headers = {}

        # Check if origin is allowed
        if self._is_origin_allowed(origin):
            headers["Access-Control-Allow-Origin"] = origin

            if self.config.allow_credentials:
                headers["Access-Control-Allow-Credentials"] = "true"

            headers["Access-Control-Allow-Methods"] = ", ".join(self.config.allow_methods)
            headers["Access-Control-Allow-Headers"] = ", ".join(self.config.allow_headers)

            if self.config.expose_headers:
                headers["Access-Control-Expose-Headers"] = ", ".join(self.config.expose_headers)

            headers["Access-Control-Max-Age"] = str(self.config.max_age)

        return headers

    def _is_origin_allowed(self, origin: str) -> bool:
        """
        Check if origin is allowed based on CORS policy

        Args:
            origin: Request origin

        Returns:
            True if origin is allowed, False otherwise
        """
        if "*" in self.config.allow_origins:
            return True

        return origin in self.config.allow_origins

    def is_preflight_request(self, method: str) -> bool:
        """
        Check if request is a CORS preflight request

        Args:
            method: HTTP method

        Returns:
            True if preflight request, False otherwise
        """
        return method.upper() == "OPTIONS"


def create_production_security_headers() -> SecurityHeaders:
    """
    Create security headers configuration for production

    Returns:
        SecurityHeaders configured for production
    """
    return SecurityHeaders(
        X_Content_Type_Options="nosniff",
        X_Frame_Options="DENY",
        X_XSS_Protection="1; mode=block",
        Strict_Transport_Security="max-age=31536000; includeSubDomains; preload",
        Content_Security_Policy="default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'",
        Referrer_Policy="strict-origin-when-cross-origin",
        Permissions_Policy="geolocation=(), microphone=(), camera=()",
        Cache_Control="no-cache, no-store, must-revalidate",
        Pragma="no-cache",
    )


def create_development_security_headers() -> SecurityHeaders:
    """
    Create security headers configuration for development

    Returns:
        SecurityHeaders configured for development
    """
    return SecurityHeaders(
        X_Content_Type_Options="nosniff",
        X_Frame_Options="SAMEORIGIN",
        X_XSS_Protection="1; mode=block",
        Strict_Transport_Security="max-age=3600",
        Content_Security_Policy="default-src 'self' 'unsafe-inline' 'unsafe-eval'",
        Referrer_Policy="strict-origin-when-cross-origin",
        Permissions_Policy="",
        Cache_Control="no-cache",
        Pragma="no-cache",
    )


def create_strict_cors_config(allowed_origins: list[str]) -> CORSConfig:
    """
    Create strict CORS configuration

    Args:
        allowed_origins: List of allowed origins

    Returns:
        CORSConfig with strict settings
    """
    return CORSConfig(
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
        allow_credentials=True,
        expose_headers=["X-Request-ID"],
        max_age=3600,
    )


def create_permissive_cors_config() -> CORSConfig:
    """
    Create permissive CORS configuration (for development)

    Returns:
        CORSConfig with permissive settings
    """
    return CORSConfig(
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=False,
        expose_headers=["*"],
        max_age=86400,
    )
