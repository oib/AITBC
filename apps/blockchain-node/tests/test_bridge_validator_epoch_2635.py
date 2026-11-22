"""#2635 AUDIT-BN-BRIDGE-VALIDATOR-EPOCH-500-1 pins.

``GET /bridge/validators/{chain}?epoch=<garbage>`` used to reach
``int(epoch_str)`` inside the generic ``except Exception`` → HTTP 500.
The epoch param is now validated: non-integer or negative → 400, and a
valid epoch is forwarded to ``bridge.get_validator_set`` untouched.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import aitbc_chain.cross_chain.bridge as ccb
from aitbc_chain.rpc import bridge as bridge_rpc


class _FakeBridge:
    def __init__(self) -> None:
        self.seen_epoch: int | None = -1

    def get_validator_set(self, chain_id: str, epoch: int | None = None):
        self.seen_epoch = epoch
        return None  # -> "no validators registered" success body


def _request(epoch: str | None):
    params = {} if epoch is None else {"epoch": epoch}
    return SimpleNamespace(query_params=params)


@pytest.fixture
def bridge(monkeypatch):
    fake = _FakeBridge()
    monkeypatch.setattr(ccb, "get_cross_chain_bridge", lambda: fake)
    return fake


@pytest.mark.parametrize("bad", ["abc", "1.5", "0x10", "-1", "-500"])
def test_invalid_epoch_400(bridge, bad):
    with pytest.raises(HTTPException) as err:
        bridge_rpc.get_validator_set(_request(bad), chain_id="c1")
    assert err.value.status_code == 400


def test_valid_epoch_forwarded(bridge):
    out = bridge_rpc.get_validator_set(_request("7"), chain_id="c1")
    assert bridge.seen_epoch == 7
    assert out["success"] is True


def test_missing_epoch_defaults_none(bridge):
    out = bridge_rpc.get_validator_set(_request(None), chain_id="c1")
    assert bridge.seen_epoch is None
    assert out["success"] is True
