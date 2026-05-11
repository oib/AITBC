"""
End-to-End Test Configuration
Fixtures and setup for E2E tests
"""

import pytest
import httpx
import os
from typing import AsyncGenerator, Generator


@pytest.fixture(scope="session")
def coordinator_url() -> str:
    """Coordinator API URL"""
    return os.getenv("COORDINATOR_URL", "http://localhost:8011")


@pytest.fixture(scope="session")
def blockchain_url() -> str:
    """Blockchain RPC URL"""
    return os.getenv("BLOCKCHAIN_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def marketplace_url() -> str:
    """Marketplace URL"""
    return os.getenv("MARKETPLACE_URL", "http://localhost:8102")


@pytest.fixture(scope="session")
def api_key() -> str:
    """Test API key"""
    return os.getenv("TEST_API_KEY", "test-api-key")


@pytest.fixture(scope="function")
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTP client for API calls"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
def sync_http_client() -> Generator[httpx.Client, None, None]:
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
            "wallet_address": "ait1e2etestuser001"
        },
        "test_job": {
            "job_type": "ai_inference",
            "parameters": {
                "model": "gpt-4",
                "prompt": "E2E test prompt",
                "max_tokens": 100
            }
        }
    }


@pytest.fixture(scope="session")
def service_health_check(coordinator_url, blockchain_url, marketplace_url):
    """Check if required services are healthy"""
    import time
    
    def _check_service(url: str, service_name: str, max_retries: int = 30, health_path: str = "/v1/health") -> bool:
        """Check if a service is healthy"""
        for i in range(max_retries):
            try:
                response = httpx.get(f"{url}{health_path}", timeout=5.0)
                if response.status_code == 200:
                    return True
            except Exception:
                if i < max_retries - 1:
                    time.sleep(2)
        pytest.skip(f"{service_name} not available at {url}")
        return False
    
    # Check all services with appropriate health endpoints
    _check_service(coordinator_url, "Coordinator API", health_path="/v1/health")
    _check_service(blockchain_url, "Blockchain Node", health_path="/health")
    _check_service(marketplace_url, "Marketplace", health_path="/health")
    
    return True
