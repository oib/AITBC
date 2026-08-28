"""Regression tests for AIT <-> compute-unit conversion.

``ait_to_units`` is the boundary where a user's ``--amount`` becomes the integer the chain
settles, so a rounding error here is a rounding error in a transfer. It used to compute
``int(ait * UNITS_PER_AIT)`` on a float, which truncates on the low side whenever the product
lands just below an integer -- always in the sender's disfavour.
"""

from decimal import Decimal

import pytest
from aitbc.utils import UNITS_PER_AIT, ait_to_units, format_ait, units_to_ait


# (input, expected units). Each of these came out one unit short under the float
# implementation; they are the first few found by scanning 5-decimal inputs below 2 AIT.
TRUNCATED_UNDER_FLOAT = [
    ("0.00015", 5400),
    ("0.00030", 10800),
    ("0.00060", 21600),
    ("0.00089", 32040),
    ("0.00120", 43200),
    ("0.00153", 55080),
    ("0.00178", 64080),
    ("0.00207", 74520),
]


@pytest.mark.unit
@pytest.mark.parametrize(("amount", "expected"), TRUNCATED_UNDER_FLOAT)
def test_ait_to_units_does_not_lose_a_unit(amount: str, expected: int) -> None:
    assert ait_to_units(amount) == expected
    assert ait_to_units(Decimal(amount)) == expected
    # and from a float, because callers that still hold one must not regress either
    assert ait_to_units(float(amount)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(("amount", "expected"), TRUNCATED_UNDER_FLOAT)
def test_the_float_implementation_was_wrong(amount: str, expected: int) -> None:
    """Pins the defect itself, so the regression is recognisable if it comes back."""
    assert int(float(amount) * UNITS_PER_AIT) == expected - 1


@pytest.mark.unit
def test_round_trip_is_exact() -> None:
    for units in (0, 1, 360, 1809, 3600, 44280, 123456789):
        assert ait_to_units(units_to_ait(units)) == units


@pytest.mark.unit
def test_units_to_ait_returns_decimal() -> None:
    value = units_to_ait(1809)
    assert isinstance(value, Decimal)
    assert value == Decimal("0.00005025")


@pytest.mark.unit
def test_format_ait_accepts_what_ait_to_units_accepts() -> None:
    # local wallet files hold money as decimal strings; display must not care
    assert format_ait(36000000) == "1 AIT"
    assert format_ait("36000000") == "1 AIT"
    assert format_ait(Decimal("1809")) == "0.00005025 AIT"
    assert format_ait(1809.0) == "0.00005025 AIT"
    # smallest units must be visible, not rounded to "0.0000 AIT"
    assert format_ait(360000) == "0.01 AIT"
    assert format_ait(1) == "0.00000003 AIT"
