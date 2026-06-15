"""Security utilities for API protection."""

import hashlib
import hmac
import logging
import os
import re
from datetime import datetime

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


class InputValidator:
    """Input validation and sanitization utilities."""

    SQL_INJECTION_PATTERNS = [
        "(\\bunion\\b.*\\bselect\\b)",
        "(\\bselect\\b.*\\bfrom\\b)",
        "(\\binsert\\b.*\\binto\\b)",
        "(\\bdelete\\b.*\\bfrom\\b)",
        "(\\bdrop\\b.*\\btable\\b)",
        "(\\bexec\\b|\\bexecute\\b)",
        "(--|;|\\/\\*|\\*\\/)",
        "(\\bor\\b.*=.*\\bor\\b)",
        "(\\band\\b.*=.*\\band\\b)",
    ]
    XSS_PATTERNS = [
        "<script[^>]*>.*?</script>",
        "javascript:",
        "on\\w+\\s*=",
        "<iframe[^>]*>.*?</iframe>",
        "<object[^>]*>.*?</object>",
        "<embed[^>]*>.*?</embed>",
    ]

    @classmethod
    def validate_string(cls, value: str, max_length: int = 1000) -> str:
        """Validate and sanitize string input."""
        if not isinstance(value, str):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid string input")
        if len(value) > max_length:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"String exceeds maximum length of {max_length}"
            )
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning("SQL injection attempt detected: %s", value[:100])
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input detected")
        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning("XSS attempt detected: %s", value[:100])
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input detected")
        return value

    @classmethod
    def validate_email(cls, email: str) -> str:
        """Validate email format."""
        email_pattern = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, email):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")
        return email

    @classmethod
    def validate_wallet_address(cls, address: str) -> str:
        """Validate blockchain wallet address format."""
        if not address or len(address) < 10 or len(address) > 100:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid wallet address format")
        return address

    @classmethod
    def validate_numeric_range(cls, value: float, min_val: float, max_val: float) -> float:
        """Validate numeric value is within range."""
        if not isinstance(value, (int, float)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid numeric input")
        if value < min_val or value > max_val:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Value must be between {min_val} and {max_val}"
            )
        return value


class RequestSigner:
    """Request signing for sensitive operations."""

    @staticmethod
    def sign_request(method: str, path: str, body: str, secret: str, timestamp: str) -> str:
        """Generate HMAC signature for request."""
        message = f"{method}\n{path}\n{body}\n{timestamp}"
        signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        return signature

    @staticmethod
    def verify_signature(method: str, path: str, body: str, secret: str, timestamp: str, signature: str) -> bool:
        """Verify HMAC signature."""
        expected = RequestSigner.sign_request(method, path, body, secret, timestamp)
        return hmac.compare_digest(expected, signature)


class APIKeyRotator:
    """API key rotation management."""

    @staticmethod
    def generate_api_key() -> str:
        """Generate a new API key."""
        return hashlib.sha256(f"{datetime.utcnow().isoformat()}_{os.urandom(32).hex()}".encode()).hexdigest()

    @staticmethod
    def validate_api_key_format(api_key: str) -> bool:
        """Validate API key format."""
        return len(api_key) == 64 and all(c in "0123456789abcdef" for c in api_key.lower())


async def verify_api_key(request: Request, credentials: HTTPAuthorizationCredentials | None = None) -> str:
    """Verify API key from request."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required", headers={"WWW-Authenticate": "Bearer"}
        )
    api_key = credentials.credentials
    if not APIKeyRotator.validate_api_key_format(api_key):
        client_host = request.client.host if request.client else "unknown"
        logger.warning("Invalid API key format from %s", client_host)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key format")
    from ..config import settings

    all_allowed_keys = settings.client_api_keys + settings.miner_api_keys + settings.admin_api_keys
    if api_key not in all_allowed_keys:
        client_host = request.client.host if request.client else "unknown"
        logger.warning("Invalid API key from %s", client_host)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return api_key


def get_client_ip(request: Request) -> str:
    """Get client IP address, accounting for proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
