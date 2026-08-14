"""B4: exact monetary semantics regression tests.

Verifies that wallet/cross-chain monetary values are handled as integer atomic
units or Decimal, that float inputs are rejected, and that fee/price arithmetic
stays exact through common conversions.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from coordinator_api.contexts.wallet.services.money import (
    from_atomic_units,
    parse_decimal,
    to_atomic_units,
    validate_positive_amount,
)


def test_parse_decimal_rejects_float() -> None:
    """Float inputs must be refused to avoid binary floating-point loss."""
    with pytest.raises(TypeError, match="Float"):
        parse_decimal(1.1)
    with pytest.raises(TypeError, match="Float"):
        parse_decimal(1.0)


def test_parse_decimal_accepts_decimal_string_int() -> None:
    assert parse_decimal(Decimal("1.5")) == Decimal("1.5")
    assert parse_decimal("1.5") == Decimal("1.5")
    assert parse_decimal("1.0") == Decimal("1")
    assert parse_decimal(1) == Decimal("1")


def test_to_atomic_units_exact_conversion() -> None:
    """Decimal human amounts convert to integer atomic units without float loss."""
    assert to_atomic_units("1.0") == 10**18
    assert to_atomic_units(Decimal("0.1")) == 10**17
    assert to_atomic_units(Decimal("0.000000000000000001")) == 1
    assert to_atomic_units("123456789.123456789012345678") == int(Decimal("123456789.123456789012345678") * 10**18)


def test_to_atomic_units_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        to_atomic_units("0")
    with pytest.raises(ValueError, match="positive"):
        to_atomic_units("-1")


def test_to_atomic_units_rejects_float() -> None:
    with pytest.raises(TypeError, match="Float"):
        to_atomic_units(1.0)


def test_from_atomic_units_round_trip() -> None:
    """Atomic units round-trip through Decimal."""
    for decimals in (18, 9, 0):
        for atomic in (0, 1, 10**decimals, 10**decimals // 2, 10**18 + 1):
            dec = from_atomic_units(atomic, decimals=decimals)
            assert dec == Decimal(atomic) / (Decimal(10) ** decimals)


def test_from_atomic_units_rejects_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        from_atomic_units(-1)


def test_validate_positive_amount_bounds() -> None:
    assert validate_positive_amount("10", Decimal("100")) == Decimal("10")
    with pytest.raises(ValueError, match="maximum"):
        validate_positive_amount("101", Decimal("100"))
    with pytest.raises(ValueError, match="positive"):
        validate_positive_amount("0")
