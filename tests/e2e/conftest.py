"""
End-to-End Test Configuration
Fixtures and setup for E2E tests
"""

import json
import os
from collections.abc import AsyncGenerator, Generator
from decimal import Decimal
from typing import Any

import httpx
import pytest


@pytest.fixture(scope="session")
def coordinator_url() -> str:
    """Coordinator API URL"""
    return os.getenv("COORDINATOR_URL", "http://localhost:8203")


@pytest.fixture(scope="session")
def blockchain_url() -> str:
    """Blockchain RPC URL"""
    return os.getenv("BLOCKCHAIN_URL", "http://localhost:8202")


@pytest.fixture(scope="session")
def marketplace_url() -> str:
    """Marketplace URL"""
    return os.getenv("MARKETPLACE_URL", "http://localhost:8102")


@pytest.fixture(scope="session")
def api_key() -> str:
    """Test API key"""
    return os.getenv("TEST_API_KEY", "test-api-key")


@pytest.fixture(scope="function")
async def http_client() -> AsyncGenerator[httpx.AsyncClient]:
    """HTTP client for API calls"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
def sync_http_client() -> Generator[httpx.Client]:
    """Synchronous HTTP client for API calls"""
    with httpx.Client(timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
def test_data():
    """Test data fixture"""
    return {
        "test_user": {
            "user_id": "e2e-test-user-001",
            "email": "e2e-test@example.com",
            "wallet_address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C",
        },
        "test_job": {
            "job_type": "ai_inference",
            "parameters": {"model": "gpt-4", "prompt": "E2E test prompt", "max_tokens": 100},
        },
    }


@pytest.fixture(scope="session")
def service_health_check(coordinator_url, blockchain_url, marketplace_url):
    """Check if required services are healthy - non-blocking version"""
    import time

    def _check_service(url: str, service_name: str, max_retries: int = 2, health_path: str = "/v1/health") -> bool:
        """Check if a service is healthy - reduced retries to avoid hanging"""
        for i in range(max_retries):
            try:
                response = httpx.get(f"{url}{health_path}", timeout=2.0)
                if response.status_code == 200:
                    return True
            except Exception:
                if i < max_retries - 1:
                    time.sleep(1)
        # Don't skip, just return False to allow tests to continue
        return False

    # Check all services with appropriate health endpoints (non-blocking)
    _check_service(coordinator_url, "Coordinator API", health_path="/v1/health")
    _check_service(blockchain_url, "Blockchain Node", health_path="/health")
    _check_service(marketplace_url, "Marketplace", health_path="/health")

    return True


# ---------------------------------------------------------------------------
# Marketplace escrow flow fixtures
# ---------------------------------------------------------------------------


def _derive_wallet(private_key: str | None, name: str) -> dict[str, str]:
    if not private_key:
        pytest.skip(f"{name} not set")
    try:
        from aitbc.crypto.crypto import derive_ethereum_address
    except ImportError as exc:
        pytest.skip(f"eth-account/aitbc crypto not available: {exc}")
    try:
        address = derive_ethereum_address(private_key)
    except Exception as exc:
        pytest.skip(f"Could not derive address from {name}: {exc}")
    from aitbc.crypto.signature_recovery import canonical_address

    return {"private_key": private_key, "address": canonical_address(address)}


@pytest.fixture(scope="session")
def buyer_wallet() -> dict[str, str]:
    """Buyer wallet used to fund escrows (private key + canonical address)."""
    return _derive_wallet(os.getenv("E2E_BUYER_PRIVATE_KEY"), "E2E_BUYER_PRIVATE_KEY")


@pytest.fixture(scope="session")
def provider_wallet() -> dict[str, str]:
    """Provider/miner wallet (private key + canonical address)."""
    key = os.getenv("E2E_PROVIDER_PRIVATE_KEY")
    if not key:
        try:
            from eth_account import Account
        except ImportError as exc:
            pytest.skip(f"E2E_PROVIDER_PRIVATE_KEY not set and eth_account unavailable: {exc}")
        acct = Account.create()
        key = str(acct.key.hex())
    return _derive_wallet(key, "E2E_PROVIDER_PRIVATE_KEY")


@pytest.fixture(scope="session")
def provider_address(provider_wallet: dict[str, str]) -> str:
    """Canonical provider address for the marketplace offer and miner."""
    return provider_wallet["address"]


@pytest.fixture(scope="session")
def node_wallet_address() -> str:
    """Blockchain node wallet that receives ESCROW_LOCK funds."""
    address = os.getenv("E2E_NODE_WALLET_ADDRESS") or os.getenv("NODE_WALLET_ADDRESS") or os.getenv("GENESIS_WALLET_ADDRESS")
    if not address:
        pytest.skip("E2E_NODE_WALLET_ADDRESS / NODE_WALLET_ADDRESS / GENESIS_WALLET_ADDRESS not set")
    from aitbc.crypto.signature_recovery import canonical_address

    return canonical_address(address)


@pytest.fixture(scope="session")
def chain_id() -> str:
    """Chain ID used for ESCROW_LOCK transactions."""
    return os.getenv("E2E_CHAIN_ID", "ait-hub.aitbc.bubuit.net")


@pytest.fixture(scope="function")
def client_token(buyer_wallet: dict[str, str]) -> str:
    """JWT token with client role for the buyer wallet."""
    token = os.getenv("E2E_CLIENT_TOKEN")
    if token:
        return token
    jwt_secret = os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET_KEY") or os.getenv("E2E_JWT_SECRET")
    if not jwt_secret:
        pytest.skip("E2E_CLIENT_TOKEN or JWT_SECRET/E2E_JWT_SECRET not set")
    try:
        from aitbc.auth.jwt import JWTAuth
    except ImportError as exc:
        pytest.skip(f"aitbc.auth.jwt not importable: {exc}")
    payload = {"sub": buyer_wallet["address"], "role": "client", "type": "access"}
    try:
        return JWTAuth(secret=jwt_secret).create_token(payload)
    except Exception as exc:
        pytest.skip(f"Could not create client JWT: {exc}")


@pytest.fixture(scope="function")
async def marketplace_client(marketplace_url: str) -> AsyncGenerator[httpx.AsyncClient]:
    """HTTP client configured for the marketplace service."""
    async with httpx.AsyncClient(base_url=marketplace_url, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="function")
async def blockchain_client(blockchain_url: str) -> AsyncGenerator[httpx.AsyncClient]:
    """HTTP client configured for the blockchain node."""
    async with httpx.AsyncClient(base_url=blockchain_url, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="function")
async def coordinator_client(coordinator_url: str, client_token: str) -> AsyncGenerator[httpx.AsyncClient]:
    """HTTP client authenticated for coordinator client routes."""
    headers = {"Authorization": f"Bearer {client_token}"}
    async with httpx.AsyncClient(base_url=coordinator_url, headers=headers, timeout=60.0) as client:
        yield client


@pytest.fixture(scope="function")
async def miner_client(coordinator_url: str) -> AsyncGenerator[httpx.AsyncClient]:
    """HTTP client authenticated for coordinator miner routes."""
    miner_api_key = os.getenv("E2E_MINER_API_KEY")
    miner_token = os.getenv("E2E_MINER_TOKEN")
    jwt_secret = os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET_KEY") or os.getenv("E2E_JWT_SECRET")
    headers: dict[str, str] = {"X-Miner-ID": "e2e-test-miner"}
    if miner_token:
        headers["Authorization"] = f"Bearer {miner_token}"
    elif jwt_secret:
        try:
            from aitbc.auth.jwt import JWTAuth

            token = JWTAuth(secret=jwt_secret).create_token({"sub": "e2e-test-miner", "role": "miner", "type": "access"})
            headers["Authorization"] = f"Bearer {token}"
        except Exception as exc:
            pytest.skip(f"Could not create miner JWT: {exc}")
    elif miner_api_key:
        headers["X-Api-Key"] = miner_api_key
    else:
        pytest.skip("E2E_MINER_API_KEY, E2E_MINER_TOKEN, or JWT_SECRET not set")
    async with httpx.AsyncClient(base_url=coordinator_url, headers=headers, timeout=60.0) as client:
        yield client


@pytest.fixture(scope="function")
def sign_escrow_lock(
    buyer_wallet: dict[str, str],
    node_wallet_address: str,
    chain_id: str,
) -> Any:
    """Return a helper that signs a canonical ESCROW_LOCK transaction."""
    try:
        from aitbc.crypto.crypto import sign_transaction_hash
        from aitbc.crypto.signature_recovery import canonical_address
        from eth_utils import keccak
    except ImportError as exc:
        pytest.skip(f"Missing crypto dependencies for escrow signing: {exc}")

    def _sign(
        job_id: str,
        provider_address: str,
        amount_ait: str | Decimal,
        nonce: int,
        fee: int | None = None,
    ) -> str:
        amount_dec = Decimal(str(amount_ait))
        amount_seconds = int(amount_dec * 3600)
        if amount_seconds <= 0:
            amount_seconds = int(amount_dec)
        if fee is None:
            fee = max(36, amount_seconds // 100)

        tx = {
            "from": buyer_wallet["address"],
            "to": canonical_address(node_wallet_address),
            "amount": amount_seconds,
            "fee": fee,
            "nonce": nonce,
            "type": "ESCROW_LOCK",
            "chain_id": chain_id,
            "payload": {
                "action": "escrow_lock",
                "job_id": job_id,
                "provider": canonical_address(provider_address),
            },
        }
        canonical = json.dumps(tx, sort_keys=True, separators=(",", ":")).encode()
        signing_hash = "0x" + keccak(canonical).hex()
        return sign_transaction_hash(signing_hash, buyer_wallet["private_key"])

    return _sign


@pytest.fixture(scope="function")
async def require_healthy_services(coordinator_url, blockchain_url, marketplace_url) -> None:
    """Skip the current test if any required service is not healthy."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in [
            ("coordinator", coordinator_url),
            ("blockchain", blockchain_url),
            ("marketplace", marketplace_url),
        ]:
            try:
                resp = await client.get(f"{url}/health")
            except Exception as exc:
                pytest.skip(f"{name} service not reachable at {url}: {exc}")
            if resp.status_code != 200:
                pytest.skip(f"{name} service not healthy at {url}: {resp.status_code}")
