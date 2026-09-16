"""resolve_client must never mint placeholder users for unresolvable references.

``auto_create=True`` previously created ``placeholder_<uuid>@aitbc.local`` rows
for *any* unresolvable ``client_ref`` — silently turning a bad caller-supplied
identifier into a real user. Now only wallet-address refs auto-provision (the
address is a real on-chain anchor); anything else is an error.
"""

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.utils.client_resolver import resolve_client


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=[User.__table__, Wallet.__table__])
    with Session(engine) as session:
        yield session


WALLET_ADDR = "0x" + "ab" * 20


def test_resolves_existing_user_id(session):
    user = User(id="user-1", email="u1@example.com", username="user-one")
    session.add(user)
    session.commit()
    assert resolve_client(session, "user-1") == ("user-1", "user-1")


def test_resolves_existing_username(session):
    user = User(id="user-2", email="u2@example.com", username="user-two")
    session.add(user)
    session.commit()
    assert resolve_client(session, "user-two") == ("user-2", "user-two")


def test_resolves_registered_wallet_address(session):
    user = User(id="user-3", email="u3@example.com", username="user-three")
    session.add(user)
    session.flush()
    session.add(Wallet(user_id="user-3", address=WALLET_ADDR.lower()))
    session.commit()
    assert resolve_client(session, WALLET_ADDR) == ("user-3", WALLET_ADDR)


def test_unregistered_wallet_auto_creates_when_allowed(session):
    client_id, ref = resolve_client(session, WALLET_ADDR, auto_create=True)
    wallet = session.exec(select(Wallet).where(Wallet.address == WALLET_ADDR)).first()
    assert wallet is not None
    assert wallet.user_id == client_id
    assert ref == WALLET_ADDR


def test_unregistered_wallet_errors_without_auto_create(session):
    with pytest.raises(ValueError, match="Wallet address not registered"):
        resolve_client(session, WALLET_ADDR)


def test_arbitrary_ref_never_creates_placeholder_user(session):
    """The removed behaviour: a random string must error, not mint a user."""
    with pytest.raises(ValueError, match="Client reference not found"):
        resolve_client(session, "some-random-client-string", auto_create=True)
    assert session.exec(select(User)).all() == []


def test_empty_ref_rejected(session):
    with pytest.raises(ValueError, match="must not be empty"):
        resolve_client(session, "")
