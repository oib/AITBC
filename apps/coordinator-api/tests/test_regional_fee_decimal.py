"""Pin: the regional cross-chain fee must multiply by Decimal, not float.

Regression site (MARKET-GLOBAL-REGIONAL-FEE-DECIMAL-TIMES-FLOAT-1 /
#1033 respin comment 14628): ``total_amount * 0.01`` on a Decimal
raised TypeError for any region-scoped transaction. Guards the source
line itself — reverting to a float literal fails immediately.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / ("src/coordinator_api/contexts/market/services/global_market.py")


def test_regional_fee_uses_decimal_multiplier() -> None:
    text = SRC.read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if "regional_fees[region.region_code]" in l)
    assert re.search(r"total_amount \* Decimal\(", line), line
    assert not re.search(r"\* 0\.0\d", line), line
