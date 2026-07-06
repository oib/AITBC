"""
JWT Authentication Handler for AITBC Agent Coordinator.

.. deprecated::
    This module is a backward-compatibility shim. The canonical implementation
    lives in ``aitbc.auth.jwt`` and ``aitbc.auth.password`` and
    ``aitbc.auth.api_key``. Import from ``aitbc.auth`` directly in new code.
"""

import os
import warnings

from aitbc.auth.api_key import APIKeyManager
from aitbc.auth.jwt import JWTHandler
from aitbc.auth.password import PasswordManager

warnings.warn(
    "app.auth.jwt_handler is deprecated; import from aitbc.auth instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Global instances (preserve original initialization behavior)
jwt_secret = os.getenv("JWT_SECRET")
if not jwt_secret:
    jwt_secret = "test_secret_key_for_development_only_change_in_production"
jwt_handler = JWTHandler(jwt_secret)
password_manager = PasswordManager()
api_key_manager = APIKeyManager()

__all__ = [
    "APIKeyManager",
    "JWTHandler",
    "PasswordManager",
    "api_key_manager",
    "jwt_handler",
    "password_manager",
]
