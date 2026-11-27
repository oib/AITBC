"""Regression pins for the pool-hub audit batch (#1398).

- #1398: _select_candidates treated gpu_vram_gb=0.0/ram_gb=0.0 as "no
  constraint" via a truthiness guard, so a GPU-less miner satisfied any
  positive minimum.

(The #1400 billing-usage pins lived here too; the whole billing surface —
endpoints, scheduler flag and BillingIntegration service — was removed in
#3077 because coordinator-api serves no /api/billing/* routes.)
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from poolhub.app.routers.match import _select_candidates


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
