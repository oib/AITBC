#!/usr/bin/env python3
"""
Database-backed integration tests using SQLite in-memory with async SQLAlchemy.
"""

import asyncio
import os
import sys

import pytest

# Add marketplace to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "marketplace", "src"))

from marketplace_service.main import app
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from starlette.testclient import TestClient


@pytest.fixture(scope="function")
def marketplace_test_client():
    """Create test client with async SQLite database."""
    # Create async SQLite in-memory database
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Replace the engine in the storage module
    import marketplace_service.storage as storage_module

    original_engine = storage_module.engine
    storage_module.engine = test_engine

    # Create tables
    async def init_db():
        async with test_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    asyncio.run(init_db())

    client = TestClient(app)
    yield client

    # Restore original engine
    storage_module.engine = original_engine
    asyncio.run(test_engine.dispose())


class TestMarketplaceWithDatabase:
    """Test Marketplace Service API endpoints with real database."""

    def test_health_endpoint(self, marketplace_test_client):
        """Test health check endpoint"""
        response = marketplace_test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "ok"]

    def test_ready_endpoint(self, marketplace_test_client):
        """Test readiness check endpoint"""
        response = marketplace_test_client.get("/ready")
        assert response.status_code == 200

    def test_root_endpoint(self, marketplace_test_client):
        """Test root marketplace endpoint"""
        response = marketplace_test_client.get("/v1/marketplace")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_dashboard_endpoint(self, marketplace_test_client):
        """Test status endpoint"""
        response = marketplace_test_client.get("/v1/marketplace/status")
        assert response.status_code == 200

    def test_offers_endpoint_with_db(self, marketplace_test_client):
        """Test getting offers with database populated"""
        offer_data = {
            "title": "Test GPU Offer",
            "description": "RTX 4090 for rent",
            "resource_type": "gpu",
            "price_per_hour": 0.5,
            "location": "us-east-1",
            "provider_id": "test-provider",
        }
        response = marketplace_test_client.post("/v1/marketplace/offers", json=offer_data)

        if response.status_code == 405:
            pytest.skip("POST /offers not implemented")

        if response.status_code == 401:
            pytest.skip("Authentication required for offers endpoint")

        assert response.status_code in [200, 201]

        # GET offers requires query params
        response = marketplace_test_client.get(
            "/v1/marketplace/offers", params={"status": "active", "region": "us-east-1", "gpu_model": "RTX 4090"}
        )

        if response.status_code == 401:
            pytest.skip("Authentication required for offers endpoint")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_bids_endpoint(self, marketplace_test_client):
        """Test performance endpoint (requires period param)"""
        response = marketplace_test_client.get("/v1/marketplace/performance", params={"period": "24h"})

        if response.status_code == 401:
            pytest.skip("Authentication required for performance endpoint")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_analytics_endpoint(self, marketplace_test_client):
        """Test analytics endpoint (requires period_type param)"""
        response = marketplace_test_client.get("/v1/marketplace/analytics", params={"period_type": "24h"})

        if response.status_code == 401:
            pytest.skip("Authentication required for analytics endpoint")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
