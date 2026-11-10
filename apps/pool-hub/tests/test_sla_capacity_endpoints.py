"""SLA capacity endpoint pins — #1395 (POOLHUB-FAB-1), now regression tests.

routers/sla.py forecast/recommendations/alerts endpoints used to return
hardcoded constants labeled ``source: coordinator_api`` without calling the
injected BillingIntegration, and the alerts-configure endpoint reported
"configured" while persisting nothing. With no forecast engine, no
coordinator-api forecast route and no alert-config store, the honest contract
is HTTP 501 — the same stub convention edge/gpu use. Real capacity data lives
at GET /v1/sla/capacity/snapshots. See also test_sla_capacity_honest.py.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from poolhub.app.routers.sla import (
    configure_capacity_alerts,
    get_capacity_forecast,
    get_scaling_recommendations,
)


class TestCapacityForecast:
    def test_forecast_is_honest_501_not_fabricated_data(self):
        with pytest.raises(HTTPException) as exc_info:
            get_capacity_forecast(hours_ahead=24)
        assert exc_info.value.status_code == 501
        assert "not implemented" in exc_info.value.detail


class TestScalingRecommendations:
    def test_recommendations_is_honest_501_not_fabricated_data(self):
        with pytest.raises(HTTPException) as exc_info:
            get_scaling_recommendations()
        assert exc_info.value.status_code == 501
        assert "not implemented" in exc_info.value.detail


class TestAlertConfiguration:
    def test_configure_alerts_is_honest_501_not_fake_success(self):
        with pytest.raises(HTTPException) as exc_info:
            configure_capacity_alerts(alert_config={"threshold_pct": 90}, _={})
        assert exc_info.value.status_code == 501
        # The detail must not claim the config was applied or persisted.
        detail = exc_info.value.detail.lower()
        assert "configured" not in detail or "not implemented" in detail
