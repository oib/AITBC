"""Reference-price derivation for the 1 AIT = 1 compute-hour standard.

Pure data + pure functions: no I/O, no config, no network — the same contract
as ``hardware_catalog.py``. Consumed by ``scripts/ops/ait-reference-price.py``,
which prints the breakdown and emits ``website/reference.json``, the artifact
the exchange page renders under "How the reference is calculated".

The reference price answers: what does one booked hour on the island's
reference rig cost the operator? Two components:

* **Hardware wear** — the rig's bill of materials amortized over its bookable
  lifetime, ``bom_eur / (lifespan_years * HOURS_PER_YEAR * utilization)``.
  The canonical pin assumes a three-year replacement cycle, fully booked.
* **Electricity** — the node's whole draw at the wall times the tariff,
  ``wall_watts / 1000 * eur_per_kwh``.

Their sum is the cost floor. The published reference price
(``AIT_REFERENCE_PRICE_EUR`` in ``aitbc/oracles/price_oracle.py``) is that
cost plus the operator's margin — a pricing decision, not a protocol
constant. The RTX 4060 Ti reference rig is likewise the operator's choice:
an island re-anchors on its own hardware by re-running the script with its
own BOM and republishing the JSON + value-model doc.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

HOURS_PER_YEAR = 8760

# Canonical deployment assumptions (the node2 reference rig). wall watts is
# the whole-node AC draw registered on the live energy profile: (165 W GPU
# TBP + 120 W CPU + 60 W platform) / 0.90 PSU efficiency = 384 W.
DEFAULT_WALL_WATTS = 384
DEFAULT_EUR_PER_KWH = Decimal("0.30")
DEFAULT_LIFESPAN_YEARS = Decimal("3")
DEFAULT_UTILIZATION = Decimal("1")

# The published pin — keep in sync with AIT_REFERENCE_PRICE_EUR in
# aitbc/oracles/price_oracle.py.
DEFAULT_REFERENCE_PRICE_EUR = Decimal("0.25")

# Bill of materials for the reference rig (EUR, at purchase). These are the
# operator's numbers for the canonical island — estimates, adjustable via the
# script's --component flag.
DEFAULT_COMPONENTS: dict[str, Decimal] = {
    "RTX 4060 Ti 16GB": Decimal("450"),
    "Ryzen 9 5950X": Decimal("450"),
    "64 GB DDR4 RAM": Decimal("140"),
    "Motherboard": Decimal("180"),
    "PSU 750W 80+ Gold": Decimal("110"),
    "NVMe storage": Decimal("80"),
    "Case & cooling": Decimal("120"),
}

_PER_HOUR_QUANT = Decimal("0.000001")
_PCT_QUANT = Decimal("0.01")


@dataclass
class ReferenceBreakdown:
    """Full derivation of one reference compute-hour, exact Decimals."""

    components: dict[str, Decimal]
    hardware_total_eur: Decimal
    lifespan_years: Decimal
    utilization: Decimal
    bookable_hours: Decimal
    wall_watts: int
    eur_per_kwh: Decimal
    wear_eur_per_hour: Decimal
    electricity_eur_per_hour: Decimal
    cost_eur_per_hour: Decimal
    price_eur: Decimal
    margin_eur_per_hour: Decimal
    margin_on_cost_pct: Decimal | None
    ait_per_eur: Decimal

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe rendering: Decimal money as strings, never floats."""
        return {
            "model": {
                "lifespan_years": str(self.lifespan_years),
                "utilization": str(self.utilization),
                "bookable_hours": str(self.bookable_hours.quantize(Decimal("1"))),
                "wall_watts": self.wall_watts,
                "eur_per_kwh": str(self.eur_per_kwh),
                "reference_price_eur": str(self.price_eur),
                "ait_per_eur": str(self.ait_per_eur.quantize(Decimal("0.0001"))),
            },
            "components": [{"name": name, "cost_eur": str(cost)} for name, cost in self.components.items()],
            "hardware_total_eur": str(self.hardware_total_eur),
            "per_hour": {
                "hardware_wear_eur": str(self.wear_eur_per_hour.quantize(_PER_HOUR_QUANT)),
                "electricity_eur": str(self.electricity_eur_per_hour.quantize(_PER_HOUR_QUANT)),
                "cost_eur": str(self.cost_eur_per_hour.quantize(_PER_HOUR_QUANT)),
                "price_eur": str(self.price_eur),
                "margin_eur": str(self.margin_eur_per_hour.quantize(_PER_HOUR_QUANT)),
                "margin_on_cost_pct": (
                    str(self.margin_on_cost_pct.quantize(_PCT_QUANT)) if self.margin_on_cost_pct is not None else None
                ),
            },
        }


def compute_reference(
    *,
    components: dict[str, Decimal] | None = None,
    wall_watts: int = DEFAULT_WALL_WATTS,
    eur_per_kwh: Decimal = DEFAULT_EUR_PER_KWH,
    lifespan_years: Decimal = DEFAULT_LIFESPAN_YEARS,
    utilization: Decimal = DEFAULT_UTILIZATION,
    price_eur: Decimal = DEFAULT_REFERENCE_PRICE_EUR,
) -> ReferenceBreakdown:
    """Derive the per-hour cost floor and its margin against the pinned price.

    ``utilization`` is the booked fraction of the rig's lifetime: 1 means
    every hour between purchase and replacement is sold (fully booked), so
    wear per booked hour is ``bom / (years * 8760)``. Lower utilization
    raises wear per booked hour because the same BOM buys fewer sold hours.
    """
    components = dict(DEFAULT_COMPONENTS if components is None else components)
    if not components:
        raise ValueError("components must not be empty")
    for name, cost in components.items():
        if cost < 0:
            raise ValueError(f"component {name!r} has negative cost {cost}")
    if lifespan_years <= 0:
        raise ValueError(f"lifespan_years must be > 0, got {lifespan_years}")
    if not (Decimal("0") < utilization <= Decimal("1")):
        raise ValueError(f"utilization must be in (0, 1], got {utilization}")
    if wall_watts < 0:
        raise ValueError(f"wall_watts must be >= 0, got {wall_watts}")
    if eur_per_kwh < 0:
        raise ValueError(f"eur_per_kwh must be >= 0, got {eur_per_kwh}")
    if price_eur <= 0:
        raise ValueError(f"price_eur must be > 0, got {price_eur}")

    hardware_total = sum(components.values(), Decimal("0"))
    bookable_hours = lifespan_years * HOURS_PER_YEAR * utilization
    wear = hardware_total / bookable_hours
    electricity = Decimal(wall_watts) / 1000 * eur_per_kwh
    cost = wear + electricity
    margin = price_eur - cost
    return ReferenceBreakdown(
        components=components,
        hardware_total_eur=hardware_total,
        lifespan_years=lifespan_years,
        utilization=utilization,
        bookable_hours=bookable_hours,
        wall_watts=wall_watts,
        eur_per_kwh=eur_per_kwh,
        wear_eur_per_hour=wear,
        electricity_eur_per_hour=electricity,
        cost_eur_per_hour=cost,
        price_eur=price_eur,
        margin_eur_per_hour=margin,
        margin_on_cost_pct=(margin / cost * 100) if cost > 0 else None,
        ait_per_eur=Decimal("1") / price_eur,
    )
