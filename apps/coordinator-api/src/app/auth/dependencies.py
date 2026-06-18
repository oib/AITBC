"""
Role-based authentication dependencies
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from .jwt_auth import verify_access_token


def get_token(authorization: str | None = Header(default=None, alias="Authorization")) -> str:
    """
    Extract Bearer token from Authorization header

    Args:
        authorization: Authorization header value

    Returns:
        Token string

    Raises:
        HTTPException: If header is missing or malformed
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization[7:]  # Remove "Bearer " prefix


def require_auth() -> dict[str, any]:
    """
    Require valid JWT token (any role)

    Returns:
        Token payload

    Raises:
        HTTPException: If token is invalid
    """
    token = get_token()
    return verify_access_token(token)


def require_admin() -> dict[str, any]:
    """
    Require admin role

    Returns:
        Token payload

    Raises:
        HTTPException: If token is invalid or role is not admin
    """
    token = get_token()
    return verify_access_token(token, required_role="admin")


def require_client() -> dict[str, any]:
    """
    Require client role

    Returns:
        Token payload

    Raises:
        HTTPException: If token is invalid or role is not client
    """
    token = get_token()
    return verify_access_token(token, required_role="client")


def require_miner() -> dict[str, any]:
    """
    Require miner role

    Returns:
        Token payload

    Raises:
        HTTPException: If token is invalid or role is not miner
    """
    token = get_token()
    return verify_access_token(token, required_role="miner")


# Type aliases for dependency injection
AuthDep = Annotated[dict[str, any], Depends(require_auth)]
AdminDep = Annotated[dict[str, any], Depends(require_admin)]
ClientDep = Annotated[dict[str, any], Depends(require_client)]
MinerDep = Annotated[dict[str, any], Depends(require_miner)]
