"""#3024 AUTHZ-JWT-QUERY-PARAM-LOG-LEAK-1 pins.

``users.py`` accepted ``?token=<jwt>`` as an ``_extract_token`` fallback and
``POST /v1/logout`` took an explicit ``token`` query param — a URL-borne JWT
lands in proxy/nginx access logs, browser history and Referer headers. The
query-param path is removed; header auth is unchanged. The documented
websocket bootstrap carve-out lives in agent-coordinator and is untouched.
"""

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture(autouse=True)
def _override_db_session(client):
    """Same isolated in-memory override as test_routers_users.py."""
    from coordinator_api.main import app
    from coordinator_api.storage.db import get_session

    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _get_session_override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def _sign_login(wallet_address: str, nonce: str, private_key: str) -> str:
    message = f"Sign this message to log in to AITBC.\nWallet: {wallet_address.lower()}\nNonce: {nonce}"
    signable = encode_defunct(text=message)
    return Account.from_key(private_key).sign_message(signable).signature.hex()


def _register_user(client, account: Account):
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


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_query_param_token_rejected_on_users_me(client):
    """A valid JWT in ?token= no longer authenticates /v1/users/me."""
    account = Account.create()
    reg_resp = _register_user(client, account)
    assert reg_resp.status_code == 200
    token = reg_resp.json()["session_token"]

    resp = client.get(f"/v1/users/me?token={token}")
    assert resp.status_code == 401


def test_query_param_token_rejected_on_balance(client):
    """Same for a second authenticated surface — balance read."""
    account = Account.create()
    reg_resp = _register_user(client, account)
    token = reg_resp.json()["session_token"]
    user_id = reg_resp.json()["user_id"]

    resp = client.get(f"/v1/users/{user_id}/balance?token={token}")
    assert resp.status_code == 401


def test_header_token_still_accepted(client):
    """Control: Authorization-header auth is unchanged."""
    account = Account.create()
    reg_resp = _register_user(client, account)
    token = reg_resp.json()["session_token"]

    resp = client.get("/v1/users/me", headers=_bearer(token))
    assert resp.status_code == 200
    assert resp.json()["email"].endswith("@example.com")


def test_logout_ignores_query_param_token(client):
    """POST /v1/logout?token=<jwt> must not revoke — the param is dead."""
    account = Account.create()
    reg_resp = _register_user(client, account)
    token = reg_resp.json()["session_token"]

    out = client.post(f"/v1/logout?token={token}")
    assert out.status_code == 200

    # The JWT was never read from the URL — header auth still works.
    resp = client.get("/v1/users/me", headers=_bearer(token))
    assert resp.status_code == 200


def test_logout_header_token_still_revokes(client):
    """Control: header-borne logout still lands on the blocklist."""
    account = Account.create()
    reg_resp = _register_user(client, account)
    token = reg_resp.json()["session_token"]

    out = client.post("/v1/logout", headers=_bearer(token))
    assert out.status_code == 200

    resp = client.get("/v1/users/me", headers=_bearer(token))
    assert resp.status_code == 401
