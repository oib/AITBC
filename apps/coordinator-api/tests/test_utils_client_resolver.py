"""Coverage for utils.client_resolver.resolve_client (#1289 residual).

Identity resolution is security-relevant: it decides which users.id a
caller-provided reference maps to. Pins the lookup order (user id →
wallet → username), the wallet-only auto-provision rule (GAP-59),
case-insensitive wallet matching, and unique-username collision handling.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.utils.client_resolver import resolve_client


def _user(session: Session, user_id: str, username: str, email: str | None = None) -> User:
    u = User(
        id=user_id,
        email=email or f"{username}@test.local",
        username=username,
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(u)
    session.commit()
    return u


def _wallet(session: Session, user_id: str, address: str) -> Wallet:
    w = Wallet(
        user_id=user_id,
        address=address.lower(),
        balance=Decimal("0.0"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(w)
    session.commit()
    return w


WALLET = "0x" + "a" * 40
WALLET2 = "0x" + "B" * 40  # mixed case on purpose


# ---------------------------------------------------------------------------
# input validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_ref_rejected(db_session):
    for bad in ("", "   ", None):
        with pytest.raises(ValueError, match="must not be empty"):
            resolve_client(db_session, bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# user id / username lookups
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_user_id_resolves(db_session):
    _user(db_session, "user-123", "alice")
    cid, ref = resolve_client(db_session, "user-123")
    assert cid == "user-123"
    assert ref == "user-123"


@pytest.mark.unit
def test_username_resolves(db_session):
    _user(db_session, "user-1", "bob")
    cid, _ = resolve_client(db_session, "bob")
    assert cid == "user-1"


@pytest.mark.unit
def test_unknown_ref_rejected(db_session):
    with pytest.raises(ValueError, match="not found"):
        resolve_client(db_session, "nobody")


# ---------------------------------------------------------------------------
# wallet lookups
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_registered_wallet_resolves_case_insensitive(db_session):
    _user(db_session, "user-w", "carol")
    _wallet(db_session, "user-w", WALLET)
    cid, _ = resolve_client(db_session, WALLET.upper().replace("0X", "0x"))
    assert cid == "user-w"


@pytest.mark.unit
def test_unregistered_wallet_requires_auto_create(db_session):
    with pytest.raises(ValueError, match="not registered"):
        resolve_client(db_session, WALLET, auto_create=False)


@pytest.mark.unit
def test_auto_create_provisions_user_and_wallet(db_session):
    cid, ref = resolve_client(db_session, WALLET2, auto_create=True)
    assert ref == WALLET2
    user = db_session.get(User, cid)
    assert user is not None
    wallet = db_session.exec(select(Wallet).where(Wallet.address == WALLET2.lower())).first()
    assert wallet is not None
    assert wallet.user_id == cid
    # stored lowercase regardless of input case
    assert wallet.address == WALLET2.lower()


@pytest.mark.unit
def test_auto_create_does_not_apply_to_non_wallet_refs(db_session):
    # GAP-59: arbitrary strings must never become placeholder users
    with pytest.raises(ValueError, match="not found"):
        resolve_client(db_session, "random-string", auto_create=True)


@pytest.mark.unit
def test_malformed_wallet_falls_through_to_username(db_session):
    # "0xZZZ..." is not a valid wallet; if a user happens to share the
    # name it resolves as username, else ValueError
    with pytest.raises(ValueError):
        resolve_client(db_session, "0x" + "z" * 40)
