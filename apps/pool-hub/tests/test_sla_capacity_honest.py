"""Regression tests for #1395 (POOLHUB-FAB-1): the SLA capacity endpoints must
answer honestly.

/capacity/forecast, /capacity/recommendations and /capacity/alerts/configure
used to return hardcoded constants labeled ``source: coordinator_api`` (and a
"configured" acknowledgement for alert state that was never persisted). There
is no forecast engine, no coordinator-api forecast endpoint, and no
alert-config store, so all three now answer 501 — the same contract
edge/gpu use for defined-but-unimplemented routes. Real capacity data lives
at GET /v1/sla/capacity/snapshots.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from poolhub.app.routers.sla import (
    configure_capacity_alerts,
    get_capacity_forecast,
    get_scaling_recommendations,
)


def _detail(exc_info) -> str:
    return exc_info.value.detail


class TestCapacityEndpointsAreHonest501:
    def test_forecast_raises_501_not_fabricated_data(self):
        with pytest.raises(HTTPException) as exc_info:
            get_capacity_forecast(hours_ahead=24)
        assert exc_info.value.status_code == 501
        assert "not implemented" in _detail(exc_info)

    def test_recommendations_raises_501_not_fabricated_data(self):
        with pytest.raises(HTTPException) as exc_info:
            get_scaling_recommendations()
        assert exc_info.value.status_code == 501
        assert "not implemented" in _detail(exc_info)

    def test_alerts_configure_raises_501_not_fake_success(self):
        with pytest.raises(HTTPException) as exc_info:
            configure_capacity_alerts(alert_config={"threshold_pct": 90}, _={})
        assert exc_info.value.status_code == 501
        # The detail must not claim the config was applied or persisted.
        assert "configured" not in _detail(exc_info).lower() or "not implemented" in _detail(exc_info).lower()
