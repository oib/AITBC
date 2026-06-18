"""
Token and API key management utilities
"""

import json
import os
import secrets
import time
from datetime import UTC, datetime
from typing import Any


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


class APIKeyManager:
    """API key management with storage"""

    def __init__(self, storage_path: str | None = None):
        """Initialize API key manager"""
        self.storage_path = storage_path
        self.keys: dict[str, dict[str, Any]] = {}

        if storage_path:
            self._load_keys()

    def create_api_key(self, user_id: str, scopes: list[str] | None = None, name: str | None = None) -> str:
        """Create a new API key"""
        api_key = generate_api_key()
        self.keys[api_key] = {
            "user_id": user_id,
            "scopes": scopes or ["read"],
            "name": name,
            "created_at": datetime.now(UTC).isoformat(),
            "last_used": None,
        }

        if self.storage_path:
            self._save_keys()

        return api_key

    def validate_api_key(self, api_key: str) -> dict[str, Any] | None:
        """Validate API key and return key data"""
        key_data = self.keys.get(api_key)
        if not key_data:
            return None

        # Update last used
        key_data["last_used"] = datetime.now(UTC).isoformat()
        if self.storage_path:
            self._save_keys()

        return key_data

    def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key"""
        if api_key in self.keys:
            del self.keys[api_key]
            if self.storage_path:
                self._save_keys()
            return True
        return False

    def list_user_keys(self, user_id: str) -> list[str]:
        """List all API keys for a user"""
        return [key for key, data in self.items() if data["user_id"] == user_id]

    def _load_keys(self):
        """Load keys from storage"""
        if self.storage_path and os.path.exists(self.storage_path):
            try:
                with open(self.storage_path) as f:
                    self.keys = json.load(f)
            except Exception:
                self.keys = {}

    def _save_keys(self):
        """Save keys to storage"""
        if self.storage_path:
            try:
                with open(self.storage_path, "w") as f:
                    json.dump(self.keys, f)
            except Exception:
                pass

    def items(self):
        """Return key items"""
        return self.keys.items()
