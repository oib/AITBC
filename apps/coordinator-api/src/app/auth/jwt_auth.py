"""
JWT-based authentication module for Coordinator API.

.. deprecated::
    This module is a backward-compatibility shim. The canonical implementation
    lives in ``aitbc.auth.jwt``. Import from ``aitbc.auth`` directly in new code.
"""

import warnings

from aitbc.auth.jwt import JWTAuth as _JWTAuth

from ..config import settings

warnings.warn(
    "app.auth.jwt_auth is deprecated; import from aitbc.auth instead.",
    DeprecationWarning,
    stacklevel=2,
)


class JWTAuth(_JWTAuth):
    """JWT authentication handler — delegates to aitbc.auth.jwt.JWTAuth."""

    def __init__(self) -> None:
        super().__init__(
            secret=settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
            expiration_hours=settings.jwt_expiration_hours,
        )


# Global JWT auth instance
jwt_auth = JWTAuth()


def create_access_token(user_id: str, role: str, extra_claims: dict | None = None) -> str:
    """Create access token for user."""
    payload = {"sub": user_id, "role": role}
    if extra_claims:
        payload.update(extra_claims)
    return jwt_auth.create_token(payload)


def verify_access_token(token: str, required_role: str | None = None) -> dict:
    """Verify access token and return payload."""
    return jwt_auth.verify_token(token, required_role)
