"""SLA capacity endpoint pins — #1395 (POOLHUB-FAB-1).

routers/sla.py forecast/recommendations/alerts endpoints return hardcoded
constants labeled ``source: coordinator_api`` without calling the injected
BillingIntegration, and the alerts-configure endpoint reports "configured"
while persisting nothing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from poolhub.app.routers.sla import (
    configure_capacity_alerts,
    get_capacity_forecast,
    get_scaling_recommendations,
)


class TestCapacityForecast:
    @pytest.mark.xfail(
        strict=True,
        reason="endpoint returns hardcoded 1000/1500/'+50%' labeled source=coordinator_api without calling billing_integration; fix tracked in #1395",
    )
    def test_forecast_consults_billing_integration(self):
        billing = AsyncMock()
        result = get_capacity_forecast(billing_integration=billing, hours_ahead=24)
        assert billing.mock_calls, "forecast must not fabricate coordinator-api data"
        assert result.get("source") != "coordinator_api" or billing.mock_calls


class TestScalingRecommendations:
    @pytest.mark.xfail(
        strict=True,
        reason="endpoint returns a canned add_miners recommendation labeled source=coordinator_api; fix tracked in #1395",
    )
    def test_recommendations_consults_billing_integration(self):
        billing = AsyncMock()
        get_scaling_recommendations(billing_integration=billing)
        assert billing.mock_calls, "recommendations must not fabricate coordinator-api data"


class TestAlertConfiguration:
    @pytest.mark.xfail(
        strict=True,
        reason="POST /capacity/alerts/configure returns status=configured but persists nothing — a no-op success; fix tracked in #1395",
    )
    def test_configure_alerts_does_not_claim_unpersisted_success(self):
        result = configure_capacity_alerts(
            alert_config={"threshold_pct": 90},
            db=AsyncMock(),
            _={},
        )
        # A "configured" acknowledgement for state that was never stored is a
        # fabricated success. Until a store exists the endpoint must say so.
        assert result.get("persisted") is True or result.get("applied") is True or "error" in result
