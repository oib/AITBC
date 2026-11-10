"""Property tests for the money/status pure functions from recent fixes.

Targets (batch v11 item 19 — hypothesis is already a dev dependency):

* ``aitbc.utils.decimal.to_decimal`` — the str-first Decimal conversion every
  money path funnels through; must never return a non-finite value.
* ``market_service.services.market_service._money_decimal`` — the
  finite + ``0 <= v <= MAX_PAYMENT_AMOUNT`` gate on booking/offer money
  fields (#1676-class NaN/bounds fixes).
* ``market_service.domain.offer_status`` — ``spellings_of`` /
  ``to_offer_status`` alias round-trip: every stored spelling of a state
  must map back to that state, and unknown words must raise.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from aitbc.utils.decimal import to_decimal
from market_service.domain.offer_status import OfferStatus, spellings_of, to_offer_status
from market_service.services.market_service import MAX_PAYMENT_AMOUNT, _money_decimal


class TestToDecimal:
    """to_decimal: finite in, finite out; Decimal passthrough is identity."""

    @given(st.decimals(allow_nan=False, allow_infinity=False))
    @settings(max_examples=300, deadline=None)
    def test_decimal_passthrough_is_identity(self, value: Decimal) -> None:
        assert to_decimal(value) == value
        assert to_decimal(value).is_finite()

    @given(st.integers(min_value=-(2**63), max_value=2**63))
    @settings(max_examples=200, deadline=None)
    def test_int_roundtrip(self, value: int) -> None:
        assert to_decimal(value) == Decimal(value)

    @given(st.floats(allow_nan=False, allow_infinity=False))
    @settings(max_examples=200, deadline=None)
    def test_float_uses_str_not_binary(self, value: float) -> None:
        # The whole point of str()-first: Decimal(str(0.1)) == Decimal("0.1"),
        # never the 0.1000...0555 binary expansion.
        assert to_decimal(value) == Decimal(str(value))

    @pytest.mark.parametrize("bad", ["nan", "NaN", "inf", "-inf", "Infinity", float("nan"), float("inf")])
    def test_non_finite_inputs_raise(self, bad) -> None:
        with pytest.raises(ValueError, match="non-finite|valid number|finite"):
            to_decimal(bad)

    @given(st.text(max_size=40))
    @settings(max_examples=200, deadline=None)
    def test_arbitrary_text_either_parses_finite_or_raises(self, text: str) -> None:
        try:
            result = to_decimal(text)
        except (ValueError, ArithmeticError):
            return
        assert result.is_finite()


class TestMoneyDecimal:
    """_money_decimal accepts exactly the finite in-range band."""

    @given(
        st.decimals(
            min_value=Decimal("0"),
            max_value=MAX_PAYMENT_AMOUNT,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=300, deadline=None)
    def test_in_range_accepted(self, value: Decimal) -> None:
        assert _money_decimal(value, "price") == value

    @given(st.decimals(max_value=Decimal("-0.000000000000000001"), allow_nan=False, allow_infinity=False))
    @settings(max_examples=100, deadline=None)
    def test_negative_rejected(self, value: Decimal) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            _money_decimal(value, "price")

    @given(st.decimals(min_value=MAX_PAYMENT_AMOUNT * 2, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100, deadline=None)
    def test_over_ceiling_rejected(self, value: Decimal) -> None:
        with pytest.raises(ValueError, match="must not exceed"):
            _money_decimal(value, "price")

    @pytest.mark.parametrize("bad", ["nan", float("nan"), float("inf"), "not-a-number", None, {}, []])
    def test_garbage_and_non_finite_rejected(self, bad) -> None:
        with pytest.raises(ValueError):
            _money_decimal(bad, "price")

    def test_boundary_values(self) -> None:
        assert _money_decimal(Decimal("0"), "price") == Decimal("0")
        assert _money_decimal(MAX_PAYMENT_AMOUNT, "price") == MAX_PAYMENT_AMOUNT
        with pytest.raises(ValueError):
            # +1 unit, not +1e-18: the default 28-digit Decimal context rounds
            # 1e15+1e-18 back to exactly MAX, so a sub-ulp overage is not a
            # meaningful "over ceiling" input.
            _money_decimal(MAX_PAYMENT_AMOUNT + Decimal("1"), "price")


class TestOfferStatusSpellings:
    """spellings_of/to_offer_status: the alias table is a consistent bijection
    onto stored words — every spelling of a state parses back to that state."""

    @given(st.sampled_from(list(OfferStatus)))
    @settings(max_examples=50, deadline=None)
    def test_spellings_round_trip(self, state: OfferStatus) -> None:
        spellings = spellings_of(state)
        assert spellings, f"{state} has no stored spellings"
        for word in spellings:
            assert to_offer_status(word) is state
            # Case/whitespace variants must resolve identically — stored rows
            # are not guaranteed normalized.
            assert to_offer_status(f"  {word.upper()} ") is state

    def test_alias_table_covers_every_state(self) -> None:
        for state in OfferStatus:
            assert spellings_of(state)

    @given(st.text(min_size=1, max_size=30))
    @settings(max_examples=200, deadline=None)
    def test_unknown_words_raise_value_error(self, word: str) -> None:
        assume(word.strip().lower() not in {w for s in OfferStatus for w in spellings_of(s)})
        with pytest.raises(ValueError, match="Unknown offer status"):
            to_offer_status(word)
