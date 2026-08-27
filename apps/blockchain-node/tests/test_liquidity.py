"""Tests for on-chain liquidity pool state transitions."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from aitbc_chain.models import Account, LiquidityPool, LiquidityStake
from aitbc_chain.state.liquidity import (
    _distribute_to_pool,
    _ensure_pool_accounts,
    pool_main_address,
    pool_treasury_address,
)
from aitbc_chain.state.state_transition import StateTransition


@pytest.fixture
def funded_account(session):
    """Create a funded test account."""
    address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"
    account = Account(chain_id="test-chain", address=address, balance=1_000_000, nonce=0)
    session.add(account)
    session.commit()
    return account


def _make_signed_tx(account_address: str, tx_data: dict) -> dict:
    tx = {**tx_data, "signature": "0x" + "00" * 65}
    return tx


def _find_stake(session, address: str):
    return session.exec(
        __import__("sqlmodel")
        .select(LiquidityStake)
        .where(
            LiquidityStake.chain_id == "test-chain",
            LiquidityStake.address == address,
            LiquidityStake.status == "active",
        )
    ).first()


def test_liquidity_deposit(session, funded_account):
    st = StateTransition()
    tx = _make_signed_tx(
        funded_account.address,
        {
            "type": "LIQUIDITY_DEPOSIT",
            "from": funded_account.address,
            "to": pool_main_address(),
            "amount": 10_000,
            "value": 10_000,
            "fee": 3600,
            "nonce": 0,
            "chain_id": "test-chain",
            "payload": {"pool_id": "main", "lock_days": 30},
        },
    )

    with patch("aitbc_chain.state.state_transition.verify_transaction_signature", return_value=True):
        ok, msg = st.apply_transaction(session, "test-chain", tx, "0x" + "aa" * 32)

    assert ok, msg
    pool = session.get(LiquidityPool, ("main", "test-chain"))
    assert pool is not None
    assert pool.total_staked == 10_000
    stake = _find_stake(session, funded_account.address)
    assert stake is not None
    assert stake.amount == 10_000

    # Sender balance: 1_000_000 - 10_000 - 3600 = 986_400
    session.refresh(funded_account)
    assert funded_account.balance == 986_400


def test_liquidity_claim_and_withdraw(session, funded_account):
    st = StateTransition()
    deposit_tx = _make_signed_tx(
        funded_account.address,
        {
            "type": "LIQUIDITY_DEPOSIT",
            "from": funded_account.address,
            "to": pool_main_address(),
            "amount": 10_000,
            "value": 10_000,
            "fee": 3600,
            "nonce": 0,
            "chain_id": "test-chain",
            "payload": {"pool_id": "main", "lock_days": 0},
        },
    )

    with patch("aitbc_chain.state.state_transition.verify_transaction_signature", return_value=True):
        ok, msg = st.apply_transaction(session, "test-chain", deposit_tx, "0x" + "ab" * 32)
    assert ok, msg

    stake = _find_stake(session, funded_account.address)
    assert stake is not None
    stake_id = stake.stake_id

    # Fund the reward treasury with 5_000 compute-seconds
    _ensure_pool_accounts(session, "test-chain")
    treasury = session.get(Account, ("test-chain", pool_treasury_address()))
    treasury.balance += 5_000
    session.add(treasury)
    session.commit()

    # Distribute 5_000 to the pool (1 staked token = 0.5 rps)
    _distribute_to_pool(session, "test-chain", "main", 5_000, "test")
    session.commit()

    pool = session.get(LiquidityPool, ("main", "test-chain"))
    assert pool is not None
    assert pool.reward_per_share == Decimal("0.5")

    claim_tx = _make_signed_tx(
        funded_account.address,
        {
            "type": "LIQUIDITY_CLAIM",
            "from": funded_account.address,
            "to": funded_account.address,
            "amount": 0,
            "value": 0,
            "fee": 100,
            "nonce": 1,
            "chain_id": "test-chain",
            "payload": {"pool_id": "main", "stake_id": stake_id},
        },
    )

    with patch("aitbc_chain.state.state_transition.verify_transaction_signature", return_value=True):
        ok, msg = st.apply_transaction(session, "test-chain", claim_tx, "0x" + "ac" * 32)
    assert ok, msg

    session.refresh(funded_account)
    # Balance after deposit was 986_400; after claim fee 100 and reward 5_000 -> 991_300
    assert funded_account.balance == 991_300

    withdraw_tx = _make_signed_tx(
        funded_account.address,
        {
            "type": "LIQUIDITY_WITHDRAW",
            "from": funded_account.address,
            "to": funded_account.address,
            "amount": 0,
            "value": 0,
            "fee": 100,
            "nonce": 2,
            "chain_id": "test-chain",
            "payload": {"pool_id": "main", "stake_id": stake_id},
        },
    )

    with patch("aitbc_chain.state.state_transition.verify_transaction_signature", return_value=True):
        ok, msg = st.apply_transaction(session, "test-chain", withdraw_tx, "0x" + "ad" * 32)
    assert ok, msg

    session.refresh(funded_account)
    # After withdraw: 991_300 - 100 fee + 10_000 principal = 1_001_200
    assert funded_account.balance == 1_001_200

    stake_after = session.get(LiquidityStake, (stake_id, "test-chain"))
    assert stake_after.status == "withdrawn"
