"""Wallet-based authentication routes for the coordinator API.

Provides /v1/auth/nonce and /v1/login so the CLI ``aitbc auth login`` can
obtain a client JWT by signing a nonce with a wallet's private key.
"""
from __future__ import annotations

import secrets
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import SignatureMalformed, canonical_address, verify_signature
from aitbc.rate_limiting import rate_limit
from eth_account.messages import defunct_hash_message

from ....auth import create_access_token

logger = get_logger(__name__)
router = APIRouter(tags=["authentication"])

# In-memory nonce store: wallet_address -> (nonce, created_at).
# Single uvicorn worker on the live coordinator node, so this is sufficient.
# Nonces expire after 5 minutes and are single-use.
_auth_nonces: dict[str, tuple[str, float]] = {}
_NONCE_TTL_SECONDS = 300


def _build_sign_message(wallet_address: str, nonce: str) -> str:
    """Canonical message the CLI signs for /v1/login."""
    return f"Sign this message to log in to AITBC.\nWallet: {wallet_address.lower()}\nNonce: {nonce}"


@router.post("/auth/nonce", response_model=dict, summary="Request an authentication nonce")
@rate_limit(rate=20, per=60)
async def auth_nonce(request: Request, data: dict[str, Any]) -> dict[str, Any]:
    """Return a fresh nonce that the caller must sign to log in."""
    wallet_address = data.get("wallet_address")
    if not wallet_address or not isinstance(wallet_address, str):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="wallet_address is required")

    # Canonicalise the address (accepts 0x..., ait1..., aitbc1...).
    wallet_address = canonical_address(wallet_address)

    # Clean expired nonces
    now = time.time()
    expired = [addr for addr, (_, created_at) in _auth_nonces.items() if now - created_at > _NONCE_TTL_SECONDS]
    for addr in expired:
        _auth_nonces.pop(addr, None)

    nonce = secrets.token_hex(16)
    _auth_nonces[wallet_address] = (nonce, now)
    logger.info("Issued auth nonce for %s", wallet_address)
    return {"success": True, "nonce": nonce, "wallet_address": wallet_address}


@router.post("/login", response_model=dict, summary="Log in with a wallet-signed nonce")
@rate_limit(rate=10, per=60)
async def auth_login(request: Request, data: dict[str, Any]) -> dict[str, Any]:
    """Verify a wallet-signed nonce and issue a client JWT."""
    wallet_address = data.get("wallet_address")
    nonce = data.get("nonce")
    signature = data.get("signature")

    if not wallet_address or not isinstance(wallet_address, str):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="wallet_address is required")
    if not nonce or not isinstance(nonce, str):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="nonce is required")
    if not signature or not isinstance(signature, str):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="signature is required")

    wallet_address = canonical_address(wallet_address)

    stored = _auth_nonces.get(wallet_address)
    if not stored or stored[0] != nonce:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired nonce")

    # Single-use nonce
    _auth_nonces.pop(wallet_address, None)

    message = _build_sign_message(wallet_address, nonce)
    msg_hash = defunct_hash_message(text=message)

    try:
        valid = verify_signature(msg_hash, signature, wallet_address)
    except SignatureMalformed as e:
        logger.warning("Malformed login signature from %s: %s", wallet_address, e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature format")

    if not valid:
        logger.warning("Invalid login signature from %s", wallet_address)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Signature verification failed")

    token = create_access_token(user_id=wallet_address, role="client")
    logger.info("Wallet %s logged in successfully", wallet_address)
    return {
        "success": True,
        "session_token": token,
        "wallet_address": wallet_address,
        "role": "client",
    }
