"""On-chain liquidity pool state transitions.

These are intentionally separate from StateTransition so the core state machine
stays readable. The methods here are pure-ish: they receive a session, mutate
state, and return (success, message).
"""

from __future__ import annotations

from decimal import Decimal

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlmodel import Session

from ..base_models import _to_ait_address
from ..logger import get_logger
from ..models import Account
from .liquidity import (
    _ensure_pool_accounts,
    _generate_stake_id,
    _get_or_create_pool,
    _pending_rewards,
    _realize_fixed_apy,
    pool_main_address,
    pool_treasury_address,
)
from ..base_models import LiquidityStake

logger = get_logger(__name__)


def _invalidate_account_cache(chain_id: str, address: str, cache: Any) -> None:
    if not cache or not cache.is_available():
        return
    cache.delete(f"account_balance:{chain_id}:{address.lower()}")
    cache.delete(f"account_details:{chain_id}:{address.lower()}")


def _debit_nonce(session: Session, chain_id: str, address: str, amount: int, fee: int) -> None:
    total = amount + fee
    session.execute(
        text(
            "UPDATE account SET balance = balance - :total, nonce = nonce + 1 "
            "WHERE chain_id = :chain_id AND address = :address"
        ),
        {"total": total, "chain_id": chain_id, "address": address},
    )


def apply_liquidity_deposit(
    session: Session,
    chain_id: str,
    tx_data: dict[str, Any],
    tx_hash: str,
    cache: Any,
) -> tuple[bool, str]:
    """Apply a LIQUIDITY_DEPOSIT transaction."""
    sender = _to_ait_address(tx_data.get("from", ""))
    payload = tx_data.get("payload") or {}
    pool_id = payload.get("pool_id", "main")
    lock_days = int(payload.get("lock_days", 0))
    if lock_days < 0:
        return (False, "lock_days cannot be negative")
    value = tx_data.get("value", tx_data.get("amount", 0))
    fee = tx_data.get("fee", 0)
    if value <= 0:
        return (False, "deposit amount must be positive")

    accounts = _ensure_pool_accounts(session, chain_id)
    main_addr = pool_main_address()
    main_account = accounts[main_addr]
    sender_account = session.get(Account, (chain_id, sender))
    if not sender_account:
        return (False, f"Sender account not found: {sender}")
    total_cost = value + fee
    if sender_account.balance < total_cost:
        return (False, f"Insufficient balance: {sender_account.balance} < {total_cost}")

    _debit_nonce(session, chain_id, sender, value, fee)
    main_account.balance += value
    session.add(main_account)

    pool = _get_or_create_pool(session, chain_id, pool_id)
    stake = LiquidityStake(
        stake_id=_generate_stake_id(),
        chain_id=chain_id,
        pool_id=pool_id,
        address=sender,
        amount=value,
        lock_days=lock_days,
        locked_until=datetime.now(UTC) + timedelta(days=lock_days),
        reward_per_share_at_stake=pool.reward_per_share,
        rewards_claimed=0,
        status="active",
    )
    pool.total_staked += value
    pool.updated_at = datetime.now(UTC)
    session.add(stake)
    session.add(pool)
    session.flush()

    _invalidate_account_cache(chain_id, sender, cache)
    _invalidate_account_cache(chain_id, main_addr, cache)
    logger.info("LIQUIDITY_DEPOSIT %s: %s staked %s in pool %s", tx_hash, sender, value, pool_id)
    return (True, f"Deposited {value} compute-units to pool {pool_id}")


def apply_liquidity_claim(
    session: Session,
    chain_id: str,
    tx_data: dict[str, Any],
    tx_hash: str,
    cache: Any,
) -> tuple[bool, str]:
    """Apply a LIQUIDITY_CLAIM transaction."""
    sender = _to_ait_address(tx_data.get("from", ""))
    payload = tx_data.get("payload") or {}
    pool_id = payload.get("pool_id", "main")
    stake_id = payload.get("stake_id", "")
    fee = tx_data.get("fee", 0)

    stake = session.get(LiquidityStake, (stake_id, chain_id))
    if not stake:
        return (False, f"Stake {stake_id} not found")
    if stake.address != sender or stake.pool_id != pool_id:
        return (False, "Stake does not belong to sender")
    if stake.status != "active":
        return (False, f"Stake is not active: {stake.status}")

    sender_account = session.get(Account, (chain_id, sender))
    if not sender_account:
        return (False, f"Sender account not found: {sender}")
    if sender_account.balance < fee:
        return (False, f"Insufficient balance for fee: {sender_account.balance} < {fee}")

    pool = _get_or_create_pool(session, chain_id, pool_id)

    # Realize fixed APY before computing rewards
    _realize_fixed_apy(session, chain_id, pool, stake)
    rewards = _pending_rewards(stake, pool)
    if rewards <= 0:
        # Still charge the fee and advance nonce if the user wants to refresh
        sender_account = session.get(Account, (chain_id, sender))
        session.execute(
            text(
                "UPDATE account SET balance = balance - :fee, nonce = nonce + 1 "
                "WHERE chain_id = :chain_id AND address = :address"
            ),
            {"fee": fee, "chain_id": chain_id, "address": sender},
        )
        _invalidate_account_cache(chain_id, sender, cache)
        return (True, "No rewards to claim")

    accounts = _ensure_pool_accounts(session, chain_id)
    treasury_account = accounts[pool_treasury_address()]
    if treasury_account.balance < rewards:
        return (False, f"Pool treasury has insufficient rewards: {treasury_account.balance} < {rewards}")

    # Debit sender fee
    session.execute(
        text(
            "UPDATE account SET balance = balance - :fee, nonce = nonce + 1 WHERE chain_id = :chain_id AND address = :address"
        ),
        {"fee": fee, "chain_id": chain_id, "address": sender},
    )
    # Refresh after fee debit and credit rewards
    session.refresh(sender_account)
    sender_account.balance += rewards
    treasury_account.balance -= rewards
    stake.rewards_claimed += rewards
    stake.updated_at = datetime.now(UTC)
    session.add(sender_account)
    session.add(treasury_account)
    session.add(stake)
    session.flush()

    _invalidate_account_cache(chain_id, sender, cache)
    _invalidate_account_cache(chain_id, pool_treasury_address(), cache)
    logger.info("LIQUIDITY_CLAIM %s: %s claimed %s from pool %s", tx_hash, sender, rewards, pool_id)
    return (True, f"Claimed {rewards} compute-units")


def apply_liquidity_withdraw(
    session: Session,
    chain_id: str,
    tx_data: dict[str, Any],
    tx_hash: str,
    cache: Any,
) -> tuple[bool, str]:
    """Apply a LIQUIDITY_WITHDRAW transaction."""
    sender = _to_ait_address(tx_data.get("from", ""))
    payload = tx_data.get("payload") or {}
    pool_id = payload.get("pool_id", "main")
    stake_id = payload.get("stake_id", "")
    fee = tx_data.get("fee", 0)

    stake = session.get(LiquidityStake, (stake_id, chain_id))
    if not stake:
        return (False, f"Stake {stake_id} not found")
    if stake.address != sender or stake.pool_id != pool_id:
        return (False, "Stake does not belong to sender")
    if stake.status != "active":
        return (False, f"Stake is not active: {stake.status}")
    if stake.locked_until and stake.locked_until.tzinfo is None:
        stake.locked_until = stake.locked_until.replace(tzinfo=UTC)
    if stake.locked_until and datetime.now(UTC) < stake.locked_until:
        return (False, f"Stake still locked until {stake.locked_until.isoformat()}")

    sender_account = session.get(Account, (chain_id, sender))
    if not sender_account:
        return (False, f"Sender account not found: {sender}")
    if sender_account.balance < fee:
        return (False, f"Insufficient balance for fee: {sender_account.balance} < {fee}")

    pool = _get_or_create_pool(session, chain_id, pool_id)

    # Realize fixed APY and compute total rewards
    _realize_fixed_apy(session, chain_id, pool, stake)
    rewards = _pending_rewards(stake, pool)

    accounts = _ensure_pool_accounts(session, chain_id)
    main_account = accounts[pool_main_address()]
    treasury_account = accounts[pool_treasury_address()]

    total_return = stake.amount + rewards
    if main_account.balance < stake.amount:
        return (False, f"Pool main reserves insufficient: {main_account.balance} < {stake.amount}")
    if rewards > 0 and treasury_account.balance < rewards:
        return (False, f"Pool treasury has insufficient rewards: {treasury_account.balance} < {rewards}")

    # Debit fee
    session.execute(
        text(
            "UPDATE account SET balance = balance - :fee, nonce = nonce + 1 WHERE chain_id = :chain_id AND address = :address"
        ),
        {"fee": fee, "chain_id": chain_id, "address": sender},
    )
    # Refresh after fee debit and return principal + rewards
    session.refresh(sender_account)
    sender_account.balance += total_return
    main_account.balance -= stake.amount
    session.add(sender_account)
    session.add(main_account)

    if rewards > 0:
        treasury_account.balance -= rewards
        session.add(treasury_account)

    stake.status = "withdrawn"
    stake.rewards_claimed += rewards
    stake.updated_at = datetime.now(UTC)
    pool.total_staked -= stake.amount
    if pool.total_staked <= 0:
        pool.total_staked = 0
        pool.reward_per_share = Decimal("0")
    pool.updated_at = datetime.now(UTC)
    session.add(stake)
    session.add(pool)
    session.flush()

    _invalidate_account_cache(chain_id, sender, cache)
    _invalidate_account_cache(chain_id, pool_main_address(), cache)
    if rewards > 0:
        _invalidate_account_cache(chain_id, pool_treasury_address(), cache)
    logger.info("LIQUIDITY_WITHDRAW %s: %s withdrew %s + %s rewards", tx_hash, sender, stake.amount, rewards)
    return (True, f"Withdrew {total_return} compute-units")
