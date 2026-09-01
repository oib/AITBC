"""Tests for the computation_correct ZK gate health check."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from coordinator_api.contexts.zk_applications.services.zk_health import run_computation_correct_health_check


@pytest.mark.asyncio
async def test_health_check_reports_disabled_when_zk_off():
    with patch("coordinator_api.contexts.zk_applications.services.zk_health.zk_proof_service") as mock_svc:
        mock_svc.is_enabled.return_value = False
        result = await run_computation_correct_health_check()
    assert result["computation_correct_healthy"] is False
    assert result["status"] == "disabled"


@pytest.mark.asyncio
async def test_health_check_reports_unhealthy_without_receipt_model_circuit():
    with patch("coordinator_api.contexts.zk_applications.services.zk_health.zk_proof_service") as mock_svc:
        mock_svc.is_enabled.return_value = True
        mock_svc.available_circuits = {}
        result = await run_computation_correct_health_check()
    assert result["computation_correct_healthy"] is False
    assert result["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_health_check_happy_path():
    """If the service and circuit are available, the health check runs both probes."""
    if os.getenv("COORDINATOR_ENABLE_ZK_VERIFICATION", "").lower() != "true":
        pytest.skip("ZK verification is not enabled in this environment")
    result = await run_computation_correct_health_check()
    # The live result depends on whether the circuits are actually deployed.
    assert "computation_correct_healthy" in result
    assert "good_probe" in result
    assert "bad_probe" in result
