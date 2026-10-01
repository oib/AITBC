#!/usr/bin/env python3
"""Derive the 1 AIT = 1 compute-hour reference price from hardware + power.

Computes the cost floor of one booked hour on the island's reference rig —
bill-of-materials wear amortized over the bookable lifetime plus whole-node
electricity — and reports it against the pinned reference price. With
``--write-json`` it emits ``website/reference.json``, the artifact the
exchange page renders under "How the reference is calculated".

The RTX 4060 Ti rig in the defaults is the canonical island's choice, not a
protocol constant: pass ``--reset-components`` plus your own ``--component``
entries to re-anchor on different hardware, then republish the JSON, update
``AIT_REFERENCE_PRICE_EUR`` in ``aitbc/oracles/price_oracle.py`` and the
table in ``docs/getting-started/ait-value-model.md``.

Usage (any repo checkout, venv or system python3 — no third-party deps):

    venv/bin/python scripts/ops/ait-reference-price.py
    venv/bin/python scripts/ops/ait-reference-price.py --write-json website/reference.json
    venv/bin/python scripts/ops/ait-reference-price.py --component "H100=25000" \
        --reset-components --component "EPYC=3000" --wall-watts 900 --json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

# reference_price.py is pure stdlib, but ``import aitbc.market...`` would run
# aitbc/__init__.py, which pulls fastapi and friends. Load the module file
# directly so this script runs on a bare checkout with system python3.
_spec = importlib.util.spec_from_file_location("aitbc_market_reference_price", _REPO / "aitbc/market/reference_price.py")
assert _spec is not None and _spec.loader is not None
_rp = importlib.util.module_from_spec(_spec)
# @dataclass resolves the class's module via sys.modules at decoration time,
# so the module must be registered before exec_module runs.
sys.modules[_spec.name] = _rp
_spec.loader.exec_module(_rp)

DEFAULT_COMPONENTS = _rp.DEFAULT_COMPONENTS
DEFAULT_EUR_PER_KWH = _rp.DEFAULT_EUR_PER_KWH
DEFAULT_LIFESPAN_YEARS = _rp.DEFAULT_LIFESPAN_YEARS
DEFAULT_REFERENCE_PRICE_EUR = _rp.DEFAULT_REFERENCE_PRICE_EUR
DEFAULT_UTILIZATION = _rp.DEFAULT_UTILIZATION
DEFAULT_WALL_WATTS = _rp.DEFAULT_WALL_WATTS
compute_reference = _rp.compute_reference


def _parse_component(raw: str) -> tuple[str, Decimal]:
    name, sep, cost = raw.rpartition("=")
    if not sep or not name.strip():
        raise argparse.ArgumentTypeError(f"component must be NAME=EUR, got {raw!r}")
    try:
        value = Decimal(cost.strip())
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"component cost is not a number: {raw!r}") from exc
    if value < 0:
        raise argparse.ArgumentTypeError(f"component cost must be >= 0: {raw!r}")
    return name.strip(), value


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Defaults reproduce the canonical RTX 4060 Ti reference rig.",
    )
    p.add_argument(
        "--component",
        action="append",
        type=_parse_component,
        default=[],
        metavar="NAME=EUR",
        help="add or override a BOM line item (repeatable)",
    )
    p.add_argument(
        "--reset-components",
        action="store_true",
        help="start from an empty BOM; only --component entries count",
    )
    p.add_argument(
        "--wall-watts", type=int, default=DEFAULT_WALL_WATTS, help=f"whole-node AC draw (default {DEFAULT_WALL_WATTS})"
    )
    p.add_argument(
        "--eur-per-kwh", type=Decimal, default=DEFAULT_EUR_PER_KWH, help=f"electricity tariff (default {DEFAULT_EUR_PER_KWH})"
    )
    p.add_argument(
        "--lifespan-years",
        type=Decimal,
        default=DEFAULT_LIFESPAN_YEARS,
        help=f"hardware replacement cycle (default {DEFAULT_LIFESPAN_YEARS})",
    )
    p.add_argument(
        "--utilization",
        type=Decimal,
        default=DEFAULT_UTILIZATION,
        help="booked fraction of the lifetime, (0, 1] (default 1 = fully booked)",
    )
    p.add_argument(
        "--price",
        type=Decimal,
        default=DEFAULT_REFERENCE_PRICE_EUR,
        help=f"pinned reference price in EUR (default {DEFAULT_REFERENCE_PRICE_EUR})",
    )
    p.add_argument("--json", action="store_true", help="print the JSON artifact to stdout")
    p.add_argument("--write-json", type=Path, metavar="PATH", help="write the JSON artifact (e.g. website/reference.json)")
    return p.parse_args(argv)


def _artifact(b) -> dict:
    return {
        "generated_by": "scripts/ops/ait-reference-price.py",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "unit": "1 AIT = 1 compute-hour on the island reference rig",
        **b.to_dict(),
    }


def _print_table(b) -> None:
    eur = lambda d: f"€{d.quantize(Decimal('0.01'))}"  # noqa: E731
    eur6 = lambda d: f"€{d.quantize(Decimal('0.000001'))}"  # noqa: E731

    print("Reference rig — bill of materials")
    for name, cost in b.components.items():
        print(f"  {name:<28} {eur(cost):>10}")
    print(f"  {'hardware total':<28} {eur(b.hardware_total_eur):>10}")

    print("\nAssumptions")
    print(f"  lifespan                    {b.lifespan_years} years")
    pct = (b.utilization * 100).quantize(Decimal("0.01"))
    print(f"  utilization                 {pct} %{' (fully booked)' if b.utilization == 1 else ''}")
    print(f"  bookable hours              {int(b.bookable_hours):,} h")
    print(f"  wall draw                   {b.wall_watts} W")
    print(f"  tariff                      €{b.eur_per_kwh}/kWh")

    print("\nPer compute-hour")
    print(f"  hardware wear               {eur6(b.wear_eur_per_hour)}")
    print(f"  electricity                 {eur6(b.electricity_eur_per_hour)}")
    print(f"  cost floor                  {eur6(b.cost_eur_per_hour)}")

    print(f"\nReference price               {eur(b.price_eur)}  (= {b.ait_per_eur} AIT/EUR)")
    margin_pct = f"+{b.margin_on_cost_pct.quantize(Decimal('0.1'))} %" if b.margin_on_cost_pct else "n/a"
    print(f"  margin over cost            {eur6(b.margin_eur_per_hour)}  ({margin_pct})")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    components = {} if args.reset_components else dict(DEFAULT_COMPONENTS)
    components.update(dict(args.component))

    try:
        b = compute_reference(
            components=components,
            wall_watts=args.wall_watts,
            eur_per_kwh=args.eur_per_kwh,
            lifespan_years=args.lifespan_years,
            utilization=args.utilization,
            price_eur=args.price,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    artifact = _artifact(b)
    if args.write_json:
        args.write_json.parent.mkdir(parents=True, exist_ok=True)
        args.write_json.write_text(json.dumps(artifact, indent=2) + "\n")
        print(f"wrote {args.write_json}")
    if args.json:
        print(json.dumps(artifact, indent=2))
    else:
        _print_table(b)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
