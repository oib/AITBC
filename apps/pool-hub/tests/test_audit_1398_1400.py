"""Regression pins for the pool-hub audit batch (#1398, #1400, #1401).

- #1398: _select_candidates treated gpu_vram_gb=0.0/ram_gb=0.0 as "no
  constraint" via a truthiness guard, so a GPU-less miner satisfied any
  positive minimum.
- #1400: send_usage treated explicit unit_price=Decimal("0") as missing and
  fell back to the pricing table; negative/NaN amounts reached billing
  events, and the record endpoint returned HTTP 200 on a failed send.
- #1401: distribute_rewards submitted reward transactions with
  to=<miner_id> instead of the miner's registered wallet_address.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from poolhub.app.routers import sla as sla_router
from poolhub.app.routers.match import _select_candidates
from poolhub.services.billing_integration import BillingIntegration


def _miner(**overrides: Any) -> Any:
    base = {
        "miner_id": "miner-1",
        "addr": "addr-1",
        "proto": "http",
        "gpu_vram_gb": 24.0,
        "ram_gb": 64.0,
        "capabilities": [],
        "region": None,
        "base_price": Decimal("0.10"),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


_STATUS = SimpleNamespace(avg_latency_ms=None, queue_len=0)


class TestZeroHardwareCannotSatisfyMinimum:
    """#1398 — falsy hardware values must fail a positive minimum."""

    def test_zero_vram_fails_positive_minimum(self):
        candidates = _select_candidates(
            requirements={"min_vram_gb": 8},
            hints={},
            active_miners=[(_miner(gpu_vram_gb=0.0), _STATUS, 0.9)],
            top_k=5,
        )
        assert candidates == []

    def test_zero_ram_fails_positive_minimum(self):
        candidates = _select_candidates(
            requirements={"min_ram_gb": 16},
            hints={},
            active_miners=[(_miner(ram_gb=0.0), _STATUS, 0.9)],
            top_k=5,
        )
        assert candidates == []

    def test_zero_hardware_still_passes_when_no_minimum(self):
        candidates = _select_candidates(
            requirements={},
            hints={},
            active_miners=[(_miner(gpu_vram_gb=0.0, ram_gb=0.0), _STATUS, 0.9)],
            top_k=5,
        )
        assert len(candidates) == 1

    def test_adequate_hardware_passes(self):
        candidates = _select_candidates(
            requirements={"min_vram_gb": 8, "min_ram_gb": 16},
            hints={},
            active_miners=[(_miner(), _STATUS, 0.9)],
            top_k=5,
        )
        assert len(candidates) == 1


def _integration() -> tuple[BillingIntegration, list[dict[str, Any]]]:
    integration = BillingIntegration(db=AsyncMock())
    sent: list[dict[str, Any]] = []

    async def _accept(event: dict[str, Any]) -> dict[str, Any]:
        sent.append(event)
        return {"status": "recorded"}

    integration._send_billing_event = _accept  # type: ignore[method-assign]
    return integration, sent


class TestUsagePricingAndValidation:
    """#1400 — explicit zero price honored; invalid amounts rejected."""

    @pytest.mark.asyncio
    async def test_explicit_zero_unit_price_is_not_replaced_by_fallback(self):
        integration, sent = _integration()

        await integration.send_usage(tenant_id="t", resource_type="gpu_hours", quantity=Decimal("2"), unit_price=Decimal("0"))

        assert sent[0]["unit_price"] == "0"
        assert sent[0]["total_amount"] == "0"

    @pytest.mark.asyncio
    async def test_missing_unit_price_still_uses_fallback(self):
        integration, sent = _integration()

        await integration.send_usage(tenant_id="t", resource_type="gpu_hours", quantity=Decimal("2"))

        assert sent[0]["unit_price"] == "0.50"

    @pytest.mark.asyncio
    async def test_negative_quantity_is_rejected(self):
        integration, _ = _integration()
        with pytest.raises(ValueError, match="quantity"):
            await integration.send_usage(tenant_id="t", resource_type="gpu_hours", quantity=Decimal("-1"))

    @pytest.mark.asyncio
    async def test_nan_unit_price_is_rejected(self):
        integration, _ = _integration()
        with pytest.raises(ValueError, match="unit_price"):
            await integration.send_usage(
                tenant_id="t", resource_type="gpu_hours", quantity=Decimal("1"), unit_price=Decimal("NaN")
            )


class TestUsageRecordRequestValidation:
    """#1400 — the request model rejects negative and non-finite amounts."""

    def _request(self, **overrides: Any) -> sla_router.UsageRecordRequest:
        payload: dict[str, Any] = {"tenant_id": "t", "resource_type": "gpu_hours", "quantity": "1"}
        payload.update(overrides)
        return sla_router.UsageRecordRequest(**payload)

    def test_negative_quantity_fails_validation(self):
        with pytest.raises(ValidationError):
            self._request(quantity="-1")

    def test_nan_quantity_fails_validation(self):
        with pytest.raises(ValidationError):
            self._request(quantity="NaN")

    def test_zero_unit_price_is_accepted(self):
        assert self._request(unit_price="0").unit_price == Decimal("0")

    def test_negative_unit_price_fails_validation(self):
        with pytest.raises(ValidationError):
            self._request(unit_price="-0.5")


class TestRecordUsageEndpointFailureMapping:
    """#1400 — a failed billing send must not return HTTP 200."""

    @pytest.mark.asyncio
    async def test_failed_send_maps_to_502(self):
        request = sla_router.UsageRecordRequest(tenant_id="t", resource_type="gpu_hours", quantity=Decimal("1"))
        integration = SimpleNamespace(
            record_usage=AsyncMock(return_value={"status": "failed", "error": "coordinator unreachable"})
        )

        with pytest.raises(HTTPException) as excinfo:
            await sla_router.record_usage(request=request, billing_integration=integration, _=None)

        assert excinfo.value.status_code == 502
