"""Coverage for MatchingEngine spec compatibility (#1373 residual audit).

Pins the zero-denominator guard: buyer_value == 0 with a negative
seller_value made (buyer-seller)/buyer a ZeroDivisionError.
"""

from __future__ import annotations

import pytest

from coordinator_api.contexts.trading.services.trading_market.trading import MatchingEngine


@pytest.fixture
def engine() -> MatchingEngine:
    return MatchingEngine()


@pytest.mark.unit
def test_spec_compat_zero_buyer_value_no_crash(engine):
    # buyer spec 0 vs seller spec -1: buyer_value > seller_value holds and
    # the old code divided by buyer_value == 0.
    score = engine.calculate_specification_compatibility({"vram": 0}, {"vram": -1})
    assert score == 0.0


@pytest.mark.unit
def test_spec_compat_normal_cases(engine):
    assert engine.calculate_specification_compatibility({"a": 1}, {"a": 1}) == 100.0
    assert engine.calculate_specification_compatibility({"a": 5}, {"a": 10}) == 100.0
    # buyer 10 vs seller 5 -> penalized but nonzero denominator
    s = engine.calculate_specification_compatibility({"a": 10}, {"a": 5})
    assert 0.0 <= s < 100.0
