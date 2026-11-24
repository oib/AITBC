"""#2768 AUDIT-CHAIN-STAKE-FRESHNESS-NAN-1: NaN timestamp defeats freshness.

``_freshness_fields`` computed ``abs(time.time() - float(timestamp)) >
300`` — for NaN the comparison is False, so a signed stake/unstake request
carrying ``timestamp: NaN`` never expires. ``math.isfinite`` now rejects
it before the window check.
"""

from __future__ import annotations

import math

import pytest
from fastapi import HTTPException

from aitbc_chain.rpc import staking


def test_nan_timestamp_rejected():
    with pytest.raises(HTTPException) as exc:
        staking._freshness_fields({"timestamp": math.nan, "nonce": 0}, action="stake")
    assert exc.value.status_code == 400


def test_infinite_timestamp_rejected():
    with pytest.raises(HTTPException):
        staking._freshness_fields({"timestamp": math.inf, "nonce": 0}, action="stake")


def test_fresh_timestamp_and_nonce_still_pass():
    import time

    nonce, ts = staking._freshness_fields({"timestamp": time.time(), "nonce": 7}, action="stake")
    assert nonce == 7 and ts == pytest.approx(time.time(), abs=5)
