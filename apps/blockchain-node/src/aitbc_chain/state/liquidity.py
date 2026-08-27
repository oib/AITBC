"""Liquidity pool helpers for the state transition layer.

Defines deterministic pool/treasury accounts and reward math used by
LIQUIDITY_DEPOSIT, LIQUIDITY_WITHDRAW and LIQUIDITY_CLAIM transactions.
"""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal

from eth_utils import keccak
from sqlmodel import Session

from ..base_models import _to_ait_address
from aitbc.crypto.signature_recovery import canonical_address
from ..logger import get_logger
from ..models import Account, LiquidityDistribution, LiquidityPool, LiquidityStake

logger = get_logger(__name__)

_SECONDS_PER_AIT = 3600


def _env_or_derived(label: bytes, env_var: str) -> str:
    """Return a canonical address from env or deterministically derived from a label."""
    env = os.getenv(env_var, "")
    if env:
        return canonical_address(env)
    return canonical_address("0x" + keccak(label).hex()[:40])


def pool_main_address() -> str:
    return _env_or_derived(b"aitbc.pool.main", "POOL_MAIN_ADDRESS")


def pool_treasury_address() -> str:
    return _env_or_derived(b"aitbc.pool.treasury", "POOL_TREASURY_ADDRESS")


def pool_emission_address() -> str:
    return _env_or_derived(b"aitbc.pool.emission", "LIQUIDITY_EMISSION_ADDRESS")


def _tier_apy(lock_days: int) -> Decimal:
    """Base APY based on lock tier."""
    if lock_days >= 90:
        return Decimal("0.12")
    if lock_days >= 30:
        return Decimal("0.08")
    if lock_days >= 7:
        return Decimal("0.05")
    return Decimal("0.03")


def _apy_reward_seconds(amount: int, apy: Decimal, elapsed_seconds: float) -> int:
    """Compute fixed APY reward in compute-seconds for a given elapsed time."""
    years = Decimal(str(elapsed_seconds)) / Decimal("31536000")  # 365 * 24 * 3600
    reward = Decimal(amount) * apy * years
    return int(reward.to_integral_value(rounding=ROUND_FLOOR))


def _ensure_pool_accounts(session: Session, chain_id: str) -> dict[str, Account]:
    """Create pool reserve, treasury and emission accounts if missing."""
    accounts: dict[str, Account] = {}
    for addr in (pool_main_address(), pool_treasury_address(), pool_emission_address()):
        ait_addr = _to_ait_address(addr)
        account = session.get(Account, (chain_id, ait_addr))
        if not account:
            account = Account(chain_id=chain_id, address=ait_addr, balance=0, nonce=0)
            session.add(account)
        accounts[ait_addr] = account
    return accounts


def _get_or_create_pool(session: Session, chain_id: str, pool_id: str = "main") -> LiquidityPool:
    """Return the pool row, creating it with zero state if it does not exist."""
    pool = session.get(LiquidityPool, (pool_id, chain_id))
    if not pool:
        pool = LiquidityPool(
            pool_id=pool_id,
            chain_id=chain_id,
            token="AIT",
            total_staked=0,
            reward_per_share=Decimal("0"),
            status="active",
        )
        session.add(pool)
        session.flush()
    return pool


def _scaled_reward_per_share_increment(amount: int, total_staked: int) -> Decimal:
    """Return the reward-per-share increment for a distribution of ``amount``.

    Uses direct Decimal division without extra scaling; ``reward_per_share`` is
    kept as a high-precision Decimal.
    """
    if total_staked <= 0 or amount <= 0:
        return Decimal("0")
    return Decimal(amount) / Decimal(total_staked)


def _distribute_to_pool(
    session: Session,
    chain_id: str,
    pool_id: str,
    amount_seconds: int,
    source: str,
) -> bool:
    """Add fee/emission rewards to the global reward-per-share for a pool.

    The amount must already have been transferred into ``pool_treasury_address()``
    before this helper is called, so the treasury account balance matches the
    rewards tracked by reward_per_share.
    """
    if amount_seconds <= 0:
        return True
    pool = _get_or_create_pool(session, chain_id, pool_id)
    if pool.total_staked <= 0:
        # No active stakes yet; keep the distribution as treasury balance.
        logger.info("Pool %s has no active stakes; %s reward %s held in treasury", pool_id, source, amount_seconds)
        return True

    reward_before = pool.reward_per_share
    increment = _scaled_reward_per_share_increment(amount_seconds, pool.total_staked)
    pool.reward_per_share += increment
    pool.last_distribution_at = datetime.now(UTC)
    pool.updated_at = datetime.now(UTC)
    session.add(pool)

    dist = LiquidityDistribution(
        chain_id=chain_id,
        pool_id=pool_id,
        amount=amount_seconds,
        source=source,
        reward_per_share_before=reward_before,
        reward_per_share_after=pool.reward_per_share,
        total_staked=pool.total_staked,
    )
    session.add(dist)
    logger.info(
        "Distributed %s compute-seconds to pool %s from %s; rps %s -> %s",
        amount_seconds,
        pool_id,
        source,
        reward_before,
        pool.reward_per_share,
    )
    return True


def _realize_fixed_apy(session: Session, chain_id: str, pool: LiquidityPool, stake: LiquidityStake) -> int:
    """Realize fixed APY for a stake by moving emission treasury into the pool reward pool.

    Returns the number of compute-seconds added to the pool reward-per-share.
    """
    if stake.status != "active" or stake.amount <= 0:
        return 0
    created = stake.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    elapsed = (datetime.now(UTC) - created).total_seconds()
    apy = _tier_apy(stake.lock_days)
    fixed = _apy_reward_seconds(stake.amount, apy, elapsed)
    if fixed <= 0:
        return 0

    accounts = _ensure_pool_accounts(session, chain_id)
    emission = accounts[pool_emission_address()]
    treasury = accounts[pool_treasury_address()]
    if emission.balance < fixed:
        # Emission treasury empty: fixed APY cannot be paid this time.
        logger.warning("Emission treasury shortfall for stake %s: %s < %s", stake.stake_id, emission.balance, fixed)
        return 0

    emission.balance -= fixed
    treasury.balance += fixed
    session.add(emission)
    session.add(treasury)

    _distribute_to_pool(session, chain_id, stake.pool_id, fixed, "emission")
    return fixed


def _pending_rewards(stake: LiquidityStake, pool: LiquidityPool) -> int:
    """Compute fee-share + fixed-APY rewards pending for a stake.

    Caller must have already called ``_realize_fixed_apy`` if it wants APY
    included in ``pool.reward_per_share``.
    """
    if stake.status != "active" or stake.amount <= 0:
        return 0
    share_seconds = int(
        (Decimal(stake.amount) * (pool.reward_per_share - stake.reward_per_share_at_stake)).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    return max(0, share_seconds - stake.rewards_claimed)


def _generate_stake_id() -> str:
    return f"liq_{secrets.token_hex(8)}"
