"""Unit tests for aitbc.market.reference_price.

Pure derivation of the 1 AIT = 1 compute-hour reference price: BOM
amortization over the bookable lifetime plus wall-draw electricity. No I/O,
no float money.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from aitbc.market.reference_price import (
    DEFAULT_COMPONENTS,
    compute_reference,
)


def test_default_reference_matches_published_pin() -> None:
    b = compute_reference()
    assert b.hardware_total_eur == Decimal("1530")
    assert b.bookable_hours == Decimal("26280")  # 3 years * 8760, fully booked
    assert b.wear_eur_per_hour == Decimal("1530") / Decimal("26280")
    assert b.electricity_eur_per_hour == Decimal("0.1152")  # 384 W * 0.30 EUR/kWh
    assert b.cost_eur_per_hour == b.wear_eur_per_hour + b.electricity_eur_per_hour
    assert b.price_eur == Decimal("0.25")
    # Cost floor stays comfortably under the pin: the reference is a price,
    # not a cost passthrough.
    assert b.cost_eur_per_hour < b.price_eur
    assert b.margin_eur_per_hour == b.price_eur - b.cost_eur_per_hour
    assert b.margin_on_cost_pct == pytest.approx(44, abs=1)
    assert b.ait_per_eur == Decimal("4")


def test_utilization_below_full_booking_raises_wear() -> None:
    full = compute_reference()
    half = compute_reference(utilization=Decimal("0.5"))
    assert half.bookable_hours == full.bookable_hours / 2
    assert half.wear_eur_per_hour == full.wear_eur_per_hour * 2
    # Electricity is per wall-clock hour booked, unaffected by utilization.
    assert half.electricity_eur_per_hour == full.electricity_eur_per_hour


def test_custom_components_replace_bom() -> None:
    b = compute_reference(components={"H100": Decimal("25000")})
    assert b.hardware_total_eur == Decimal("25000")
    assert b.components == {"H100": Decimal("25000")}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"components": {}},
        {"components": {"GPU": Decimal("-1")}},
        {"lifespan_years": Decimal("0")},
        {"lifespan_years": Decimal("-1")},
        {"utilization": Decimal("0")},
        {"utilization": Decimal("1.5")},
        {"wall_watts": -1},
        {"eur_per_kwh": Decimal("-0.01")},
        {"price_eur": Decimal("0")},
    ],
)
def test_invalid_inputs_raise(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        compute_reference(**kwargs)


def test_zero_cost_has_no_margin_pct() -> None:
    b = compute_reference(components={"free": Decimal("0")}, wall_watts=0, eur_per_kwh=Decimal("0"))
    assert b.cost_eur_per_hour == 0
    assert b.margin_on_cost_pct is None


def test_to_dict_is_json_safe_and_float_free() -> None:
    payload = compute_reference().to_dict()
    encoded = json.dumps(payload)
    assert "0.25" in encoded
    for per_hour_value in payload["per_hour"].values():
        assert not isinstance(per_hour_value, float)
    names = [c["name"] for c in payload["components"]]
    assert names == list(DEFAULT_COMPONENTS)
