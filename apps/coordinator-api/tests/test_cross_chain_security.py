"""Tests for cross-chain wallet trust-boundary hardening (B3)."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from aitbc.auth import create_access_token
from eth_account import Account
from eth_keys import keys as eth_keys
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture
def admin_token():
    """Admin JWT for the routes under test, all of which require the admin role.

    This lived in `apps/coordinator-api/tests/conftest.py` until that file was rewritten
    wholesale for the v0.12.0 economics work, which took the fixture with it and left this
    file erroring at setup; the file was then deleted rather than the fixture restored
    (V23-71c). It sits here now because this is its only consumer, which is also how
    `test_routers_fhe.py` and `test_v120_economic_proposals.py` do it.
    """
    return create_access_token("test-admin", "admin")


@pytest.fixture
def cross_chain_db(client, monkeypatch):
    """Provide an isolated in-memory DB for cross-chain tests and patch settings."""
    from coordinator_api.config import settings
    from coordinator_api.main import app
    from coordinator_api.storage.db import get_session

    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # A plain `create_all`. This used to be a `while True` that swallowed "already exists"
    # OperationalErrors and retried, because two services' models shared one global MetaData
    # and the `extend_existing` merge appended duplicate `Index` objects, so `create_all`
    # emitted the same CREATE INDEX twice. Each service owns its metadata now (V23-72, V23-74).
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _get_session_override
    monkeypatch.setattr(settings, "wallet_encryption_password", "strong-test-wallet-encryption-password")
    try:
        yield engine
    finally:
        app.dependency_overrides.pop(get_session, None)


def _auth_header(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _mock_factory():
    """Return a patched WalletAdapterFactory that yields async mocks."""
    from coordinator_api.agent_identity.wallet_adapter_enhanced import SecurityLevel

    class _MockFactory:
        @staticmethod
        def create_adapter(chain_id, rpc_url, security_level=SecurityLevel.MEDIUM):
            adapter = AsyncMock()
            adapter.validate_address = AsyncMock(return_value=True)
            adapter.get_balance = AsyncMock(return_value={"address": "0x", "eth_balance": 1.0})
            adapter.execute_transaction = AsyncMock(return_value={"transaction_hash": "0x" + "00" * 32})
            adapter.get_transaction_history = AsyncMock(return_value=[])
            adapter.secure_sign_message = AsyncMock(return_value={"signature": "0x" + "00" * 65})
            adapter.verify_signature = AsyncMock(return_value=True)
            return adapter

        @staticmethod
        def get_supported_chains():
            return [1, 137, 56, 42161, 10, 43114, 1000, 1001]

    return _MockFactory


def test_create_enhanced_wallet_redacts_and_persists(client, cross_chain_db, admin_token, monkeypatch):
    """Wallet creation persists keys server-side and never returns them."""
    from coordinator_api.contexts.cross_chain.routers import cross_chain_integration

    monkeypatch.setattr(cross_chain_integration, "WalletAdapterFactory", _mock_factory())

    account = Account.create()
    response = client.post(
        "/v1/cross-chain/wallets/create",
        params={"owner_address": account.address, "chain_id": 1},
        json={"security_config": {}},
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "address" in data
    assert "public_key" in data
    assert "private_key" not in data
    assert "encrypted_private_key" not in data
    assert "security_config" not in data


def test_create_enhanced_wallet_requires_encryption_password(client, cross_chain_db, admin_token, monkeypatch):
    """Wallet creation fails when the server-side encryption password is missing."""
    from coordinator_api.config import settings
    from coordinator_api.contexts.cross_chain.routers import cross_chain_integration

    monkeypatch.setattr(cross_chain_integration, "WalletAdapterFactory", _mock_factory())
    monkeypatch.setattr(settings, "wallet_encryption_password", "")

    account = Account.create()
    response = client.post(
        "/v1/cross-chain/wallets/create",
        params={"owner_address": account.address, "chain_id": 1},
        json={"security_config": {}},
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 400
    assert "encryption password" in response.json()["detail"].lower()


def test_durable_wallet_recovery(client, cross_chain_db, admin_token, monkeypatch):
    """A created wallet can be recovered from encrypted storage with the server password."""
    from coordinator_api.config import settings
    from coordinator_api.contexts.cross_chain.routers import cross_chain_integration
    from coordinator_api.contexts.wallet.services.secure_wallet_service import SecureWalletService

    monkeypatch.setattr(cross_chain_integration, "WalletAdapterFactory", _mock_factory())

    account = Account.create()
    create_resp = client.post(
        "/v1/cross-chain/wallets/create",
        params={"owner_address": account.address, "chain_id": 1},
        json={"security_config": {}},
        headers=_auth_header(admin_token),
    )
    wallet_id = create_resp.json()["id"]

    with Session(cross_chain_db) as session:
        service = SecureWalletService(session, None)
        keys = asyncio.run(service.get_wallet_with_private_key(wallet_id, settings.wallet_encryption_password))
        assert keys["address"].lower() == create_resp.json()["address"].lower()
        assert len(keys["private_key"]) == 64


def test_get_wallet_balance_rejects_private_network_rpc(client, cross_chain_db, admin_token):
    """A chain allowlist entry pointing to a private IP is rejected."""
    from coordinator_api.contexts.wallet.domain.wallet import AgentWallet, NetworkConfig, NetworkType

    account = Account.create()
    with Session(cross_chain_db) as session:
        wallet = AgentWallet(
            agent_id="test-admin",
            address=account.address.lower(),
            public_key=eth_keys.PrivateKey(account.key).public_key.to_hex(),
            wallet_type="eoa",
        )
        session.add(wallet)
        config = NetworkConfig(
            chain_id=1,
            name="Ethereum",
            network_type=NetworkType.EVM,
            rpc_url="http://169.254.169.254/latest",
            explorer_url="https://example.com",
            native_currency_symbol="ETH",
        )
        session.add(config)
        session.commit()

    response = client.get(
        f"/v1/cross-chain/wallets/{account.address.lower()}/balance",
        params={"chain_id": 1},
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 400
    assert "private network" in response.json()["detail"].lower()


def test_get_wallet_balance_uses_server_allowlist(client, cross_chain_db, admin_token, monkeypatch):
    """Balance queries use the server-resolved RPC URL and enforce wallet ownership."""
    from coordinator_api.contexts.cross_chain.routers import cross_chain_integration
    from coordinator_api.contexts.wallet.domain.wallet import AgentWallet, NetworkConfig, NetworkType

    monkeypatch.setattr(cross_chain_integration, "WalletAdapterFactory", _mock_factory())

    account = Account.create()
    with Session(cross_chain_db) as session:
        wallet = AgentWallet(
            agent_id="test-admin",
            address=account.address.lower(),
            public_key=eth_keys.PrivateKey(account.key).public_key.to_hex(),
            wallet_type="eoa",
        )
        session.add(wallet)
        config = NetworkConfig(
            chain_id=1,
            name="Ethereum",
            network_type=NetworkType.EVM,
            rpc_url="http://test-rpc.example.com",
            explorer_url="https://example.com",
            native_currency_symbol="ETH",
        )
        session.add(config)
        session.commit()

    response = client.get(
        f"/v1/cross-chain/wallets/{account.address.lower()}/balance",
        params={"chain_id": 1},
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 200
    assert "eth_balance" in response.json()


def test_get_wallet_balance_ownership_enforced(client, cross_chain_db, admin_token, monkeypatch):
    """One agent cannot read another agent's wallet balance."""
    from coordinator_api.contexts.cross_chain.routers import cross_chain_integration
    from coordinator_api.contexts.wallet.domain.wallet import AgentWallet

    monkeypatch.setattr(cross_chain_integration, "WalletAdapterFactory", _mock_factory())

    account = Account.create()
    with Session(cross_chain_db) as session:
        wallet = AgentWallet(
            agent_id="other-agent",
            address=account.address.lower(),
            public_key=eth_keys.PrivateKey(account.key).public_key.to_hex(),
            wallet_type="eoa",
        )
        session.add(wallet)
        session.commit()

    response = client.get(
        f"/v1/cross-chain/wallets/{account.address.lower()}/balance",
        params={"chain_id": 1},
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 403


def test_rpc_url_query_param_ignored(client, cross_chain_db, admin_token, monkeypatch):
    """Client-supplied rpc_url query parameters are ignored; the server-resolved URL is used."""
    from coordinator_api.contexts.cross_chain.routers import cross_chain_integration
    from coordinator_api.contexts.wallet.domain.wallet import AgentWallet, NetworkConfig, NetworkType

    monkeypatch.setattr(cross_chain_integration, "WalletAdapterFactory", _mock_factory())

    account = Account.create()
    with Session(cross_chain_db) as session:
        wallet = AgentWallet(
            agent_id="test-admin",
            address=account.address.lower(),
            public_key=eth_keys.PrivateKey(account.key).public_key.to_hex(),
            wallet_type="eoa",
        )
        session.add(wallet)
        config = NetworkConfig(
            chain_id=1,
            name="Ethereum",
            network_type=NetworkType.EVM,
            rpc_url="http://test-rpc.example.com",
            explorer_url="https://example.com",
            native_currency_symbol="ETH",
        )
        session.add(config)
        session.commit()

    response = client.get(
        f"/v1/cross-chain/wallets/{account.address.lower()}/balance",
        params={"chain_id": 1, "rpc_url": "http://attacker.internal/"},
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 200
    assert "eth_balance" in response.json()


def test_execute_transaction_rejects_private_key_in_data(client, cross_chain_db, admin_token, monkeypatch):
    """Transaction payloads containing a private key are rejected before any signing."""
    from coordinator_api.contexts.cross_chain.routers import cross_chain_integration

    monkeypatch.setattr(cross_chain_integration, "WalletAdapterFactory", _mock_factory())

    account = Account.create()
    response = client.post(
        f"/v1/cross-chain/wallets/{account.address.lower()}/transactions",
        params={"to_address": Account.create().address, "amount": 1.0, "chain_id": 1},
        json={"private_key": "0x" + "00" * 32},
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 400
    assert "private key" in response.json()["detail"].lower()


def test_sign_message_uses_server_stored_key(client, cross_chain_db, admin_token, monkeypatch):
    """Signing uses the persisted encrypted key, not a client-provided private key."""
    from coordinator_api.contexts.cross_chain.routers import cross_chain_integration

    monkeypatch.setattr(cross_chain_integration, "WalletAdapterFactory", _mock_factory())

    owner = Account.create()
    create_resp = client.post(
        "/v1/cross-chain/wallets/create",
        params={"owner_address": owner.address, "chain_id": 1},
        json={"security_config": {}},
        headers=_auth_header(admin_token),
    )
    wallet_address = create_resp.json()["address"]

    response = client.post(
        f"/v1/cross-chain/wallets/{wallet_address}/sign",
        params={"message": "hello", "chain_id": 1},
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 200
    assert "signature" in response.json()


def test_verify_signature_does_not_require_private_key(client, cross_chain_db, admin_token, monkeypatch):
    """Signature verification is a public operation and never touches a private key."""
    from coordinator_api.contexts.cross_chain.routers import cross_chain_integration

    monkeypatch.setattr(cross_chain_integration, "WalletAdapterFactory", _mock_factory())

    account = Account.create()
    response = client.post(
        "/v1/cross-chain/wallets/verify-signature",
        params={
            "message": "hello",
            "signature": "0x" + "00" * 65,
            "address": account.address,
            "chain_id": 1,
        },
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True
