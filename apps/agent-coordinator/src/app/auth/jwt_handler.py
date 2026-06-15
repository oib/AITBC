"""
JWT Authentication Handler for AITBC Agent Coordinator
Implements JWT token generation, validation, and management
"""

import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from dotenv import load_dotenv

from aitbc import get_logger

load_dotenv()
logger = get_logger(__name__)


class JWTHandler:
    """JWT token management and validation"""

    def __init__(self, secret_key: str | None = None) -> None:
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.algorithm = "HS256"
        self.token_expiry = timedelta(hours=24)
        self.refresh_expiry = timedelta(days=7)

    def generate_token(self, payload: dict[str, Any], expires_delta: timedelta | None = None) -> dict[str, Any]:
        """Generate JWT token with specified payload"""
        import jwt

        try:
            if expires_delta:
                expire = datetime.now(UTC) + expires_delta
            else:
                expire = datetime.now(UTC) + self.token_expiry
            token_payload = {**payload, "exp": expire, "iat": datetime.now(UTC), "type": "access"}
            token = jwt.encode(token_payload, self.secret_key, algorithm=self.algorithm)
            return {"status": "success", "token": token, "expires_at": expire.isoformat(), "token_type": "Bearer"}
        except Exception as e:
            logger.error("Error generating JWT token: %s", e)
            return {"status": "error", "message": str(e)}

    def generate_refresh_token(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Generate refresh token for token renewal"""
        import jwt

        try:
            expire = datetime.now(UTC) + self.refresh_expiry
            token_payload = {**payload, "exp": expire, "iat": datetime.now(UTC), "type": "refresh"}
            token = jwt.encode(token_payload, self.secret_key, algorithm=self.algorithm)
            return {"status": "success", "refresh_token": token, "expires_at": expire.isoformat()}
        except Exception as e:
            logger.error("Error generating refresh token: %s", e)
            return {"status": "error", "message": str(e)}

    def validate_token(self, token: str) -> dict[str, Any]:
        """Validate JWT token and return payload"""
        import jwt

        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm], options={"verify_exp": True})
            return {"status": "success", "valid": True, "payload": payload}
        except jwt.ExpiredSignatureError:
            return {"status": "error", "valid": False, "message": "Token has expired"}
        except jwt.InvalidTokenError as e:
            return {"status": "error", "valid": False, "message": f"Invalid token: {str(e)}"}
        except Exception as e:
            logger.error("Error validating token: %s", e)
            return {"status": "error", "valid": False, "message": f"Token validation error: {str(e)}"}

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Generate new access token from refresh token"""
        try:
            validation = self.validate_token(refresh_token)
            if not validation["valid"] or validation["payload"].get("type") != "refresh":
                return {"status": "error", "message": "Invalid or expired refresh token"}
            payload = validation["payload"]
            user_payload = {
                "user_id": payload.get("user_id"),
                "username": payload.get("username"),
                "role": payload.get("role"),
                "permissions": payload.get("permissions", []),
            }
            return self.generate_token(user_payload)
        except Exception as e:
            logger.error("Error refreshing token: %s", e)
            return {"status": "error", "message": str(e)}

    def decode_token_without_validation(self, token: str) -> dict[str, Any]:
        """Decode token without expiration validation (for debugging)"""
        import jwt

        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm], options={"verify_exp": False})
            return {"status": "success", "payload": payload}
        except Exception as e:
            return {"status": "error", "message": f"Error decoding token: {str(e)}"}


class PasswordManager:
    """Password hashing and verification using bcrypt"""

    @staticmethod
    def hash_password(password: str) -> dict[str, Any]:
        """Hash password using bcrypt"""
        import bcrypt  # type: ignore

        try:
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
            return {"status": "success", "hashed_password": hashed.decode("utf-8"), "salt": salt.decode("utf-8")}
        except Exception as e:
            logger.error("Error hashing password: %s", e)
            return {"status": "error", "message": str(e)}

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> dict[str, Any]:
        """Verify password against hash"""
        try:
            import bcrypt

            hashed_bytes = hashed_password.encode("utf-8")
            password_bytes = password.encode("utf-8")
            is_valid = bcrypt.checkpw(password_bytes, hashed_bytes)
            return {"status": "success", "valid": is_valid}
        except Exception as e:
            logger.error("Error verifying password: %s", e)
            return {"status": "error", "message": str(e)}


class APIKeyManager:
    """API key generation and management with persistent storage"""

    def __init__(self, storage_path: str | None = None) -> None:
        self.storage_path: str = (
            storage_path or os.getenv("API_KEY_STORAGE_PATH", "/var/lib/aitbc/api_keys.json") or "/var/lib/aitbc/api_keys.json"
        )
        self.api_keys = self._load_keys()

    def _load_keys(self) -> dict[str, Any]:
        """Load API keys from persistent storage"""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path) as f:
                    import json

                    data: dict[str, Any] = json.load(f)
                    return data
            return {}
        except Exception as e:
            logger.error("Error loading API keys: %s", e)
            return {}

    def _save_keys(self) -> None:
        """Save API keys to persistent storage"""
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w") as f:
                import json

                json.dump(self.api_keys, f, indent=2)
            os.chmod(self.storage_path, 384)
        except Exception as e:
            logger.error("Error saving API keys: %s", e)

    def generate_api_key(self, user_id: str, permissions: list[str] | None = None) -> dict[str, Any]:
        """Generate new API key for user"""
        try:
            api_key = secrets.token_urlsafe(32)
            key_data = {
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
        """Validate API key and return user info"""
        try:
            if api_key not in self.api_keys:
                return {"status": "error", "valid": False, "message": "Invalid API key"}
            key_data = self.api_keys[api_key]
            key_data["last_used"] = datetime.now(UTC).isoformat()
            key_data["usage_count"] += 1
            self._save_keys()
            return {"status": "success", "valid": True, "user_id": key_data["user_id"], "permissions": key_data["permissions"]}
        except Exception as e:
            logger.error("Error validating API key: %s", e)
            return {"status": "error", "message": str(e)}

    def revoke_api_key(self, api_key: str) -> dict[str, Any]:
        """Revoke API key"""
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


# Global instances
jwt_secret = os.getenv("JWT_SECRET")
if not jwt_secret:
    jwt_secret = "test_secret_key_for_development_only_change_in_production"
jwt_handler = JWTHandler(jwt_secret)
password_manager = PasswordManager()
api_key_manager = APIKeyManager()
