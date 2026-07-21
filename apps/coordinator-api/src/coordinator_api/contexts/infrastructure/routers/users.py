"""
User Management Router for AITBC

v0.10.16: Session state moved from module-global Redis sessions to JWT access
tokens issued after a wallet-signed nonce challenge. Object-level ownership is
enforced on balance and transaction routes.
"""

import re
import secrets
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, cast

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from aitbc.auth import create_access_token, verify_access_token
from aitbc.rate_limiting import rate_limit
from coordinator_api.contexts.infrastructure.services.redis_state import RedisStateManager

from ...infrastructure.domain import Transaction, User, Wallet
from ....schemas import UserBalance, UserCreate, UserLogin, UserNonceRequest, UserNonceResponse, UserProfile
from ....storage import get_session

router = APIRouter(tags=["users"])

# Redis-backed state (falls back to in-memory if Redis unavailable)
_state = RedisStateManager.get_instance_sync()
_SESSION_NS = "sessions"
_NONCE_NS = "wallet_nonces"
_BLOCKLIST_NS = "token_blocklist"

# Nonce lifetime in seconds
_NONCE_TTL = 300


def _admin_wallet_addresses() -> set[str]:
    """Return configured admin wallet addresses as a lower-case set."""
    from ....config import settings

    return {a.strip().lower() for a in settings.admin_wallet_addresses.split(",") if a.strip()}


def _user_role_for_wallet(wallet_address: str) -> str:
    """Determine JWT role for a wallet address."""
    if wallet_address.lower() in _admin_wallet_addresses():
        return "admin"
    return "client"


def _is_valid_wallet_address(wallet_address: str) -> bool:
    """Check that a wallet address looks like a 20-byte hex Ethereum address."""
    return bool(re.fullmatch(r"^0x[a-fA-F0-9]{40}$", wallet_address))


def _build_sign_message(wallet_address: str, nonce: str) -> str:
    """Build the canonical message a wallet must sign to prove ownership."""
    return f"Sign this message to log in to AITBC.\nWallet: {wallet_address.lower()}\nNonce: {nonce}"


def _verify_wallet_signature(wallet_address: str, signature: str, nonce: str) -> bool:
    """Verify that ``signature`` over ``nonce`` recovers to ``wallet_address``."""
    if not signature:
        return False

    message = _build_sign_message(wallet_address, nonce)
    try:
        signable = encode_defunct(text=message)
        sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
        recovered = Account.recover_message(signable, signature=sig_bytes)
    except Exception:
        return False

    return bool(recovered.lower() == wallet_address.lower())


async def _issue_nonce(wallet_address: str) -> str:
    """Generate, store, and return a one-time login nonce."""
    nonce = secrets.token_urlsafe(16)
    expires_at = int(time.time()) + _NONCE_TTL
    await _state.cache_set(_NONCE_NS, wallet_address.lower(), {"nonce": nonce, "expires_at": expires_at}, ttl=_NONCE_TTL)
    return nonce


async def _consume_nonce(wallet_address: str, nonce: str) -> bool:
    """Validate a nonce for a wallet address and delete it to prevent replay."""
    key = wallet_address.lower()
    record = await _state.cache_get(_NONCE_NS, key)
    if not record or record.get("nonce") != nonce:
        return False
    if int(time.time()) > record.get("expires_at", 0):
        return False

    await _state.cache_delete(_NONCE_NS, key)
    return True


async def _create_session(user_id: str, role: str) -> str:
    """Create a JWT access token for a user."""
    return create_access_token(user_id, role)


async def _is_token_revoked(token: str) -> bool:
    """Check whether a token has been logged out."""
    revoked = await _state.cache_get(_BLOCKLIST_NS, token)
    return revoked is not None


async def _revoke_token(token: str) -> None:
    """Add a token to the revocation blocklist until its natural expiry."""
    try:
        payload = verify_access_token(token)
    except HTTPException:
        return

    exp = payload.get("exp")
    if not exp:
        return

    ttl = max(int(exp) - int(time.time()), 60)
    await _state.cache_set(_BLOCKLIST_NS, token, True, ttl=ttl)


def _extract_token(request: Request) -> str:
    """Extract session token from Authorization header or query parameter."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return request.query_params.get("token", "")


async def _get_current_user_payload(request: Request) -> dict[str, Any]:
    """Extract and verify a JWT token from the request, checking the blocklist.

    If the global JWT middleware already verified the token and attached it to
    request state, reuse that payload after the blocklist check so the two auth
    flows do not double-verify.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    if await _is_token_revoked(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    state_payload = cast(dict[str, Any] | None, getattr(request.state, "user", None))
    if state_payload and state_payload.get("sub"):
        return state_payload

    try:
        return verify_access_token(token)
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from None


def _require_owner_or_admin(user_id: str, current_user: dict[str, Any]) -> None:
    """Enforce that ``current_user`` owns ``user_id`` or is an admin."""
    if current_user.get("role") == "admin":
        return
    if current_user.get("sub") == user_id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.post("/auth/nonce", response_model=UserNonceResponse)
@rate_limit(rate=20, per=60)
async def get_login_nonce(
    request_data: UserNonceRequest,
    request: Request,  # noqa: ARG001
) -> dict[str, Any]:
    """Issue a short-lived nonce that must be signed to log in or register."""
    wallet_address = request_data.wallet_address
    if not _is_valid_wallet_address(wallet_address):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid wallet address")

    nonce = await _issue_nonce(wallet_address)
    return {
        "wallet_address": wallet_address,
        "nonce": nonce,
        "expires_at": int(time.time()) + _NONCE_TTL,
    }


@router.post("/register", response_model=UserProfile)
@rate_limit(rate=10, per=60)
async def register_user(
    user_data: UserCreate, request: Request, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    """Register a new user with a cryptographically proven wallet address."""
    wallet_address = user_data.wallet_address
    if not _is_valid_wallet_address(wallet_address):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid wallet address")

    if not await _consume_nonce(wallet_address, user_data.nonce):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired nonce")

    if not _verify_wallet_signature(wallet_address, user_data.signature, user_data.nonce):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid wallet signature")

    # Check for existing user or wallet
    existing_user = session.execute(select(User).where(User.email == user_data.email)).scalars().first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    existing_wallet = session.execute(select(Wallet).where(Wallet.address == wallet_address.lower())).scalars().first()
    if existing_wallet:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Wallet already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=user_data.email,
        username=user_data.username,
        created_at=datetime.now(UTC),
        last_login=datetime.now(UTC),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    wallet = Wallet(user_id=user.id, address=wallet_address.lower(), balance=Decimal("0.0"), created_at=datetime.now(UTC))
    session.add(wallet)
    session.commit()

    role = _user_role_for_wallet(wallet_address)
    token = await _create_session(user.id, role)

    return {
        "user_id": user.id,
        "email": user.email,
        "username": user.username,
        "created_at": user.created_at.isoformat(),
        "session_token": token,
    }


@router.post("/login", response_model=UserProfile)
@rate_limit(rate=20, per=60)
async def login_user(
    login_data: UserLogin, request: Request, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    """Log in (or auto-register) with a signed wallet-address nonce challenge."""
    wallet_address = login_data.wallet_address
    if not _is_valid_wallet_address(wallet_address):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid wallet address")

    if not await _consume_nonce(wallet_address, login_data.nonce):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired nonce")

    if not _verify_wallet_signature(wallet_address, login_data.signature, login_data.nonce):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid wallet signature")

    # Find existing wallet; auto-register if this wallet has never logged in
    wallet = session.execute(select(Wallet).where(Wallet.address == wallet_address.lower())).scalars().first()
    if wallet:
        user = session.get(User, wallet.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for wallet")
        user.last_login = datetime.now(UTC)
        session.commit()
    else:
        user = User(
            id=str(uuid.uuid4()),
            email=f"{wallet_address.lower()}@aitbc.local",
            username=f"user_{wallet_address.lower()[-8:]}_{str(uuid.uuid4())[:8]}",
            created_at=datetime.now(UTC),
            last_login=datetime.now(UTC),
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        wallet = Wallet(user_id=user.id, address=wallet_address.lower(), balance=Decimal("0.0"), created_at=datetime.now(UTC))
        session.add(wallet)
        session.commit()

    role = _user_role_for_wallet(wallet_address)
    token = await _create_session(user.id, role)

    return {
        "user_id": user.id,
        "email": user.email,
        "username": user.username,
        "created_at": user.created_at.isoformat(),
        "session_token": token,
    }


@router.get("/users/me", response_model=UserProfile)
@rate_limit(rate=100, per=60)
async def get_current_user(
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, Any]:
    """Get current user profile"""
    payload = await _get_current_user_payload(request)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return {
        "user_id": user.id,
        "email": user.email,
        "username": user.username,
        "created_at": user.created_at.isoformat(),
        "session_token": _extract_token(request),
    }


@router.get("/users/{user_id}/balance", response_model=UserBalance)
@rate_limit(rate=50, per=60)
async def get_user_balance(
    user_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get user's AITBC balance"""
    current_user = await _get_current_user_payload(request)
    _require_owner_or_admin(user_id, current_user)

    wallet = session.execute(select(Wallet).where(Wallet.user_id == user_id)).scalars().first()
    if not wallet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

    return {
        "user_id": user_id,
        "address": wallet.address,
        "balance": wallet.balance,
        "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None,
    }


@router.post("/logout")
@rate_limit(rate=20, per=60)
async def logout_user(token: str, request: Request) -> dict[str, str]:
    """Logout user and invalidate session"""
    # Accept token from explicit query parameter or Authorization header
    effective_token = token or _extract_token(request)
    if effective_token:
        await _revoke_token(effective_token)

    return {"message": "Logged out successfully"}


@router.get("/users/{user_id}/transactions")
@rate_limit(rate=50, per=60)
async def get_user_transactions(
    user_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get user's transaction history from the database."""
    current_user = await _get_current_user_payload(request)
    _require_owner_or_admin(user_id, current_user)

    user = session.execute(select(User).where(User.id == user_id)).scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    txs = (
        session.execute(select(Transaction).where(Transaction.user_id == user_id).order_by(Transaction.created_at.desc()))  # type: ignore[attr-defined]
        .scalars()
        .all()
    )

    transactions = [
        {
            "id": tx.id,
            "type": tx.type,
            "status": tx.status,
            "amount": tx.amount,
            "fee": tx.fee,
            "description": tx.description,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
            "confirmed_at": tx.confirmed_at.isoformat() if tx.confirmed_at else None,
        }
        for tx in txs
    ]

    return {"user_id": user_id, "transactions": transactions, "total": len(transactions)}
