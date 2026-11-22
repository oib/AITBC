"""#2551: dashboard wallet balances must read 'N/A' — not '0 AIT' — when both
the wallet daemon and the chain RPC balance lookup fail.
"""

from __future__ import annotations

from typing import cast

import pytest

import aitbc_cli.commands.dashboard as dashboard_mod
from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError

ADDR = "0x" + "ab" * 20


class _DownClient:
    def __init__(self, *a, **kw):
        pass

    def get(self, *a, **kw):
        raise NetworkError("connection refused")


class _UpRpcClient:
    balance = 5 * 10**18

    def __init__(self, *a, **kw):
        pass

    def get(self, path, *a, **kw):
        return {"balance": _UpRpcClient.balance, "nonce": 0, "chain_id": "ait-devnet"}


@pytest.fixture
def down_everywhere(monkeypatch):
    monkeypatch.setattr(dashboard_mod, "AITBCHTTPClient", _DownClient)


def test_both_sources_down_reports_na(down_everywhere):
    wallet_client = _DownClient()
    info = dashboard_mod._live_wallet_balance(
        cast(AITBCHTTPClient, wallet_client), "w1", ADDR, "ait-devnet", "http://rpc:8202"
    )
    assert info["balance"] == "N/A"
    assert info["balance_ait"] == "N/A"


def test_daemon_down_rpc_answers_real_balance(monkeypatch):
    """Fallback still works: daemon down + RPC up -> the real on-chain balance."""
    monkeypatch.setattr(dashboard_mod, "AITBCHTTPClient", _UpRpcClient)

    # wallet daemon probe uses the same class — make only its first call fail
    # by giving the wallet client object a failing get directly.
    class _FailWallet:
        def get(self, *a, **kw):
            raise NetworkError("daemon down")

    info = dashboard_mod._live_wallet_balance(
        cast(AITBCHTTPClient, _FailWallet()), "w1", ADDR, "ait-devnet", "http://rpc:8202"
    )
    assert info["balance"] == _UpRpcClient.balance
    assert info["balance_ait"] != "N/A"


def test_daemon_balance_zero_is_real_zero(monkeypatch):
    """A genuine 0 from the daemon must still render '0 AIT', not 'N/A'."""

    class _ZeroWallet:
        def get(self, path, *a, **kw):
            return {"balance": 0}

    info = dashboard_mod._live_wallet_balance(
        cast(AITBCHTTPClient, _ZeroWallet()), "w1", ADDR, "ait-devnet", "http://rpc:8202"
    )
    assert info["balance_ait"] == "0 AIT" or info["balance_ait"].startswith("0")
