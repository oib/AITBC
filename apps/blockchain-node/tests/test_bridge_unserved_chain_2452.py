"""#2452 BRIDGE-UNSERVED-CHAIN-500-1 pins — allowed-but-unserved chain ids.

On a node that doesn't serve ``bc-2-island-1``'s store, the bridge read
endpoints used to answer HTTP 500: ``session_scope`` raises
ChainDbMissingError/ForeignChainDbError and the handlers' generic
``except Exception`` swallowed it. They now answer 404 naming the chain.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi import HTTPException

import aitbc_chain.cross_chain.bridge as ccb
from aitbc_chain.database import ChainDbMissingError, ForeignChainDbError
from aitbc_chain.rpc import bridge as bridge_rpc

UNSERVED = "bc-2-island-1"


class _MissingDbBridge:
    """Bridge stand-in whose chain-scoped reads raise the typed DB errors."""

    def __init__(self, exc: Exception):
        self._exc = exc

    def get_bridge_balance(self, chain_id=None):
        raise self._exc

    def list_pending_transfers(self, chain_id=None):
        raise self._exc

    def get_validator_set(self, chain_id, epoch=None):
        raise self._exc

    def get_block_header_status(self, chain_id, height):
        raise self._exc


@pytest.mark.parametrize("exc", [ChainDbMissingError("no chain.db"), ForeignChainDbError("foreign chain")])
def test_balance_unserved_chain_404(monkeypatch, exc):
    monkeypatch.setattr(ccb, "get_cross_chain_bridge", lambda: _MissingDbBridge(exc))
    with pytest.raises(HTTPException) as err:
        bridge_rpc.get_bridge_balance(request=Mock(), chain_id=UNSERVED)
    assert err.value.status_code == 404
    assert UNSERVED in err.value.detail
    assert "not served" in err.value.detail


@pytest.mark.parametrize("exc", [ChainDbMissingError("no chain.db"), ForeignChainDbError("foreign chain")])
def test_pending_unserved_chain_404(monkeypatch, exc):
    monkeypatch.setattr(ccb, "get_cross_chain_bridge", lambda: _MissingDbBridge(exc))
    monkeypatch.setattr(bridge_rpc, "get_chain_id", lambda c=None: c or "test")
    with pytest.raises(HTTPException) as err:
        bridge_rpc.list_pending_transfers(request=Mock(), chain_id=UNSERVED)
    assert err.value.status_code == 404
    assert UNSERVED in err.value.detail


def test_validator_set_unserved_chain_404(monkeypatch):
    monkeypatch.setattr(ccb, "get_cross_chain_bridge", lambda: _MissingDbBridge(ChainDbMissingError("x")))
    request = Mock()
    request.query_params = {}
    with pytest.raises(HTTPException) as err:
        bridge_rpc.get_validator_set(request, UNSERVED)
    assert err.value.status_code == 404


def test_block_header_unserved_chain_404(monkeypatch):
    monkeypatch.setattr(ccb, "get_cross_chain_bridge", lambda: _MissingDbBridge(ChainDbMissingError("x")))
    with pytest.raises(HTTPException) as err:
        bridge_rpc.get_block_header(request=Mock(), chain_id=UNSERVED, height=1)
    assert err.value.status_code == 404


def test_unrelated_error_still_500(monkeypatch):
    """A non-chain-scoped failure keeps the generic 500 mapping."""

    class _BoomBridge(_MissingDbBridge):
        def get_bridge_balance(self, chain_id=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(ccb, "get_cross_chain_bridge", lambda: _BoomBridge(RuntimeError("x")))
    with pytest.raises(HTTPException) as err:
        bridge_rpc.get_bridge_balance(request=Mock(), chain_id=UNSERVED)
    assert err.value.status_code == 500
