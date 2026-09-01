"""Resolve caller-provided client references to canonical users.id values."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlmodel import Session

from ..contexts.infrastructure.domain.user import User, Wallet


_WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def _looks_like_uuid(value: str) -> bool:
    """Return True if value is a UUID hex string."""
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _unique_username(session: Session, base: str) -> str:
    """Generate a unique username from a base string."""
    candidate = base[:255]
    if not session.exec(select(User).where(User.username == candidate)).first():
        return candidate
    suffix = uuid.uuid4().hex[:8]
    return f"{base[:246]}_{suffix}"


def _create_user_for_wallet(session: Session, wallet_address: str) -> User:
    """Create a User and Wallet for an Ethereum-style address."""
    user_id = str(uuid.uuid4())
    address_lower = wallet_address.lower()
    user = User(
        id=user_id,
        email=f"wallet_{address_lower[-8:]}_{uuid.uuid4().hex[:8]}@aitbc.local",
        username=_unique_username(session, f"user_{address_lower[-8:]}_{uuid.uuid4().hex[:8]}"),
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_login=datetime.now(UTC),
    )
    wallet = Wallet(
        user_id=user.id,
        address=address_lower,
        balance=Decimal("0.0"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(user)
    session.add(wallet)
    session.commit()
    session.refresh(user)
    return user


def _create_placeholder_user(session: Session, client_ref: str) -> User:
    """Create a placeholder User for an arbitrary caller identifier."""
    user_id = str(uuid.uuid4())
    safe_ref = client_ref[:255]
    user = User(
        id=user_id,
        email=f"placeholder_{uuid.uuid4().hex[:8]}@aitbc.local",
        username=_unique_username(session, safe_ref),
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_login=datetime.now(UTC),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def resolve_client(
    session: Session,
    client_ref: str,
    *,
    auto_create: bool = False,
) -> tuple[str, str]:
    """Resolve a caller-provided client reference to a canonical ``users.id``.

    Returns ``(client_id, client_ref)`` where ``client_id`` is the canonical
    ``users.id`` and ``client_ref`` is the original caller string. ``auto_create``
    controls whether a missing wallet/username reference causes a placeholder user
    to be created.
    """
    raw = (client_ref or "").strip()
    if not raw:
        raise ValueError("client_ref must not be empty")

    # Already a user id (UUID or other primary key).
    user = session.get(User, raw)
    if user:
        return user.id, raw

    # Ethereum wallet address.
    if _WALLET_RE.match(raw):
        wallet = session.exec(select(Wallet).where(Wallet.address == raw.lower())).scalars().first()
        if wallet:
            user = session.get(User, wallet.user_id)
            if user:
                return user.id, raw
        if auto_create:
            return _create_user_for_wallet(session, raw).id, raw
        raise ValueError(f"Wallet address not registered: {raw}")

    # Username lookup.
    user = session.exec(select(User).where(User.username == raw)).scalars().first()
    if user:
        return user.id, raw

    if auto_create:
        return _create_placeholder_user(session, raw).id, raw

    raise ValueError(f"Client reference not found: {raw}")
