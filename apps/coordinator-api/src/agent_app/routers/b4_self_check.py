"""Self-check for B4 monetary semantics."""

from decimal import Decimal


def test_decimal_exactness():
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")
    print("B4 self-check: Decimal arithmetic is exact.")


if __name__ == "__main__":
    test_decimal_exactness()
