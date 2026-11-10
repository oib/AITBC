"""Property tests for ``_coerce_remote_rating`` (MKT-RATING-1, #1446).

``sync_ratings_from_remote`` persists peer-supplied ratings; the coerce
helper is the single gate that keeps out-of-range, non-finite, boolean or
non-numeric values out of ``avg_rating``/``rating_count``. The sync-level
tests in ``apps/market/tests/test_rating_sync_validation.py`` pin example
rows; these properties pin the whole input space.
"""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from market_service.services.market_service import _coerce_remote_rating


@given(rating=st.floats(min_value=1.0, max_value=5.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=300)
def test_coerce_accepts_and_returns_finite_in_range_float(rating):
    """Any finite float inside [1.0, 5.0] comes back as a float in range."""
    result = _coerce_remote_rating(rating)
    assert isinstance(result, float)
    assert math.isfinite(result)
    assert 1.0 <= result <= 5.0
    assert result == rating


@given(rating=st.integers(min_value=1, max_value=5))
@settings(max_examples=100)
def test_coerce_accepts_integral_ratings(rating):
    """Integer ratings 1..5 are valid ratings (1 and 5 are inclusive bounds)."""
    assert _coerce_remote_rating(rating) == float(rating)


@pytest.mark.parametrize("bad", [0.0, 0.999999, 5.000001, 6.0, -1.0, 100.0])
def test_coerce_rejects_out_of_range_floats(bad):
    """Values outside [1.0, 5.0] raise ValueError — inclusive bounds."""
    with pytest.raises(ValueError):
        _coerce_remote_rating(bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_coerce_rejects_non_finite(bad):
    """NaN and infinities are not ratings."""
    with pytest.raises(ValueError):
        _coerce_remote_rating(bad)


@pytest.mark.parametrize("bad", [True, False])
def test_coerce_rejects_bools(bad):
    """bool is an int subclass but is never a rating — pinned explicitly."""
    with pytest.raises(ValueError):
        _coerce_remote_rating(bad)


@pytest.mark.parametrize("bad", ["abc", "", None, [4.5], {"r": 4.5}, object()])
def test_coerce_rejects_non_numeric(bad):
    """Non-numeric remote payloads raise ValueError, not TypeError."""
    with pytest.raises(ValueError):
        _coerce_remote_rating(bad)


@given(
    rating=st.text(max_size=20).filter(
        lambda s: s != "" and not s.replace(".", "", 1).replace("-", "", 1).replace("+", "", 1).isdigit()
    )
)
@settings(max_examples=100)
def test_coerce_never_returns_out_of_range(rating):
    """Whatever a string parses to, an accepted value is in [1.0, 5.0]."""
    try:
        result = _coerce_remote_rating(rating)
    except ValueError:
        return
    assert 1.0 <= result <= 5.0
