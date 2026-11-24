"""#2779: escrow amount must fit Numeric(20,8) — bound at the boundary."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EDGE = REPO / "apps" / "edge" / "src" / "aitbc_edge"


def _amount(raw) -> object:
    import sys

    edge_src = REPO / "apps" / "edge" / "src"
    if str(edge_src) not in sys.path:
        sys.path.insert(0, str(edge_src))
    from aitbc_edge.routers.serve import _escrow_amount_ait

    return _escrow_amount_ait({"amount": raw})


def test_oversized_escrow_amount_is_unusable_not_a_500() -> None:
    # Numeric(20,8) ceiling: 12 integer digits
    assert _amount("999999999999.99999999") == Decimal("999999999999.99999999")
    assert _amount("1000000000000") is None
    assert _amount("1e30") is None
    assert _amount("-5") is None
    assert _amount("not-a-number") is None
    assert _amount("") is None


def test_extra_decimals_round_to_column_scale() -> None:
    assert _amount("1.123456789") == Decimal("1.12345679")


def test_router_maps_dataerror_to_422() -> None:
    src = (EDGE / "routers" / "serve.py").read_text()
    assert "except DataError" in src
    assert "status_code=422" in src
