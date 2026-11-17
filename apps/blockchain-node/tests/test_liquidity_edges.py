"""Edge-case and gate-branch tests for the liquidity state-transition layer.

Complements ``test_liquidity.py`` (happy-path deposit/claim/withdraw through
``StateTransition``) by exercising the apply functions directly: verdict
error paths, the v18 sealed-header-time branches, the v24 authoritative-read
branches, the pool-account v24 fence, and the fixed-APY/distribution helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import select

from aitbc.crypto.signature_recovery import canonical_address
from aitbc_chain.base_models import _to_ait_address
from aitbc_chain.models import (
    Account,
    LiquidityDistribution,
    LiquidityPool,
    LiquidityStake,
)
from aitbc_chain.state.liquidity import (
    _apy_reward_units,
    _distribute_to_pool,
    _ensure_pool_accounts,
    _get_or_create_pool,
    _pending_rewards,
    _realize_fixed_apy,
    _scaled_reward_per_share_increment,
    _tier_apy,
    pool_emission_address,
    pool_main_address,
    pool_treasury_address,
)
from aitbc_chain.state.liquidity_transition import (
    apply_liquidity_claim,
    apply_liquidity_deposit,
    apply_liquidity_withdraw,
)
from aitbc_chain.v24_rules import v24_rules_active

CHAIN = "test-chain"
SENDER = _to_ait_address("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
OTHER = _to_ait_address("0x1111111111111111111111111111111111111111")
BLOCK_TIME = datetime(2026, 11, 6, 12, 0, 0, tzinfo=UTC)


class _RecordingCache:
    """Minimal cache stub: reports available and records delete() keys."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    def is_available(self) -> bool:
        return True

    def delete(self, key: str) -> None:
        self.deleted.append(key)


@pytest.fixture
def funded_sender(session):
    account = Account(chain_id=CHAIN, address=SENDER, balance=1_000_000, nonce=0)
    session.add(account)
    session.commit()
    return account


def _fund(session, address: str, balance: int) -> Account:
    account = Account(chain_id=CHAIN, address=_to_ait_address(address), balance=balance, nonce=0)
    session.add(account)
    session.commit()
    return account


def _seed_stake(
    session,
    *,
    stake_id: str = "liq_edge",
    address: str = SENDER,
    pool_id: str = "main",
    amount: int = 10_000,
    lock_days: int = 0,
    locked_until: datetime | None = None,
    rps_at_stake: Decimal = Decimal("0"),
    rewards_claimed: int = 0,
    status: str = "active",
    created_at: datetime | None = None,
) -> LiquidityStake:
    now = datetime.now(UTC)
    pool = session.get(LiquidityPool, (pool_id, CHAIN))
    if pool is None:
        pool = LiquidityPool(
            pool_id=pool_id,
            chain_id=CHAIN,
            token="AIT",
            total_staked=amount,
            reward_per_share=Decimal("1"),
            status="active",
        )
        session.add(pool)
    stake = LiquidityStake(
        stake_id=stake_id,
        chain_id=CHAIN,
        pool_id=pool_id,
        address=_to_ait_address(address),
        amount=amount,
        lock_days=lock_days,
        locked_until=locked_until,
        reward_per_share_at_stake=rps_at_stake,
        rewards_claimed=rewards_claimed,
        status=status,
        created_at=created_at or now,
        updated_at=now,
    )
    session.add(stake)
    session.commit()
    return stake


def _tx_data(sender: str, *, pool_id: str = "main", stake_id: str = "", fee: int = 0, **payload) -> dict:
    return {
        "from": sender,
        "to": sender,
        "fee": fee,
        "payload": {"pool_id": pool_id, "stake_id": stake_id, **payload},
    }


# ---------------------------------------------------------------------------
# liquidity.py helpers
# ---------------------------------------------------------------------------


def test_tier_apy_boundaries():
    assert _tier_apy(0) == Decimal("0.03")
    assert _tier_apy(6) == Decimal("0.03")
    assert _tier_apy(7) == Decimal("0.05")
    assert _tier_apy(29) == Decimal("0.05")
    assert _tier_apy(30) == Decimal("0.08")
    assert _tier_apy(89) == Decimal("0.08")
    assert _tier_apy(90) == Decimal("0.12")
    assert _tier_apy(365) == Decimal("0.12")


def test_apy_reward_units_scales_with_time():
    # 1 year at the 30-day tier (8% APY) on 36_000_000 units -> 2_880_000.
    year = 365 * 24 * 3600
    assert _apy_reward_units(36_000_000, Decimal("0.08"), year) == 2_880_000
    # Half a year floors to exactly half.
    assert _apy_reward_units(36_000_000, Decimal("0.08"), year / 2) == 1_440_000
    # Seconds, not days: one hour is ~0.0114% of a year -> floor to 0 for small stakes.
    assert _apy_reward_units(1_000, Decimal("0.03"), 3600) == 0


def test_pool_addresses_env_override(monkeypatch):
    env_addrs = {
        "POOL_MAIN_ADDRESS": "0x" + "11" * 20,
        "POOL_TREASURY_ADDRESS": "0x" + "22" * 20,
        "LIQUIDITY_EMISSION_ADDRESS": "0x" + "33" * 20,
    }
    for key, value in env_addrs.items():
        monkeypatch.setenv(key, value)
    assert pool_main_address() == canonical_address(env_addrs["POOL_MAIN_ADDRESS"])
    assert pool_treasury_address() == canonical_address(env_addrs["POOL_TREASURY_ADDRESS"])
    assert pool_emission_address() == canonical_address(env_addrs["LIQUIDITY_EMISSION_ADDRESS"])


def test_pool_addresses_deterministic_derivation():
    # No env vars in the test env: labels derive stable, distinct addresses.
    main, treasury, emission = pool_main_address(), pool_treasury_address(), pool_emission_address()
    assert len({main, treasury, emission}) == 3
    for addr in (main, treasury, emission):
        assert addr.startswith("0x") and len(addr) == 42
    # Deterministic across calls.
    assert pool_main_address() == main


def test_ensure_pool_accounts_v24_fence_reloads_committed_state(session):
    """Under v24 rules a persistent Account is flushed+expired+reloaded so
    downstream ``balance +/-=`` computes on committed state, not a stale
    identity-map snapshot."""
    first = _ensure_pool_accounts(session, CHAIN)
    session.commit()
    # Mutate committed state behind the identity map's back is not needed to
    # cover the fence — the flush/expire/reload runs on every persistent hit.
    with v24_rules_active():
        second = _ensure_pool_accounts(session, CHAIN)
    assert set(second) == set(first)
    for key in first:
        assert second[key] is not first[key] or second[key].balance == first[key].balance


def test_scaled_reward_per_share_increment_zero_cases():
    assert _scaled_reward_per_share_increment(100, 0) == Decimal("0")
    assert _scaled_reward_per_share_increment(0, 100) == Decimal("0")
    assert _scaled_reward_per_share_increment(-5, 100) == Decimal("0")
    assert _scaled_reward_per_share_increment(50, 200) == Decimal("0.25")


def test_distribute_to_pool_zero_amount_is_noop(session):
    _get_or_create_pool(session, CHAIN, "main")
    session.commit()
    assert _distribute_to_pool(session, CHAIN, "main", 0, "test") is True
    assert _distribute_to_pool(session, CHAIN, "main", -10, "test") is True
    pool = session.get(LiquidityPool, ("main", CHAIN))
    assert pool.reward_per_share == Decimal("0")
    dists = session.exec(select(LiquidityDistribution).where(LiquidityDistribution.chain_id == CHAIN)).all()
    assert dists == []


def test_distribute_to_pool_without_stakes_holds_in_treasury(session):
    """Rewards distributed before any stake exists stay as treasury balance:
    no reward-per-share bump and no distribution row."""
    _get_or_create_pool(session, CHAIN, "main")  # total_staked = 0
    session.commit()
    assert _distribute_to_pool(session, CHAIN, "main", 5_000, "escrow_fee") is True
    session.flush()
    pool = session.get(LiquidityPool, ("main", CHAIN))
    assert pool.reward_per_share == Decimal("0")
    dists = session.exec(select(LiquidityDistribution).where(LiquidityDistribution.chain_id == CHAIN)).all()
    assert dists == []


def test_distribute_to_pool_updates_reward_per_share(session):
    _get_or_create_pool(session, CHAIN, "main")
    pool = session.get(LiquidityPool, ("main", CHAIN))
    pool.total_staked = 10_000
    session.add(pool)
    session.commit()
    assert _distribute_to_pool(session, CHAIN, "main", 5_000, "gas_fee") is True
    session.flush()
    session.refresh(pool)
    assert pool.reward_per_share == Decimal("0.5")
    dist = session.exec(select(LiquidityDistribution).where(LiquidityDistribution.chain_id == CHAIN)).one()
    assert dist.amount == 5_000
    assert dist.source == "gas_fee"
    assert dist.reward_per_share_before == Decimal("0")
    assert dist.reward_per_share_after == Decimal("0.5")
    assert dist.total_staked == 10_000


def test_realize_fixed_apy_moves_emission_to_treasury(session):
    """A year-old 30-day-tier stake realizes floor(amount * 0.08 * 1yr)."""
    now = datetime.now(UTC)
    stake = _seed_stake(session, amount=36_000_000, lock_days=30, created_at=now - timedelta(days=365))
    pool = _get_or_create_pool(session, CHAIN, "main")
    pool.reward_per_share = Decimal("0")  # isolate the emission increment
    session.add(pool)
    _fund(session, pool_emission_address(), 100_000_000)
    session.commit()

    realized = _realize_fixed_apy(session, CHAIN, pool, stake, now=now)
    assert realized == 2_880_000
    session.flush()
    emission = session.get(Account, (CHAIN, _to_ait_address(pool_emission_address())))
    treasury = session.get(Account, (CHAIN, _to_ait_address(pool_treasury_address())))
    assert emission.balance == 100_000_000 - 2_880_000
    assert treasury.balance == 2_880_000
    session.refresh(pool)
    # rps increment = 2_880_000 / total_staked(36_000_000) = 0.08
    # (Numeric(28,18) column rounding — compare with tolerance).
    assert abs(pool.reward_per_share - Decimal("0.08")) < Decimal("1e-12")
    dist = session.exec(
        select(LiquidityDistribution).where(
            LiquidityDistribution.chain_id == CHAIN, LiquidityDistribution.source == "emission"
        )
    ).one()
    assert dist.amount == 2_880_000


def test_realize_fixed_apy_zero_cases(session):
    now = datetime.now(UTC)
    pool = _get_or_create_pool(session, CHAIN, "main")
    _fund(session, pool_emission_address(), 100_000_000)
    session.commit()

    # Inactive stake: no accrual.
    withdrawn = _seed_stake(session, stake_id="liq_wd", status="withdrawn", created_at=now - timedelta(days=400))
    assert _realize_fixed_apy(session, CHAIN, pool, withdrawn, now=now) == 0

    # Active but just created: elapsed ~0 -> fixed rounds to 0.
    fresh = _seed_stake(session, stake_id="liq_fresh", created_at=now)
    assert _realize_fixed_apy(session, CHAIN, pool, fresh, now=now) == 0

    # Emission treasury empty: shortfall -> 0, no state mutated.
    broke = _seed_stake(session, stake_id="liq_broke", created_at=now - timedelta(days=400))
    emission = session.get(Account, (CHAIN, _to_ait_address(pool_emission_address())))
    emission.balance = 0
    session.add(emission)
    session.commit()
    session.refresh(broke)
    assert _realize_fixed_apy(session, CHAIN, pool, broke, now=now) == 0


def test_pending_rewards_inactive_or_empty_stake(session):
    pool = _get_or_create_pool(session, CHAIN, "main")
    pool.reward_per_share = Decimal("1")
    session.add(pool)
    session.commit()

    withdrawn = _seed_stake(session, stake_id="liq_p1", status="withdrawn")
    assert _pending_rewards(withdrawn, pool) == 0

    # Active stake whose rps snapshot already includes all distributions.
    caught_up = _seed_stake(session, stake_id="liq_p2", rps_at_stake=Decimal("1"))
    assert _pending_rewards(caught_up, pool) == 0

    # Active stake with pending share: floor(amount * delta) - claimed.
    pending = _seed_stake(session, stake_id="liq_p3", amount=10_000, rps_at_stake=Decimal("0.5"), rewards_claimed=100)
    # floor(10_000 * (1 - 0.5)) = 5_000; minus 100 claimed -> 4_900.
    assert _pending_rewards(pending, pool) == 4_900


# ---------------------------------------------------------------------------
# apply_liquidity_deposit verdicts
# ---------------------------------------------------------------------------


def test_deposit_rejects_negative_lock_days(session, funded_sender):
    tx = _tx_data(SENDER, lock_days=-1, value=1_000)
    tx["value"] = 1_000
    ok, msg = apply_liquidity_deposit(session, CHAIN, tx, "0x" + "01" * 32, None)
    assert not ok
    assert "lock_days" in msg


def test_deposit_rejects_nonpositive_value(session, funded_sender):
    tx = _tx_data(SENDER, lock_days=0)
    tx["value"] = 0
    ok, msg = apply_liquidity_deposit(session, CHAIN, tx, "0x" + "02" * 32, None)
    assert not ok
    assert "positive" in msg

    tx["value"] = -5
    ok, msg = apply_liquidity_deposit(session, CHAIN, tx, "0x" + "03" * 32, None)
    assert not ok


def test_deposit_rejects_missing_sender(session):
    tx = _tx_data(OTHER, lock_days=0)
    tx["value"] = 1_000
    ok, msg = apply_liquidity_deposit(session, CHAIN, tx, "0x" + "04" * 32, None)
    assert not ok
    assert "not found" in msg.lower()


def test_deposit_rejects_insufficient_balance(session, funded_sender):
    tx = _tx_data(SENDER, lock_days=0)
    tx["value"] = 2_000_000  # balance is 1_000_000, fee 0
    tx["fee"] = 0
    ok, msg = apply_liquidity_deposit(session, CHAIN, tx, "0x" + "05" * 32, None)
    assert not ok
    assert "Insufficient" in msg


def test_deposit_v24_authoritative_balance_read(session, funded_sender):
    """Under v24 the balance verdict reads committed scalar state, bypassing
    the identity map."""
    tx = _tx_data(SENDER, lock_days=0)
    tx["value"] = 5_000
    tx["fee"] = 10
    cache = _RecordingCache()
    with v24_rules_active():
        ok, msg = apply_liquidity_deposit(session, CHAIN, tx, "0x" + "06" * 32, cache)
    assert ok, msg
    session.flush()
    stake = session.exec(
        select(LiquidityStake).where(LiquidityStake.chain_id == CHAIN, LiquidityStake.address == SENDER)
    ).one()
    assert stake.amount == 5_000
    # Sender debited value+fee; pool main credited value.
    session.refresh(funded_sender)
    assert funded_sender.balance == 1_000_000 - 5_000 - 10
    main = session.get(Account, (CHAIN, _to_ait_address(pool_main_address())))
    assert main.balance == 5_000
    # Cache invalidation fired for sender and pool-main.
    assert any("account_balance" in k and SENDER.lower() in k for k in cache.deleted)
    assert any("account_balance" in k and pool_main_address().lower() in k for k in cache.deleted)


def test_deposit_v18_uses_sealed_header_time(session, funded_sender):
    """v18: stake id derives from tx_hash and timestamps from the block
    header — deterministic across hosts replaying the same sealed block."""
    tx = _tx_data(SENDER, lock_days=30)
    tx["value"] = 7_500
    tx_hash = "0x" + "07" * 32
    ok, msg = apply_liquidity_deposit(session, CHAIN, tx, tx_hash, None, block_version=18, block_time=BLOCK_TIME)
    assert ok, msg
    session.flush()
    stake = session.exec(select(LiquidityStake).where(LiquidityStake.chain_id == CHAIN)).one()
    # v18 derives the id from the tx hash prefix: f"liq_{tx_hash[:16]}".
    assert stake.stake_id == f"liq_{tx_hash[:16]}"
    # sqlite DateTime columns drop tzinfo — compare the wall-clock fields.
    assert stake.created_at.replace(tzinfo=None) == BLOCK_TIME.replace(tzinfo=None)
    assert stake.locked_until.replace(tzinfo=None) == (BLOCK_TIME + timedelta(days=30)).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# apply_liquidity_claim verdicts
# ---------------------------------------------------------------------------


def test_claim_rejects_unknown_stake(session, funded_sender):
    tx = _tx_data(SENDER, stake_id="liq_missing")
    tx["fee"] = 0
    ok, msg = apply_liquidity_claim(session, CHAIN, tx, "0x" + "11" * 32, None)
    assert not ok
    assert "not found" in msg.lower()


def test_claim_rejects_foreign_stake(session):
    _seed_stake(session, stake_id="liq_foreign", address=OTHER)
    tx = _tx_data(SENDER, stake_id="liq_foreign")
    tx["fee"] = 0
    ok, msg = apply_liquidity_claim(session, CHAIN, tx, "0x" + "12" * 32, None)
    assert not ok
    assert "does not belong" in msg


def test_claim_rejects_wrong_pool(session, funded_sender):
    _seed_stake(session, stake_id="liq_pool", pool_id="main")
    tx = _tx_data(SENDER, pool_id="other-pool", stake_id="liq_pool")
    tx["fee"] = 0
    ok, msg = apply_liquidity_claim(session, CHAIN, tx, "0x" + "13" * 32, None)
    assert not ok
    assert "does not belong" in msg


def test_claim_rejects_inactive_stake(session, funded_sender):
    _seed_stake(session, stake_id="liq_done", status="withdrawn")
    tx = _tx_data(SENDER, stake_id="liq_done")
    tx["fee"] = 0
    ok, msg = apply_liquidity_claim(session, CHAIN, tx, "0x" + "14" * 32, None)
    assert not ok
    assert "not active" in msg


def test_claim_rejects_missing_sender_account(session):
    _seed_stake(session, stake_id="liq_nosender", address=SENDER)
    tx = _tx_data(SENDER, stake_id="liq_nosender")
    tx["fee"] = 0
    ok, msg = apply_liquidity_claim(session, CHAIN, tx, "0x" + "15" * 32, None)
    assert not ok
    assert "not found" in msg.lower()


def test_claim_rejects_insufficient_fee_balance(session):
    _seed_stake(session, stake_id="liq_fee", address=SENDER)
    _fund(session, SENDER, 50)
    tx = _tx_data(SENDER, stake_id="liq_fee", fee=100)
    ok, msg = apply_liquidity_claim(session, CHAIN, tx, "0x" + "16" * 32, None)
    assert not ok
    assert "Insufficient" in msg


def test_claim_no_rewards_still_charges_fee(session, funded_sender):
    """An active stake with no pending rewards returns success, debits the
    fee and bumps the nonce."""
    _seed_stake(session, stake_id="liq_noreward", amount=10_000, rps_at_stake=Decimal("0"))
    pool = session.get(LiquidityPool, ("main", CHAIN))
    pool.reward_per_share = Decimal("0")  # equal to rps_at_stake -> rewards 0
    session.add(pool)
    session.commit()

    tx = _tx_data(SENDER, stake_id="liq_noreward", fee=100)
    ok, msg = apply_liquidity_claim(session, CHAIN, tx, "0x" + "17" * 32, _RecordingCache())
    assert ok, msg
    assert msg == "No rewards to claim"
    session.refresh(funded_sender)
    assert funded_sender.balance == 1_000_000 - 100
    assert funded_sender.nonce == 1


def test_claim_rejects_when_treasury_short(session, funded_sender):
    """Pending rewards exist but the treasury cannot cover them."""
    _seed_stake(session, stake_id="liq_short", amount=10_000, rps_at_stake=Decimal("0"))
    pool = session.get(LiquidityPool, ("main", CHAIN))
    pool.reward_per_share = Decimal("1")  # rewards = floor(10_000 * 1) = 10_000
    session.add(pool)
    _fund(session, pool_treasury_address(), 5_000)
    session.commit()

    tx = _tx_data(SENDER, stake_id="liq_short", fee=0)
    ok, msg = apply_liquidity_claim(session, CHAIN, tx, "0x" + "18" * 32, None)
    assert not ok
    assert "treasury" in msg.lower()


def test_claim_success_under_v24(session, funded_sender):
    """v24 claim: fee debited via raw SQL, rewards read/paid from committed
    scalar state; sender credited rewards, treasury debited."""
    _seed_stake(session, stake_id="liq_v24", amount=10_000, rps_at_stake=Decimal("0"))
    pool = session.get(LiquidityPool, ("main", CHAIN))
    pool.reward_per_share = Decimal("1")
    session.add(pool)
    _fund(session, pool_treasury_address(), 50_000)
    session.commit()

    tx = _tx_data(SENDER, stake_id="liq_v24", fee=100)
    cache = _RecordingCache()
    with v24_rules_active():
        ok, msg = apply_liquidity_claim(session, CHAIN, tx, "0x" + "19" * 32, cache)
    assert ok, msg
    assert "Claimed" in msg
    session.refresh(funded_sender)
    # -100 fee + 10_000 rewards
    assert funded_sender.balance == 1_000_000 - 100 + 10_000
    treasury = session.get(Account, (CHAIN, _to_ait_address(pool_treasury_address())))
    session.refresh(treasury)
    assert treasury.balance == 40_000
    stake = session.get(LiquidityStake, ("liq_v24", CHAIN))
    assert stake.rewards_claimed == 10_000
    assert cache.deleted  # sender + treasury invalidated


# ---------------------------------------------------------------------------
# apply_liquidity_withdraw verdicts
# ---------------------------------------------------------------------------


def test_withdraw_rejects_unknown_stake(session, funded_sender):
    tx = _tx_data(SENDER, stake_id="liq_missing")
    tx["fee"] = 0
    ok, msg = apply_liquidity_withdraw(session, CHAIN, tx, "0x" + "21" * 32, None)
    assert not ok
    assert "not found" in msg.lower()


def test_withdraw_rejects_foreign_stake(session):
    _seed_stake(session, stake_id="liq_foreign_wd", address=OTHER, locked_until=datetime.now(UTC) - timedelta(days=1))
    tx = _tx_data(SENDER, stake_id="liq_foreign_wd")
    tx["fee"] = 0
    ok, msg = apply_liquidity_withdraw(session, CHAIN, tx, "0x" + "22" * 32, None)
    assert not ok
    assert "does not belong" in msg


def test_withdraw_rejects_inactive_stake(session, funded_sender):
    _seed_stake(session, stake_id="liq_done_wd", status="withdrawn")
    tx = _tx_data(SENDER, stake_id="liq_done_wd")
    tx["fee"] = 0
    ok, msg = apply_liquidity_withdraw(session, CHAIN, tx, "0x" + "23" * 32, None)
    assert not ok
    assert "not active" in msg


def test_withdraw_rejects_while_locked(session, funded_sender):
    locked_until = BLOCK_TIME + timedelta(days=30)
    _seed_stake(session, stake_id="liq_locked", lock_days=30, locked_until=locked_until)
    tx = _tx_data(SENDER, stake_id="liq_locked")
    tx["fee"] = 0
    # v18: the verdict compares against the sealed header timestamp.
    ok, msg = apply_liquidity_withdraw(session, CHAIN, tx, "0x" + "24" * 32, None, block_version=18, block_time=BLOCK_TIME)
    assert not ok
    assert "locked" in msg


def test_withdraw_allows_at_lock_boundary(session, funded_sender):
    """``now == locked_until`` is not ``now < locked_until``: the boundary
    timestamp unlocks the stake."""
    _seed_stake(
        session,
        stake_id="liq_boundary",
        amount=10_000,
        lock_days=30,
        locked_until=BLOCK_TIME,
        rps_at_stake=Decimal("0"),
    )
    pool = session.get(LiquidityPool, ("main", CHAIN))
    pool.reward_per_share = Decimal("0")  # no pending rewards
    pool.total_staked = 10_000
    session.add(pool)
    _fund(session, pool_main_address(), 1_000_000)
    session.commit()

    tx = _tx_data(SENDER, stake_id="liq_boundary", fee=100)
    ok, msg = apply_liquidity_withdraw(
        session, CHAIN, tx, "0x" + "25" * 32, _RecordingCache(), block_version=18, block_time=BLOCK_TIME
    )
    assert ok, msg
    assert "Withdrew" in msg
    session.refresh(funded_sender)
    # -100 fee + 10_000 principal, zero rewards.
    assert funded_sender.balance == 1_000_000 - 100 + 10_000
    stake = session.get(LiquidityStake, ("liq_boundary", CHAIN))
    assert stake.status == "withdrawn"
    session.refresh(pool)
    assert pool.total_staked == 0
    assert pool.reward_per_share == Decimal("0")  # reset when pool empties
    main = session.get(Account, (CHAIN, _to_ait_address(pool_main_address())))
    session.refresh(main)
    assert main.balance == 1_000_000 - 10_000


def test_withdraw_rejects_missing_sender_account(session):
    _seed_stake(
        session,
        stake_id="liq_nosender_wd",
        address=SENDER,
        locked_until=datetime.now(UTC) - timedelta(days=1),
    )
    tx = _tx_data(SENDER, stake_id="liq_nosender_wd")
    tx["fee"] = 0
    ok, msg = apply_liquidity_withdraw(session, CHAIN, tx, "0x" + "26" * 32, None)
    assert not ok
    assert "not found" in msg.lower()


def test_withdraw_rejects_insufficient_fee_balance(session):
    _seed_stake(
        session,
        stake_id="liq_fee_wd",
        address=SENDER,
        locked_until=datetime.now(UTC) - timedelta(days=1),
    )
    _fund(session, SENDER, 50)
    tx = _tx_data(SENDER, stake_id="liq_fee_wd", fee=100)
    ok, msg = apply_liquidity_withdraw(session, CHAIN, tx, "0x" + "27" * 32, None)
    assert not ok
    assert "Insufficient" in msg


def test_withdraw_rejects_when_pool_main_short(session, funded_sender):
    """No rewards pending, but pool main reserves cannot cover principal."""
    _seed_stake(
        session,
        stake_id="liq_mainshort",
        amount=10_000,
        locked_until=datetime.now(UTC) - timedelta(days=1),
        rps_at_stake=Decimal("0"),
    )
    pool = session.get(LiquidityPool, ("main", CHAIN))
    pool.reward_per_share = Decimal("0")
    session.add(pool)
    # Pool main account absent -> _ensure_pool_accounts creates it at 0.
    session.commit()
    assert session.get(Account, (CHAIN, _to_ait_address(pool_main_address()))) is None

    tx = _tx_data(SENDER, stake_id="liq_mainshort", fee=0)
    ok, msg = apply_liquidity_withdraw(session, CHAIN, tx, "0x" + "28" * 32, None)
    assert not ok
    assert "reserves" in msg.lower()


def test_withdraw_rejects_when_treasury_short_under_v24(session, funded_sender):
    """v24 withdraw: main covers principal but treasury cannot cover pending
    rewards — both balances are read via authoritative scalar reads."""
    _seed_stake(
        session,
        stake_id="liq_treasuryshort",
        amount=10_000,
        locked_until=datetime.now(UTC) - timedelta(days=1),
        rps_at_stake=Decimal("0"),
    )
    pool = session.get(LiquidityPool, ("main", CHAIN))
    pool.reward_per_share = Decimal("1")  # rewards = 10_000
    session.add(pool)
    _fund(session, pool_main_address(), 1_000_000)
    _fund(session, pool_treasury_address(), 5_000)  # < 10_000 rewards
    session.commit()

    tx = _tx_data(SENDER, stake_id="liq_treasuryshort", fee=0)
    with v24_rules_active():
        ok, msg = apply_liquidity_withdraw(session, CHAIN, tx, "0x" + "29" * 32, None)
    assert not ok
    assert "treasury" in msg.lower()


def test_withdraw_success_with_rewards(session, funded_sender):
    """Full withdraw: principal from pool main + pending rewards from
    treasury, fee debited, stake closed, pool total reduced."""
    _seed_stake(
        session,
        stake_id="liq_full",
        amount=10_000,
        locked_until=datetime.now(UTC) - timedelta(days=1),
        rps_at_stake=Decimal("0"),
    )
    pool = session.get(LiquidityPool, ("main", CHAIN))
    pool.reward_per_share = Decimal("1")  # rewards = 10_000
    pool.total_staked = 10_000
    session.add(pool)
    _fund(session, pool_main_address(), 1_000_000)
    _fund(session, pool_treasury_address(), 50_000)
    session.commit()

    tx = _tx_data(SENDER, stake_id="liq_full", fee=100)
    ok, msg = apply_liquidity_withdraw(session, CHAIN, tx, "0x" + "2a" * 32, _RecordingCache())
    assert ok, msg
    session.refresh(funded_sender)
    # -100 fee + 10_000 principal + 10_000 rewards
    assert funded_sender.balance == 1_000_000 - 100 + 20_000
    stake = session.get(LiquidityStake, ("liq_full", CHAIN))
    assert stake.status == "withdrawn"
    assert stake.rewards_claimed == 10_000
    session.refresh(pool)
    assert pool.total_staked == 0
    main = session.get(Account, (CHAIN, _to_ait_address(pool_main_address())))
    session.refresh(main)
    assert main.balance == 1_000_000 - 10_000
    treasury = session.get(Account, (CHAIN, _to_ait_address(pool_treasury_address())))
    session.refresh(treasury)
    assert treasury.balance == 40_000
