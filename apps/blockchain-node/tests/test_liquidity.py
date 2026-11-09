"""Tests for on-chain liquidity pool state transitions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlmodel import select

from aitbc.utils.units import LIQUIDITY_FEE_UNITS
from aitbc_chain.base_models import _to_ait_address
from aitbc_chain.models import Account, LiquidityPool, LiquidityStake
from aitbc_chain.state.liquidity import (
    _distribute_to_pool,
    _ensure_pool_accounts,
    pool_emission_address,
    pool_main_address,
    pool_treasury_address,
)
from aitbc_chain.state.liquidity_transition import (
    apply_liquidity_claim,
    apply_liquidity_withdraw,
)
from aitbc_chain.state.state_transition import StateTransition


@pytest.fixture
def funded_account(session):
    """Create a funded test account."""
    address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"
    account = Account(chain_id="test-chain", address=address, balance=1_000_000_000, nonce=0)
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
            "fee": LIQUIDITY_FEE_UNITS,
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

    # Sender balance: 1_000_000_000 - 10_000 - 36_000_000 = 963_990_000
    session.refresh(funded_account)
    assert funded_account.balance == 963_990_000


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
            "fee": LIQUIDITY_FEE_UNITS,
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

    # Fund the reward treasury with 5_000 compute-units
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
    # Balance after deposit was 963_990_000; after claim fee 100 and reward 5_000 -> 963_994_900
    assert funded_account.balance == 963_994_900

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
    # After withdraw: 963_994_900 - 100 fee + 10_000 principal = 964_004_800
    assert funded_account.balance == 964_004_800

    stake_after = session.get(LiquidityStake, (stake_id, "test-chain"))
    assert stake_after.status == "withdrawn"


def _seed_active_stake(session, sender_address: str, *, stake_id: str = "liq_regress") -> LiquidityStake:
    """Seed a pool + active stake directly, leaving pool *accounts* absent.

    Going through ``apply_liquidity_deposit`` would materialize the pool
    accounts via its own ``_ensure_pool_accounts`` call; the regression under
    test needs at least one of them missing when claim/withdraw runs, so the
    rows are inserted straight into the tables and committed.
    """
    now = datetime.now(UTC)
    pool = LiquidityPool(
        pool_id="main",
        chain_id="test-chain",
        token="AIT",
        total_staked=36_000_000,
        reward_per_share=Decimal("1"),
        status="active",
    )
    stake = LiquidityStake(
        stake_id=stake_id,
        chain_id="test-chain",
        pool_id="main",
        # Canonical spelling: the apply path compares against
        # ``_to_ait_address(tx.from)`` and the identity-map attribute is not
        # re-canonicalized under expire_on_commit=False.
        address=_to_ait_address(sender_address),
        amount=36_000_000,
        lock_days=30,
        locked_until=now - timedelta(hours=1),
        reward_per_share_at_stake=Decimal("0"),
        rewards_claimed=0,
        status="active",
        # One hour old: fixed APY = floor(36e6 * 0.08 * 3600 / 31536000) = 328,
        # so _realize_fixed_apy reaches its _ensure_pool_accounts call.
        created_at=now - timedelta(hours=1),
    )
    session.add(pool)
    session.add(stake)
    session.commit()
    return stake


def _fund_pool_account(session, address: str, balance: int) -> None:
    session.add(Account(chain_id="test-chain", address=address, balance=balance, nonce=0))
    session.commit()


def test_ensure_pool_accounts_idempotent_pending(session):
    """A second ``_ensure_pool_accounts`` in one autoflush=False session must
    reuse the pending inserts, not queue duplicate primary keys (#1314)."""
    first = _ensure_pool_accounts(session, "test-chain")
    second = _ensure_pool_accounts(session, "test-chain")
    assert set(first) == set(second)
    for key in first:
        assert first[key] is second[key]
    session.flush()  # IntegrityError on unfixed code: duplicate account PKs
    accounts = session.exec(select(Account).where(Account.chain_id == "test-chain")).all()
    assert len(accounts) == 3


def test_liquidity_claim_with_absent_pool_accounts(session, funded_account):
    """LIQUIDITY_CLAIM success path: ``_realize_fixed_apy`` and the claim body
    each call ``_ensure_pool_accounts``. With the emission account absent the
    unfixed code queued duplicate pending inserts and ``session.flush`` raised
    IntegrityError instead of applying the claim."""
    sender = funded_account.address
    stake = _seed_active_stake(session, sender)
    # Fund only the treasury: pool main/emission stay absent, so both ensure
    # calls add pending rows that a flush-less session.get cannot see.
    _fund_pool_account(session, pool_treasury_address(), 40_000_000)
    assert session.get(Account, ("test-chain", pool_emission_address())) is None

    tx_data = {
        "from": sender,
        "to": sender,
        "fee": 100,
        "payload": {"pool_id": "main", "stake_id": stake.stake_id},
    }
    ok, msg = apply_liquidity_claim(session, "test-chain", tx_data, "0x" + "ee" * 32, None)
    assert ok, msg
    assert "Claimed" in msg
    session.flush()
    # Exactly one row per pool address.
    for addr in (pool_main_address(), pool_treasury_address(), pool_emission_address()):
        assert session.get(Account, ("test-chain", addr)) is not None


def test_liquidity_withdraw_with_absent_pool_accounts(session, funded_account):
    """LIQUIDITY_WITHDRAW success path: same double ``_ensure_pool_accounts``
    exposure as the claim path — emission absent, main+treasury funded."""
    sender = funded_account.address
    stake = _seed_active_stake(session, sender, stake_id="liq_regress_wd")
    _fund_pool_account(session, pool_main_address(), 40_000_000)
    _fund_pool_account(session, pool_treasury_address(), 40_000_000)
    assert session.get(Account, ("test-chain", pool_emission_address())) is None

    tx_data = {
        "from": sender,
        "to": sender,
        "fee": 100,
        "payload": {"pool_id": "main", "stake_id": stake.stake_id},
    }
    ok, msg = apply_liquidity_withdraw(session, "test-chain", tx_data, "0x" + "ef" * 32, None)
    assert ok, msg
    assert "Withdrew" in msg
    session.flush()
    for addr in (pool_main_address(), pool_treasury_address(), pool_emission_address()):
        assert session.get(Account, ("test-chain", addr)) is not None
