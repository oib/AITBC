"""
Integration tests for agent and market interaction
"""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestAgentMarketIntegration:
    """Test integration between agent and market services"""

    @patch("coordinator_api.contexts.market.routers.market.MarketService")
    def test_agent_registers_in_market(self, mock_market_service_cls):
        """Test that an agent-provided offer appears in the market"""
        from coordinator_api.contexts.market.routers.market import router as market_router
        from coordinator_api.schemas import MarketOfferView
        from coordinator_api.storage import get_session

        mock_service = Mock()
        mock_market_service_cls.return_value = mock_service
        mock_service.list_offers.return_value = [
            MarketOfferView(
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
        app.include_router(market_router, prefix="/v1")
        app.dependency_overrides[get_session] = lambda: Mock()
        # Register the slowapi limiter used by the market router decorators
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.util import get_remote_address

        app.state.limiter = Limiter(key_func=get_remote_address)
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        try:
            client = TestClient(app)

            # List market offers (agent-provided compute appears here)
            response = client.get("/v1/market/offers")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["provider"] == "agent1"
        finally:
            app.dependency_overrides.clear()
