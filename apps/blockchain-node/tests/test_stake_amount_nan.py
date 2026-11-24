"""#2771 AUDIT-CHAIN-STAKE-AMOUNT-NAN-1: stake_tokens amount type/finite check.

``amount <= 0`` was the only guard — NaN bypasses it (every comparison is
False), str/dict input raised TypeError → 500, and a NaN amount then
flowed into the signed message, the balance check (also NaN-bypassed),
the Stake row, and the queued STAKE_LOCK. The endpoint now requires a
positive finite integer before any signature work.
"""

from __future__ import annotations

import math
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from aitbc_chain.rpc import staking

ADDR = "0x" + "55" * 20


def _body(amount):
    return {"address": ADDR, "amount": amount, "lock_days": 30}


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -5, 0, 5.5, "100", {"x": 1}, True])
def test_bad_amount_rejected_400(bad):
    with pytest.raises(HTTPException) as exc:
        staking.stake_tokens(Mock(), _body(bad))
    assert exc.value.status_code == 400
    assert "positive integer" in exc.value.detail


def test_integral_float_amount_passes_amount_gate():
    """``5.0`` is integral — it must NOT die on the amount check (it will
    fail later on the missing signature, which proves it got past)."""
    with pytest.raises(HTTPException) as exc:
        staking.stake_tokens(Mock(), _body(5.0))
    assert exc.value.status_code != 400 or "positive integer" not in exc.value.detail
