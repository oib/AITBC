"""Tests for users router with signed-nonce wallet authentication."""

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture(autouse=True)
def _override_db_session(client):
    """Override the app's ``get_session`` dependency with an isolated in-memory
    SQLite database so the users-router tests do not depend on a real/persistent
    database file. The override is installed after the shared ``client`` fixture
    is built and removed on teardown.
    """
    from coordinator_api.main import app
    from coordinator_api.storage.db import get_session

    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # A plain `create_all`. This used to be a `while True` that swallowed "already exists"
    # OperationalErrors and retried, blamed on a model declaring the same index twice. The
    # real cause was two services' models sharing one global MetaData: `extend_existing`
    # merged the second definition into the first table and appended `Index` objects already
    # on it. Each service owns its metadata now (V23-72, V23-74).
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _get_session_override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_session, None)


def _sign_login(wallet_address: str, nonce: str, private_key: str) -> str:
    """Sign the canonical AITBC login message with an Ethereum private key."""
    message = f"Sign this message to log in to AITBC.\nWallet: {wallet_address.lower()}\nNonce: {nonce}"
    signable = encode_defunct(text=message)
    return Account.from_key(private_key).sign_message(signable).signature.hex()


def _register_user(client, account: Account):
    """Register a user with a signed nonce. Returns the register response."""
    wallet_address = account.address.lower()
    nonce_resp = client.post("/v1/auth/nonce", json={"wallet_address": wallet_address})
    assert nonce_resp.status_code == 200
    nonce = nonce_resp.json()["nonce"]
    signature = _sign_login(wallet_address, nonce, account.key.hex())

    return client.post(
        "/v1/register",
        json={
            "email": f"{wallet_address[2:10]}@example.com",
            "username": f"user_{wallet_address[2:10]}",
            "wallet_address": wallet_address,
            "nonce": nonce,
            "signature": signature,
        },
    )


def _login_user(client, account: Account):
    """Log in a user with a signed nonce. Returns the login response."""
    wallet_address = account.address.lower()
    nonce_resp = client.post("/v1/auth/nonce", json={"wallet_address": wallet_address})
    assert nonce_resp.status_code == 200
    nonce = nonce_resp.json()["nonce"]
    signature = _sign_login(wallet_address, nonce, account.key.hex())

    return client.post(
        "/v1/login",
        json={
            "wallet_address": wallet_address,
            "nonce": nonce,
            "signature": signature,
        },
    )


def test_register_user(client):
    """Test user registration with a signed wallet address."""
    account = Account.create()
    response = _register_user(client, account)
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    assert data["email"].endswith("@example.com")
    assert "session_token" in data


def test_login_user(client):
    """Test user login with a signed nonce challenge."""
    account = Account.create()
    response = _login_user(client, account)
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    assert "session_token" in data


def test_get_current_user(client):
    """Test getting current user profile with a JWT session token."""
    account = Account.create()
    reg_resp = _register_user(client, account)
    token = reg_resp.json()["session_token"]

    profile_resp = client.get(f"/v1/users/me?token={token}")
    assert profile_resp.status_code == 200
    data = profile_resp.json()
    assert data["email"] == reg_resp.json()["email"]


def test_get_current_user_invalid_token(client):
    """Test getting profile with an invalid or malformed token."""
    response = client.get("/v1/users/me?token=invalid-token")
    assert response.status_code == 401
    assert "Invalid or expired token" in response.json()["detail"]


def test_logout(client):
    """Test user logout invalidates the session token."""
    account = Account.create()
    reg_resp = _register_user(client, account)
    token = reg_resp.json()["session_token"]

    logout_resp = client.post(f"/v1/logout?token={token}")
    assert logout_resp.status_code == 200
    assert "Logged out successfully" in logout_resp.json()["message"]

    profile_resp = client.get(f"/v1/users/me?token={token}")
    assert profile_resp.status_code == 401


def test_forged_signature_rejected(client):
    """A signature from a different wallet is rejected."""
    account = Account.create()
    attacker = Account.create()
    wallet_address = account.address.lower()

    nonce_resp = client.post("/v1/auth/nonce", json={"wallet_address": wallet_address})
    assert nonce_resp.status_code == 200
    nonce = nonce_resp.json()["nonce"]
    forged_signature = _sign_login(wallet_address, nonce, attacker.key.hex())

    response = client.post(
        "/v1/login",
        json={
            "wallet_address": wallet_address,
            "nonce": nonce,
            "signature": forged_signature,
        },
    )
    assert response.status_code == 401


def test_replayed_nonce_rejected(client):
    """A nonce cannot be used more than once."""
    account = Account.create()
    wallet_address = account.address.lower()

    nonce_resp = client.post("/v1/auth/nonce", json={"wallet_address": wallet_address})
    nonce = nonce_resp.json()["nonce"]
    signature = _sign_login(wallet_address, nonce, account.key.hex())

    payload = {
        "wallet_address": wallet_address,
        "nonce": nonce,
        "signature": signature,
    }

    # First use succeeds
    first = client.post("/v1/login", json=payload)
    assert first.status_code == 200

    # Replay fails
    second = client.post("/v1/login", json=payload)
    assert second.status_code == 401
    assert "nonce" in second.json()["detail"].lower()


def test_token_guessing_rejected(client):
    """A random, syntactically plausible token is rejected."""
    import secrets

    fake_token = secrets.token_urlsafe(32)
    response = client.get(f"/v1/users/me?token={fake_token}")
    assert response.status_code == 401


def test_idor_balance_access_denied(client):
    """A user cannot read another user's balance using their own token."""
    alice = Account.create()
    bob = Account.create()

    alice_resp = _register_user(client, alice)
    alice_token = alice_resp.json()["session_token"]
    alice_user_id = alice_resp.json()["user_id"]

    bob_resp = _register_user(client, bob)
    bob_user_id = bob_resp.json()["user_id"]

    # Alice tries to read Bob's balance
    response = client.get(f"/v1/users/{bob_user_id}/balance?token={alice_token}")
    assert response.status_code == 403

    # Alice can read her own balance
    own = client.get(f"/v1/users/{alice_user_id}/balance?token={alice_token}")
    assert own.status_code == 200
    assert own.json()["user_id"] == alice_user_id
