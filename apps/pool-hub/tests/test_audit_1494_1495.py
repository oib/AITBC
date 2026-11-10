"""Regression pins for #1494/#1495 — pool-hub 500-instead-of-4xx defects.

- #1494: _select_candidates float()/set() on unvalidated caller requirements
  JSON → 500; NaN minimum silently bypassed the hardware filter.
- #1495: MinerRegisterRequest.base_price reached Decimal()/Numeric(20,8)
  unvalidated → 500 on "abc", NaN/negative/oversized storable.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from poolhub.app.routers.match import _select_candidates
from poolhub.app.routers.miners import MinerRegisterRequest

_STATUS = SimpleNamespace(avg_latency_ms=None, queue_len=0)


def _miner() -> Any:
    return SimpleNamespace(
        miner_id="miner-1",
        addr="addr-1",
        proto="http",
        gpu_vram_gb=24.0,
        ram_gb=64.0,
        capabilities=[],
        region=None,
        base_price=Decimal("0.10"),
    )


class TestMalformedRequirementsAre400:
    """#1494 — bad requirements raise HTTPException 400, never a crash."""

    @pytest.mark.parametrize(
        "requirements",
        [
            {"min_vram_gb": "abc"},
            {"min_vram_gb": {}},
            {"min_vram_gb": []},
            {"min_vram_gb": True},
            {"min_ram_gb": "lots"},
            {"min_vram_gb": float("nan")},
            {"min_vram_gb": float("inf")},
            {"min_vram_gb": -1},
            {"capabilities_any": 5},
            {"capabilities_any": "cuda"},
            {"capabilities_any": {"a": 1}},
            {"capabilities_any": ["cuda", 3]},
        ],
    )
    def test_invalid_requirements_raise_400(self, requirements: dict[str, Any]):
        with pytest.raises(HTTPException) as excinfo:
            _select_candidates(requirements, {}, [(_miner(), _STATUS, 0.9)], 5)
        assert excinfo.value.status_code == 400

    def test_nan_minimum_cannot_bypass_filter(self):
        # Pre-fix: every `vram < NaN` is False, so a NaN minimum matched everyone.
        # Now NaN is rejected before the comparison is reached.
        with pytest.raises(HTTPException):
            _select_candidates({"min_vram_gb": float("nan")}, {}, [(_miner(), _STATUS, 0.9)], 5)

    def test_numeric_strings_and_ints_still_work(self):
        candidates = _select_candidates({"min_vram_gb": "8", "min_ram_gb": 16}, {}, [(_miner(), _STATUS, 0.9)], 5)
        assert len(candidates) == 1


class TestBasePriceValidation:
    """#1495 — base_price is validated at the model boundary (422, not 500)."""

    def _request(self, base_price: str) -> MinerRegisterRequest:
        return MinerRegisterRequest(miner_id="m", api_key="k", base_price=base_price)

    @pytest.mark.parametrize("bad", ["abc", "", "NaN", "Infinity", "-5", "1e30"])
    def test_invalid_prices_rejected(self, bad: str):
        with pytest.raises(ValidationError):
            self._request(bad)

    @pytest.mark.parametrize("good", ["0", "0.01", "999999999999.99999999", "1e2"])
    def test_valid_prices_accepted(self, good: str):
        assert self._request(good).base_price == good
