"""
API key generation and management with persistent storage.

Extracted from ``apps/agent-coordinator/src/app/auth/jwt_handler.py::APIKeyManager``.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class APIKeyManager:
    """API key generation and management with persistent storage.

    Keys are stored in a JSON file (default: ``/var/lib/aitbc/api_keys.json``)
    with ``0600`` permissions. Each key maps to a dict with user_id,
    permissions, created_at, last_used, and usage_count.
    """

    def __init__(self, storage_path: str | None = None) -> None:
        self.storage_path: str = (
            storage_path or os.getenv("API_KEY_STORAGE_PATH", "/var/lib/aitbc/api_keys.json") or "/var/lib/aitbc/api_keys.json"
        )
        self.api_keys: dict[str, Any] = self._load_keys()

    def _load_keys(self) -> dict[str, Any]:
        """Load API keys from persistent storage."""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path) as f:
                    data: dict[str, Any] = json.load(f)
                    return data
            return {}
        except Exception as e:
            logger.error("Error loading API keys: %s", e)
            return {}

    def _save_keys(self) -> None:
        """Save API keys to persistent storage."""
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w") as f:
                json.dump(self.api_keys, f, indent=2)
            os.chmod(self.storage_path, 384)  # 0600
        except Exception as e:
            logger.error("Error saving API keys: %s", e)

    def generate_api_key(self, user_id: str, permissions: list[str] | None = None) -> dict[str, Any]:
        """Generate new API key for user.

        Returns:
            ``{"status": "success", "api_key": ..., "permissions": ..., "created_at": ...}``
            or ``{"status": "error", "message": ...}``
        """
        try:
            api_key = secrets.token_urlsafe(32)
            key_data: dict[str, Any] = {
                "user_id": user_id,
                "permissions": permissions or [],
                "created_at": datetime.now(UTC).isoformat(),
                "last_used": None,
                "usage_count": 0,
            }
            self.api_keys[api_key] = key_data
            self._save_keys()
            return {
                "status": "success",
                "api_key": api_key,
                "permissions": permissions or [],
                "created_at": key_data["created_at"],
            }
        except Exception as e:
            logger.error("Error generating API key: %s", e)
            return {"status": "error", "message": str(e)}

    def validate_api_key(self, api_key: str) -> dict[str, Any]:
        """Validate API key and return user info.

        Returns:
            ``{"status": "success", "valid": True, "user_id": ..., "permissions": ...}``
            or ``{"status": "error", "valid": False, "message": ...}``
        """
        try:
            if api_key not in self.api_keys:
                return {"status": "error", "valid": False, "message": "Invalid API key"}
            key_data = self.api_keys[api_key]
            key_data["last_used"] = datetime.now(UTC).isoformat()
            key_data["usage_count"] += 1
            self._save_keys()
            return {
                "status": "success",
                "valid": True,
                "user_id": key_data["user_id"],
                "permissions": key_data["permissions"],
            }
        except Exception as e:
            logger.error("Error validating API key: %s", e)
            return {"status": "error", "message": str(e)}

    def revoke_api_key(self, api_key: str) -> dict[str, Any]:
        """Revoke API key.

        Returns:
            ``{"status": "success", "message": ...}``
            or ``{"status": "error", "message": ...}``
        """
        try:
            if api_key in self.api_keys:
                del self.api_keys[api_key]
                self._save_keys()
                return {"status": "success", "message": "API key revoked"}
            else:
                return {"status": "error", "message": "API key not found"}
        except Exception as e:
            logger.error("Error revoking API key: %s", e)
            return {"status": "error", "message": str(e)}


# Global instance (agent-coordinator compatibility)
api_key_manager = APIKeyManager()


__all__ = ["APIKeyManager", "api_key_manager"]
