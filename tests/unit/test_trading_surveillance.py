"""Unit tests for the coordinator trading surveillance service."""

from __future__ import annotations

import pytest

from coordinator_api.contexts.security.services.trading_surveillance import TradingSurveillance


@pytest.mark.asyncio
async def test_trading_surveillance_mock_data_is_deterministic() -> None:
    """Seeded surveillance instances produce deterministic mock data."""
    first = await TradingSurveillance(seed=42)._get_trading_data("AIT")
    second = await TradingSurveillance(seed=42)._get_trading_data("AIT")
    assert first["order_cancellations"] == second["order_cancellations"]
    assert first["total_orders"] == second["total_orders"]
    assert first["current_volume"] == second["current_volume"]
    assert 0 <= first["order_cancellations"]
    assert 0 <= first["total_orders"]
    assert len(first["volume_history"]) == 60
    assert len(first["user_distribution"]) == 100
