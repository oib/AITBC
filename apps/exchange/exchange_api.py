#!/usr/bin/env python3
"""
FastAPI backend for the AITBC Trade Exchange
"""

import json
import os
import secrets
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

sys.path.insert(0, "/opt/aitbc")
from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

from database import get_db, init_db  # noqa: E402
from models import Order, Trade, User  # noqa: E402

from aitbc.rate_limiting import RateLimitMiddleware  # noqa: E402

# Session storage configuration.
# In production, set EXCHANGE_REDIS_URL to use Redis-backed sessions (survives
# restarts, works across multiple workers). When unset or unreachable, falls
# back to an in-memory dict for local development.
_REDIS_URL = os.getenv("EXCHANGE_REDIS_URL", "")
_SESSION_TTL = 86400  # 24 hours


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    yield
    # Shutdown (cleanup if needed)
    pass


# Initialize FastAPI app
app = FastAPI(title="AITBC Trade Exchange API", version="1.0.0", lifespan=lifespan)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware, rate=100, per=60)

# In-memory session storage fallback (used when Redis is not configured/unreachable).
_user_sessions: dict[str, dict] = {}

_redis_client = None
if _REDIS_URL:
    try:
        import redis as _redis_module

        _redis_client = _redis_module.from_url(_REDIS_URL, decode_responses=True)
        _redis_client.ping()  # verify connectivity
        logger.info("Exchange sessions backed by Redis: %s", _REDIS_URL)
    except Exception as e:
        logger.warning("Redis unavailable (%s); falling back to in-memory sessions", e)
        _redis_client = None


def _store_session(token: str, session_data: dict) -> None:
    """Persist a session token. Uses Redis if available, else in-memory dict."""
    if _redis_client is not None:
        _redis_client.setex(f"session:{token}", _SESSION_TTL, json.dumps(session_data))
    else:
        _user_sessions[token] = session_data


def _load_session(token: str) -> dict | None:
    """Load a session token. Returns None if not found or expired."""
    if _redis_client is not None:
        raw = _redis_client.get(f"session:{token}")
        if raw is None:
            return None
        return json.loads(raw)
    session = _user_sessions.get(token)
    if session is None:
        return None
    if int(time.time()) > session["expires_at"]:
        _user_sessions.pop(token, None)
        return None
    return session


def _delete_session(token: str) -> None:
    """Remove a session token."""
    if _redis_client is not None:
        _redis_client.delete(f"session:{token}")
    else:
        _user_sessions.pop(token, None)


def verify_session_token(token: str = Header(..., alias="Authorization")) -> int:
    """Verify session token and return user_id"""
    # Remove "Bearer " prefix if present
    if token.startswith("Bearer "):
        token = token[7:]

    session = _load_session(token)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    return session["user_id"]


def optional_auth(token: str | None = Header(None, alias="Authorization")) -> int | None:
    """Optional authentication - returns user_id if token is valid, None otherwise"""
    if not token:
        return None

    try:
        return verify_session_token(token)
    except HTTPException:
        return None


# Type annotations for dependencies
UserDep = Annotated[int, Depends(verify_session_token)]
OptionalUserDep = Annotated[int | None, Depends(optional_auth)]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080", "http://localhost:8011", "http://localhost:8008"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],  # Allow all headers for auth tokens
)


# Pydantic models
class OrderCreate(BaseModel):
    order_type: str  # 'BUY' or 'SELL'
    amount: float
    price: float


class OrderResponse(BaseModel):
    id: int
    order_type: str
    amount: float
    price: float
    total: float
    filled: float
    remaining: float
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TradeResponse(BaseModel):
    id: int
    amount: float
    price: float
    total: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderBookResponse(BaseModel):
    buys: list[OrderResponse]
    sells: list[OrderResponse]


def create_mock_trades(db: Session):
    """Deprecated — no longer creates mock trades.

    The exchange now uses only real trade data. This function is kept as a
    no-op for backward compatibility with any code that calls it.
    """
    logger.info("create_mock_trades is a no-op — exchange uses real data only")


@app.get("/api/trades/recent", response_model=list[TradeResponse])
def get_recent_trades(limit: int | None, db: Annotated[Session, Depends(get_db)]):
    """Get recent trades"""
    trades = db.query(Trade).order_by(desc(Trade.created_at)).limit(limit).all()
    return trades


@app.get("/api/orders", response_model=list[OrderResponse])
def get_orders(
    status_filter: str | None,
    user_only: bool | None,
    db: Annotated[Session, Depends(get_db)],
    user_id: OptionalUserDep = None,
):
    """Get all orders with optional status filter"""
    query = db.query(Order)

    # Filter by user if requested and authenticated
    if user_only and user_id:
        query = query.filter(Order.user_id == user_id)

    if status_filter:
        query = query.filter(Order.status == status_filter.upper())

    orders = query.order_by(Order.created_at.desc()).all()
    return orders


@app.get("/api/my/orders", response_model=list[OrderResponse])
def get_my_orders(user_id: UserDep, status_filter: str | None, db: Annotated[Session, Depends(get_db)]):
    """Get current user's orders"""
    query = db.query(Order).filter(Order.user_id == user_id)

    if status_filter:
        query = query.filter(Order.status == status_filter.upper())

    orders = query.order_by(Order.created_at.desc()).all()
    return orders


@app.get("/api/orders/orderbook", response_model=OrderBookResponse)
def get_orderbook(db: Annotated[Session, Depends(get_db)]):
    """Get current order book"""

    # Get open buy orders (sorted by price descending)
    buys = (
        db.query(Order)
        .filter(and_(Order.order_type == "BUY", Order.status == "OPEN"))
        .order_by(desc(Order.price))
        .limit(20)
        .all()
    )

    # Get open sell orders (sorted by price ascending)
    sells = (
        db.query(Order).filter(and_(Order.order_type == "SELL", Order.status == "OPEN")).order_by(Order.price).limit(20).all()
    )

    return OrderBookResponse(buys=buys, sells=sells)


@app.post("/api/orders", response_model=OrderResponse)
def create_order(order: OrderCreate, user_id: UserDep, db: Annotated[Session, Depends(get_db)]):
    """Create a new order"""

    # Validate order type
    if order.order_type not in ["BUY", "SELL"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order type must be 'BUY' or 'SELL'")

    # Create order — use Decimal for exact monetary arithmetic
    amount_dec = Decimal(str(order.amount))
    price_dec = Decimal(str(order.price))
    total_dec = amount_dec * price_dec
    db_order = Order(
        user_id=user_id,  # Use authenticated user_id
        order_type=order.order_type,
        amount=amount_dec,
        price=price_dec,
        total=total_dec,
        remaining=amount_dec,
    )

    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    # Try to match the order
    try_match_order(db_order, db)

    return db_order


def try_match_order(order: Order, db: Session):
    """Try to match an order with existing orders.

    Uses ``SELECT ... FOR UPDATE`` row locking to prevent concurrent
    requests from double-matching the same counterparty orders (double-spend
    risk). On SQLite ``with_for_update`` is a no-op; on PostgreSQL it
    acquires row-level locks for the duration of the transaction.
    """

    try:
        if order.order_type == "BUY":
            # Match with sell orders at same or lower price
            matching_orders = (
                db.query(Order)
                .filter(and_(Order.order_type == "SELL", Order.status == "OPEN", Order.price <= order.price))
                .order_by(Order.price)
                .with_for_update()
                .all()
            )
        else:
            # Match with buy orders at same or higher price
            matching_orders = (
                db.query(Order)
                .filter(and_(Order.order_type == "BUY", Order.status == "OPEN", Order.price >= order.price))
                .order_by(desc(Order.price))
                .with_for_update()
                .all()
            )

        for match in matching_orders:
            if order.remaining <= 0:
                break

            # Calculate trade amount — Decimal arithmetic avoids float drift
            trade_amount = min(order.remaining, match.remaining)
            trade_total = trade_amount * match.price

            # Create trade record — use uuid4 for unique, unguessable trade_hash
            trade = Trade(
                buyer_id=order.user_id if order.order_type == "BUY" else match.user_id,
                seller_id=match.user_id if order.order_type == "BUY" else order.user_id,
                order_id=order.id,
                amount=trade_amount,
                price=match.price,
                total=trade_total,
                trade_hash=f"trade_{uuid.uuid4()}",
            )

            db.add(trade)

            # Update orders
            order.filled += trade_amount
            order.remaining -= trade_amount
            match.filled += trade_amount
            match.remaining -= trade_amount

            # Update order statuses
            if order.remaining <= 0:
                order.status = "FILLED"
            else:
                order.status = "PARTIALLY_FILLED"

            if match.remaining <= 0:
                match.status = "FILLED"
            else:
                match.status = "PARTIALLY_FILLED"

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Order matching failed for order %s", order.id)
        raise


@app.post("/api/auth/login")
def login_user(wallet_address: str, db: Annotated[Session, Depends(get_db)]):
    """Login with wallet address"""
    # Find or create user
    user = db.query(User).filter(User.wallet_address == wallet_address).first()
    if not user:
        user = User(wallet_address=wallet_address, email=f"{wallet_address}@aitbc.local", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)

    # Create cryptographically random session token (not guessable)
    token = secrets.token_urlsafe(32)

    # Store session
    now = int(time.time())
    _store_session(token, {"user_id": user.id, "created_at": now, "expires_at": now + _SESSION_TTL})

    return {"token": token, "user_id": user.id}


@app.post("/api/auth/logout")
def logout_user(token: str = Header(..., alias="Authorization")):
    """Logout user"""
    if token.startswith("Bearer "):
        token = token[7:]

    _delete_session(token)

    return {"message": "Logged out successfully"}


@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now(UTC)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8008)  # nosec B104
