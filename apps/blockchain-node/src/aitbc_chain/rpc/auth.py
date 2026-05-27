"""
Authentication utilities for blockchain RPC endpoints.
"""

import os
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from ..logger import get_logger

_logger = get_logger(__name__)


def get_authenticated_address(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = None) -> str:
    """
    Extract authenticated wallet address from request headers or JWT token.

    Priority order:
    1. X-Wallet-Address header (for API key auth)
    2. JWT Bearer token (if provided)
    3. Development mode fallback (if DEV_MODE=true)

    Returns:
        str: The authenticated wallet address

    Raises:
        HTTPException: If authentication fails and not in development mode
    """
    # Check for X-Wallet-Address header (API key authentication)
    wallet_address = request.headers.get("X-Wallet-Address")
    if wallet_address:
        if not wallet_address.startswith("0x") or len(wallet_address) != 42:
            _logger.warning(f"Invalid wallet address format in X-Wallet-Address header: {wallet_address}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid wallet address format"
            )
        if os.getenv("TRUST_X_WALLET_ADDRESS", "false").lower() != "true":
            _logger.warning("Rejected untrusted X-Wallet-Address header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-Wallet-Address header is not trusted without explicit server configuration"
            )
        _logger.debug(f"Authenticated via X-Wallet-Address header: {wallet_address}")
        return wallet_address

    # Check for JWT Bearer token
    if credentials and credentials.scheme == "Bearer":
        _logger.warning("JWT authentication attempted but not supported")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT authentication is not supported. Use X-Wallet-Address header with TRUST_X_WALLET_ADDRESS=true for trusted internal requests."
        )

    # Development mode fallback - remove zero-address fallback for security
    if os.getenv("DEV_MODE", "false").lower() == "true":
        _logger.warning("Development mode enabled but authentication still required")
        # Still require authentication even in dev mode for security

    # No valid authentication found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide X-Wallet-Address header with TRUST_X_WALLET_ADDRESS=true for trusted internal requests.",
        headers={"WWW-Authenticate": "Bearer"}
    )
