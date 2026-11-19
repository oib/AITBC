"""
User Management Router for AITBC

v0.10.16: Session state moved from module-global Redis sessions to JWT access
tokens issued after a wallet-signed nonce challenge. Object-level ownership is
enforced on balance and transaction routes.
"""

import os
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from aitbc.auth import create_access_token, verify_access_token
from aitbc.auth.jwt import canonical_token
from aitbc.rate_limiting import rate_limit

from ...infrastructure.domain import Transaction, User, Wallet
from ....schemas import UserBalance, UserCreate, UserLogin, UserNonceRequest, UserNonceResponse, UserProfile
from ....storage import get_session

router = APIRouter(tags=["users"])

# Expected failure surface for wallet-signature verification: the lazy
# eth_account import, hex decoding and recover_message data-shape errors.
# BaseExceptions still propagate.
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
)

# Nonce lifetime in seconds
_NONCE_TTL = 300

# ------------------------------------------------------------------
# Shared auth state — sqlite store under ``AITBC_DATA_DIR`` (#2154, #2180)
#
# Login nonces and the logout token blocklist used to live in
# ``_state.cache_*`` (RedisStateManager), which falls back to per-process
# memory when Redis is disabled — and Redis cannot even be enabled through
# the service env (``settings.redis.enabled`` had no env mapping until
# #2180). coordinator-api runs ``uvicorn --workers 2``, so state written by
# one worker was invisible to the other: ``POST /v1/auth/nonce`` landed on
# one worker and ``POST /v1/login`` on the other a fraction of the time,
# returning "Invalid or expired nonce" for a nonce issued seconds earlier —
# observed live against the ``default`` admin wallet on hub (#2154). The
# same split meant ``POST /v1/logout`` revoked the JWT only in the handling
# worker's memory while the other worker kept accepting it until JWT expiry
# (#2180). Same bug class as #1771 (island swarm-key nonces) and #1967
# (provider-bond challenges); same cure — a small sqlite file shared by
# every worker and every restart. The file keeps the ``login-nonces.db``
# name it was created with; it now also holds ``revoked_token``.
# ------------------------------------------------------------------

_LOGIN_NONCE_MAX_PENDING = 10_000
_TOKEN_BLOCKLIST_MAX = 10_000

_AUTH_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS wallet_login_nonce (
    wallet_address TEXT PRIMARY KEY,
    nonce TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS revoked_token (
    token TEXT PRIMARY KEY,
    expires_at REAL NOT NULL,
    revoked_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revoked_token_expires ON revoked_token(expires_at);
"""


def _auth_db_path() -> Path:
    """Shared auth-state store under ``AITBC_DATA_DIR``."""
    data_dir = Path(os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc/data"))
    return data_dir / "auth" / "login-nonces.db"


def _connect_auth_db() -> sqlite3.Connection:
    """Open the shared auth-state DB, creating schema on first use.

    ``isolation_level=None`` gives explicit transaction control so issue,
    consume, revoke and check can hold a write lock (``BEGIN IMMEDIATE``) —
    two workers cannot interleave a consume with an issue for the same
    wallet, or a revoke-check with a logout.
    """
    path = _auth_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(_AUTH_DB_SCHEMA)
    return conn


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
    # Function-local: eth_account pulls in the coincurve/eth-keys chain (~0.3 s)
    # and this router is imported on every coordinator start, while signature
    # verification only runs on login attempts.
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from eth_keys.exceptions import BadSignature
    from eth_utils.exceptions import ValidationError

    try:
        signable = encode_defunct(text=message)
        sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
        recovered = Account.recover_message(signable, signature=sig_bytes)
    except _OPS_ERRORS + (BadSignature, ValidationError):
        return False

    return bool(recovered.lower() == wallet_address.lower())


def _issue_nonce(wallet_address: str) -> str:
    """Generate, store, and return a one-time login nonce.

    One pending nonce per wallet — issuing a new nonce replaces the old one,
    matching the previous ``cache_set`` upsert semantics. Runs under
    ``BEGIN IMMEDIATE`` so the expiry sweep, pending cap and upsert are
    atomic across workers.
    """
    now = time.time()
    expires_at = now + _NONCE_TTL
    nonce = secrets.token_urlsafe(16)
    wallet = wallet_address.lower()
    with closing(_connect_auth_db()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM wallet_login_nonce WHERE expires_at <= ?", (now,))
            pending = conn.execute("SELECT COUNT(*) FROM wallet_login_nonce").fetchone()
            if pending is not None and int(pending[0]) >= _LOGIN_NONCE_MAX_PENDING:
                # Evict the oldest pending nonce rather than fail logins.
                conn.execute(
                    "DELETE FROM wallet_login_nonce WHERE wallet_address = ("
                    "SELECT wallet_address FROM wallet_login_nonce ORDER BY created_at ASC LIMIT 1)"
                )
            conn.execute(
                "INSERT OR REPLACE INTO wallet_login_nonce"
                " (wallet_address, nonce, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (wallet, nonce, expires_at, now),
            )
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
    return nonce


def _consume_nonce(wallet_address: str, nonce: str) -> bool:
    """Validate a nonce for a wallet address and delete it to prevent replay.

    The whole check-and-burn runs inside one ``BEGIN IMMEDIATE`` transaction,
    so exactly one worker can consume a given nonce — the same
    DELETE-on-success semantics the in-memory path had, now shared across
    workers. A wrong or expired nonce leaves the stored row untouched,
    matching the previous behaviour (the caller must request a fresh nonce).
    """
    if not nonce:
        return False
    now = time.time()
    wallet = wallet_address.lower()
    with closing(_connect_auth_db()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT nonce, expires_at FROM wallet_login_nonce WHERE wallet_address = ?",
                (wallet,),
            ).fetchone()
            consumed = False
            if row is not None and row[0] == nonce and now <= float(row[1]):
                conn.execute("DELETE FROM wallet_login_nonce WHERE wallet_address = ?", (wallet,))
                consumed = True
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
    return consumed


def _create_session(user_id: str, role: str) -> str:
    """Create a JWT access token for a user with a secure random session identifier."""
    return create_access_token(user_id, role, extra_claims={"session_id": secrets.token_urlsafe(16)})


def _is_token_revoked(token: str) -> bool:
    """Check whether a token is on the shared revocation blocklist.

    Reads the sqlite store directly so every uvicorn worker sees revocations
    written by any other worker (#2180). Expired entries are ignored — JWT
    expiry bounds the blocklist naturally, and ``_revoke_token`` sweeps them
    on write.
    """
    now = time.time()
    # #2273: PyJWT verifies several spellings of one token (last signature
    # character's unused bits, padding, stray characters), so the lookup keys
    # on the canonical spelling. The raw string is matched too, so rows written
    # by the pre-#2273 code stay revoked across the upgrade.
    canonical = canonical_token(token)
    with closing(_connect_auth_db()) as conn:
        rows = conn.execute("SELECT expires_at FROM revoked_token WHERE token IN (?, ?)", (canonical, token)).fetchall()
    return any(now <= float(row[0]) for row in rows)


def _revoke_token(token: str) -> None:
    """Add a token to the shared revocation blocklist until its natural expiry.

    Same semantics as the old ``cache_set`` path — block until the JWT's own
    ``exp`` — but persisted in sqlite so the other uvicorn worker honours the
    logout too. Runs under ``BEGIN IMMEDIATE`` with an expired-row sweep and
    an oldest-evict cap, mirroring ``_issue_nonce``.
    """
    try:
        payload = verify_access_token(token)
    except HTTPException:
        return

    exp = payload.get("exp")
    if not exp:
        return

    now = time.time()
    expires_at = float(exp)
    with closing(_connect_auth_db()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM revoked_token WHERE expires_at <= ?", (now,))
            pending = conn.execute("SELECT COUNT(*) FROM revoked_token").fetchone()
            if pending is not None and int(pending[0]) >= _TOKEN_BLOCKLIST_MAX:
                # Evict the oldest revocation rather than fail logouts — an
                # evicted token is still bounded by its own JWT expiry.
                conn.execute(
                    "DELETE FROM revoked_token WHERE token = (SELECT token FROM revoked_token ORDER BY revoked_at ASC LIMIT 1)"
                )
            conn.execute(
                "INSERT OR REPLACE INTO revoked_token (token, expires_at, revoked_at) VALUES (?, ?, ?)",
                (canonical_token(token), expires_at, now),
            )
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise


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

    if await run_in_threadpool(_is_token_revoked, token):
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

    nonce = await run_in_threadpool(_issue_nonce, wallet_address)
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

    if not await run_in_threadpool(_consume_nonce, wallet_address, user_data.nonce):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired nonce")

    if not _verify_wallet_signature(wallet_address, user_data.signature, user_data.nonce):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid wallet signature")

    # Check for existing user or wallet
    existing_user = await run_in_threadpool(
        lambda: session.execute(select(User).where(User.email == user_data.email)).scalars().first()
    )
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    existing_wallet = await run_in_threadpool(
        lambda: session.execute(select(Wallet).where(Wallet.address == wallet_address.lower())).scalars().first()
    )
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
    await run_in_threadpool(session.commit)
    await run_in_threadpool(session.refresh, user)

    wallet = Wallet(user_id=user.id, address=wallet_address.lower(), balance=Decimal("0.0"), created_at=datetime.now(UTC))
    session.add(wallet)
    await run_in_threadpool(session.commit)

    role = _user_role_for_wallet(wallet_address)
    token = _create_session(user.id, role)

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

    if not await run_in_threadpool(_consume_nonce, wallet_address, login_data.nonce):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired nonce")

    if not _verify_wallet_signature(wallet_address, login_data.signature, login_data.nonce):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid wallet signature")

    # Find existing wallet; auto-register if this wallet has never logged in
    wallet = await run_in_threadpool(
        lambda: session.execute(select(Wallet).where(Wallet.address == wallet_address.lower())).scalars().first()
    )
    if wallet:
        user = await run_in_threadpool(session.get, User, wallet.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for wallet")
        user.last_login = datetime.now(UTC)
        await run_in_threadpool(session.commit)
    else:
        user = User(
            id=str(uuid.uuid4()),
            email=f"{wallet_address.lower()}@aitbc.local",
            username=f"user_{wallet_address.lower()[-8:]}_{str(uuid.uuid4())[:8]}",
            created_at=datetime.now(UTC),
            last_login=datetime.now(UTC),
        )
        session.add(user)
        await run_in_threadpool(session.commit)
        await run_in_threadpool(session.refresh, user)

        wallet = Wallet(user_id=user.id, address=wallet_address.lower(), balance=Decimal("0.0"), created_at=datetime.now(UTC))
        session.add(wallet)
        await run_in_threadpool(session.commit)

    role = _user_role_for_wallet(wallet_address)
    token = _create_session(user.id, role)

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

    user = await run_in_threadpool(session.get, User, user_id)
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

    wallet = await run_in_threadpool(
        lambda: session.execute(select(Wallet).where(Wallet.user_id == user_id)).scalars().first()
    )
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
        await run_in_threadpool(_revoke_token, effective_token)

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

    user = await run_in_threadpool(lambda: session.execute(select(User).where(User.id == user_id)).scalars().first())
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    txs = await run_in_threadpool(
        lambda: (
            session.execute(select(Transaction).where(Transaction.user_id == user_id).order_by(Transaction.created_at.desc()))  # type: ignore[attr-defined]
            .scalars()
            .all()
        )
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
