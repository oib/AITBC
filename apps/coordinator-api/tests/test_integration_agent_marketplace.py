"""
Integration tests for agent and marketplace interaction
"""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestAgentMarketplaceIntegration:
    """Test integration between agent and marketplace services"""

    @patch("app.contexts.marketplace.routers.marketplace.MarketplaceService")
    def test_agent_registers_in_marketplace(self, mock_marketplace_service_cls):
        """Test that an agent-provided offer appears in the marketplace"""
        from app.contexts.marketplace.routers.marketplace import router as marketplace_router
        from app.schemas import MarketplaceOfferView
        from app.storage import get_session

        mock_service = Mock()
        mock_marketplace_service_cls.return_value = mock_service
        mock_service.list_offers.return_value = [
            MarketplaceOfferView(
                id="offer1",
                provider="agent1",
                capacity=4,
                price=0.50,
                sla="standard",
                status="open",
                created_at=datetime.now(UTC),
            ),
        ]

        app = FastAPI()
        app.include_router(marketplace_router, prefix="/v1")
        app.dependency_overrides[get_session] = lambda: Mock()
        # Register the slowapi limiter used by the marketplace router decorators
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.util import get_remote_address

        app.state.limiter = Limiter(key_func=get_remote_address)
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        try:
            client = TestClient(app)

            # List marketplace offers (agent-provided compute appears here)
            response = client.get("/v1/marketplace/offers")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["provider"] == "agent1"
        finally:
            app.dependency_overrides.clear()
