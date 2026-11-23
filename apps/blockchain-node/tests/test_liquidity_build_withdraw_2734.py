"""LIQ-WITHDRAW-ZERO-AMOUNT (#2734): ``/rpc/liquidity/build-withdraw`` built
the LIQUIDITY_WITHDRAW record with ``amount``/``value``/``payload.amount``
all zero, so the sealed tx read as a zero-value withdraw of a real
position. The builder now records the stake principal in
``payload.amount``; top-level ``value`` stays 0 because the sender pays fee
only and the payout is pool-state, not a sender transfer (a nonzero value
would fail the sender-balance >= value+fee validation gate).
"""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock

from aitbc_chain.base_models import Account, LiquidityStake
from aitbc_chain.rpc.routers import liquidity as liquidity_router

_ADDRESS = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"
_STAKE_AMOUNT = 36_000_000  # 1 AIT in compute-units


def _seed(session):
    session.add(Account(chain_id="test-chain", address=_ADDRESS, balance=1_000_000, nonce=3))
    session.add(
        LiquidityStake(
            stake_id="liq_test1",
            chain_id="test-chain",
            pool_id="main",
            address=_ADDRESS,
            amount=_STAKE_AMOUNT,
            lock_days=0,
            locked_until=None,
            status="active",
        )
    )
    session.commit()


def test_build_withdraw_records_principal_in_payload(session, monkeypatch):
    _seed(session)
    # EvmAddress normalizes on write — request with the stored form.
    stored_address = session.get(LiquidityStake, ("liq_test1", "test-chain")).address
    monkeypatch.setattr(liquidity_router, "session_scope", lambda cid: contextlib.nullcontext(session))

    body = liquidity_router.BuildWithdrawRequest(address=stored_address, stake_id="liq_test1")
    result = liquidity_router.build_withdraw(MagicMock(), body, chain_id="test-chain")

    tx = result["transaction"]
    assert tx["type"] == "LIQUIDITY_WITHDRAW"
    assert tx["payload"]["amount"] == _STAKE_AMOUNT
    # value/amount stay zero: sender pays fee only; payout is pool-state.
    assert tx["value"] == 0
    assert tx["amount"] == 0
    assert tx["nonce"] == 3


def test_build_withdraw_unknown_stake_still_404(session, monkeypatch):
    _seed(session)
    stored_address = session.get(LiquidityStake, ("liq_test1", "test-chain")).address
    monkeypatch.setattr(liquidity_router, "session_scope", lambda cid: contextlib.nullcontext(session))

    body = liquidity_router.BuildWithdrawRequest(address=stored_address, stake_id="liq_nope")
    try:
        liquidity_router.build_withdraw(MagicMock(), body, chain_id="test-chain")
    except Exception as e:  # noqa: BLE001 - HTTPException expected
        assert "404" in str(e) or getattr(e, "status_code", None) == 404
    else:  # pragma: no cover
        raise AssertionError("expected 404 for unknown stake")
