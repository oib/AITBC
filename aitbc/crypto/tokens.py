"""
Token and API key management utilities
"""

import secrets
import time
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


def generate_token(length: int = 32, prefix: str = "") -> str:
    """Generate a secure random token"""
    token = secrets.token_urlsafe(length)
    return f"{prefix}{token}" if prefix else token


def generate_api_key(prefix: str = "aitbc") -> str:
    """Generate a secure API key with prefix"""
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}_{random_part}"


def validate_token_format(token: str, min_length: int = 16) -> bool:
    """Validate token format"""
    return bool(token) and len(token) >= min_length and all(c.isalnum() or c in "-_" for c in token)


def validate_api_key(api_key: str, prefix: str = "aitbc") -> bool:
    """Validate API key format"""
    if not api_key or not api_key.startswith(f"{prefix}_"):
        return False
    token_part = api_key[len(prefix) + 1 :]
    return validate_token_format(token_part)


class SessionManager:
    """Simple in-memory session manager"""

    def __init__(self, session_timeout: int = 3600):
        """Initialize session manager with timeout in seconds"""
        self.sessions: dict[str, dict[str, Any]] = {}
        self.session_timeout = session_timeout

    def create_session(self, user_id: str, data: dict[str, Any] | None = None) -> str:
        """Create a new session"""
        session_id = generate_token()
        self.sessions[session_id] = {
            "user_id": user_id,
            "data": data or {},
            "created_at": time.time(),
            "expires_at": time.time() + self.session_timeout,
        }
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session data"""
        session = self.sessions.get(session_id)
        if not session:
            return None

        # Check if session expired
        if time.time() > session["expires_at"]:
            del self.sessions[session_id]
            return None

        return session

    def update_session(self, session_id: str, data: dict[str, Any]) -> bool:
        """Update session data"""
        session = self.get_session(session_id)
        if not session:
            return False

        session["data"].update(data)
        return True

    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions"""
        current_time = time.time()
        expired_keys = [key for key, session in self.sessions.items() if current_time > session["expires_at"]]

        for key in expired_keys:
            del self.sessions[key]

        return len(expired_keys)
