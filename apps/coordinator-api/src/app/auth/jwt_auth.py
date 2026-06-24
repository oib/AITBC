"""
JWT-based authentication module for Coordinator API
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, jwt

from ..config import settings


class JWTAuth:
    """JWT authentication handler"""

    def __init__(self):
        self.secret = settings.jwt_secret
        self.algorithm = settings.jwt_algorithm
        self.expiration_hours = settings.jwt_expiration_hours

    def create_token(self, payload: dict[str, Any]) -> str:
        """
        Create JWT token with expiration

        Args:
            payload: Claims to include in token

        Returns:
            Encoded JWT token string
        """
        expire = datetime.now(UTC) + timedelta(hours=self.expiration_hours)
        to_encode = payload.copy()
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self.secret, algorithm=self.algorithm)

    def decode_token(self, token: str) -> dict[str, Any]:
        """
        Decode and validate JWT token

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid
        """
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            return payload
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e

    def verify_token(self, token: str, required_role: str | None = None) -> dict[str, Any]:
        """
        Verify token and optionally check role

        Args:
            token: JWT token string
            required_role: Required role (optional)

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid or role doesn't match
        """
        payload = self.decode_token(token)
        if required_role and payload.get("role") != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required",
            )
        return payload


# Global JWT auth instance
jwt_auth = JWTAuth()


def create_access_token(user_id: str, role: str, extra_claims: dict[str, Any] | None = None) -> str:
    """
    Create access token for user

    Args:
        user_id: User identifier
        role: User role (admin, client, miner)
        extra_claims: Additional claims to include

    Returns:
        Encoded JWT token string
    """
    payload = {"sub": user_id, "role": role}
    if extra_claims:
        payload.update(extra_claims)
    return jwt_auth.create_token(payload)


def verify_access_token(token: str, required_role: str | None = None) -> dict[str, Any]:
    """
    Verify access token and return payload

    Args:
        token: JWT token string
        required_role: Required role (optional)

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is invalid or role doesn't match
    """
    return jwt_auth.verify_token(token, required_role)
