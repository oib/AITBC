"""Regression tests for AIT <-> compute-second conversion.

``ait_to_seconds`` is the boundary where a user's ``--amount`` becomes the integer the chain
settles, so a rounding error here is a rounding error in a transfer. It used to compute
``int(ait * 3600)`` on a float, which truncates on the low side whenever the product lands
just below an integer -- always in the sender's disfavour.
"""

from decimal import Decimal

import pytest
from aitbc.utils import ait_to_seconds, format_ait, seconds_to_ait


# (input, expected seconds). Each of these came out one second short under the float
# implementation; they are the first few found by scanning 5-decimal inputs below 2 AIT.
TRUNCATED_UNDER_FLOAT = [
    ("0.28250", 1017),
    ("0.50250", 1809),
    ("0.50750", 1827),
    ("0.51250", 1845),
    ("0.51750", 1863),
    ("0.52250", 1881),
    ("0.56500", 2034),
    ("1.00500", 3618),
]


@pytest.mark.unit
@pytest.mark.parametrize(("amount", "expected"), TRUNCATED_UNDER_FLOAT)
def test_ait_to_seconds_does_not_lose_a_second(amount: str, expected: int) -> None:
    assert ait_to_seconds(amount) == expected
    assert ait_to_seconds(Decimal(amount)) == expected
    # and from a float, because callers that still hold one must not regress either
    assert ait_to_seconds(float(amount)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(("amount", "expected"), TRUNCATED_UNDER_FLOAT)
def test_the_float_implementation_was_wrong(amount: str, expected: int) -> None:
    """Pins the defect itself, so the regression is recognisable if it comes back."""
    assert int(float(amount) * 3600) == expected - 1


@pytest.mark.unit
def test_round_trip_is_exact() -> None:
    for seconds in (0, 1, 360, 1809, 3600, 44280, 123456789):
        assert ait_to_seconds(seconds_to_ait(seconds)) == seconds


@pytest.mark.unit
def test_seconds_to_ait_returns_decimal() -> None:
    value = seconds_to_ait(1809)
    assert isinstance(value, Decimal)
    assert value == Decimal("0.5025")


@pytest.mark.unit
def test_format_ait_accepts_what_ait_to_seconds_accepts() -> None:
    # local wallet files hold money as decimal strings; display must not care
    assert format_ait(3600) == "1 AIT"
    assert format_ait("3600") == "1 AIT"
    assert format_ait(Decimal("1809")) == "0.5025 AIT"
    assert format_ait(1809.0) == "0.5025 AIT"
