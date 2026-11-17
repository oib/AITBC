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
from ..v24_rules import v24_rules_is_active
from .authoritative_reads import read_current_account
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


def _v18_apply_time(block_version: int | None, block_time: datetime | None) -> datetime | None:
    """Return the sealed header timestamp when the v18 deterministic-apply
    gate is armed for this transaction, else ``None``.

    At v18 the committed apply output must be a pure function of
    (transaction, prior state, block header) — the header timestamp replaces
    wall-clock reads and tx_hash replaces random ids. ``block_time`` may be
    ``None`` for non-consensus callers; the volatile path then stays
    (unreachable on sealed v18 replay — the gate always carries a header
    timestamp — but kept for safety)."""
    if block_version is not None and block_version >= 18 and block_time is not None:
        return block_time
    return None


def apply_liquidity_deposit(
    session: Session,
    chain_id: str,
    tx_data: dict[str, Any],
    tx_hash: str,
    cache: Any,
    *,
    block_version: int | None = None,
    block_time: datetime | None = None,
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
    if v24_rules_is_active():
        # #1314 V7: scalar authoritative balance — bypasses identity-map
        # staleness after earlier same-block raw-SQL writes.
        _sbal, _snonce, _sexists = read_current_account(session, chain_id, sender)
        sender_balance = _sbal if _sbal is not None else 0
    else:
        sender_balance = sender_account.balance
    if sender_balance < total_cost:
        return (False, f"Insufficient balance: {sender_balance} < {total_cost}")

    _debit_nonce(session, chain_id, sender, value, fee)
    main_account.balance += value
    session.add(main_account)

    pool = _get_or_create_pool(session, chain_id, pool_id)
    v18_now = _v18_apply_time(block_version, block_time)
    # v18: the id derives from tx_hash (unique per tx) and every stored
    # timestamp from the sealed header — two hosts applying the same sealed
    # tx commit byte-identical rows. Below v18 the volatile shapes stay for
    # replay of the (empty) pre-v18 era of this type.
    now = v18_now or datetime.now(UTC)
    stake = LiquidityStake(
        stake_id=f"liq_{tx_hash[:16]}" if v18_now is not None else _generate_stake_id(),
        chain_id=chain_id,
        pool_id=pool_id,
        address=sender,
        amount=value,
        lock_days=lock_days,
        locked_until=now + timedelta(days=lock_days),
        reward_per_share_at_stake=pool.reward_per_share,
        rewards_claimed=0,
        status="active",
    )
    if v18_now is not None:
        # created_at feeds _realize_fixed_apy's accrual window — it must be
        # header-derived or elapsed differs across hosts.
        stake.created_at = now
    pool.total_staked += value
    pool.updated_at = now
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
    *,
    block_version: int | None = None,
    block_time: datetime | None = None,
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
    if v24_rules_is_active():
        _sbal, _snonce, _sexists = read_current_account(session, chain_id, sender)
        sender_fee_balance = _sbal if _sbal is not None else 0
    else:
        sender_fee_balance = sender_account.balance
    if sender_fee_balance < fee:
        return (False, f"Insufficient balance for fee: {sender_fee_balance} < {fee}")

    pool = _get_or_create_pool(session, chain_id, pool_id)

    # v18: accrue to the sealed header timestamp so every host computes the
    # identical reward amount.
    now = _v18_apply_time(block_version, block_time) or datetime.now(UTC)
    # Realize fixed APY before computing rewards
    _realize_fixed_apy(session, chain_id, pool, stake, now=now)
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
    if v24_rules_is_active():
        _tbal, _tnonce, _texists = read_current_account(session, chain_id, pool_treasury_address())
        treasury_balance = _tbal if _tbal is not None else 0
    else:
        treasury_balance = treasury_account.balance
    if treasury_balance < rewards:
        return (False, f"Pool treasury has insufficient rewards: {treasury_balance} < {rewards}")

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
    stake.updated_at = now
    session.add(sender_account)
    session.add(treasury_account)
    session.add(stake)
    session.flush()

    _invalidate_account_cache(chain_id, sender, cache)
    _invalidate_account_cache(chain_id, pool_treasury_address(), cache)
    logger.info("LIQUIDITY_CLAIM %s: %s claimed %s from pool %s", tx_hash, sender, rewards, pool_id)
    return (True, f"Claimed {rewards} compute-units")


def _withdraw_lock_error(stake: LiquidityStake, now: datetime) -> str | None:
    # v18: the lock verdict compares the sealed header timestamp, not wall
    # clock — a withdraw at the lock boundary returns the same verdict on
    # every host.
    if stake.locked_until and stake.locked_until.tzinfo is None:
        stake.locked_until = stake.locked_until.replace(tzinfo=UTC)
    if stake.locked_until and now < stake.locked_until:
        return f"Stake still locked until {stake.locked_until.isoformat()}"
    return None


def _validate_liquidity_withdraw(
    session: Session,
    chain_id: str,
    sender: str,
    pool_id: str,
    stake_id: str,
    fee: int,
    *,
    block_version: int | None,
    block_time: datetime | None,
) -> tuple[LiquidityStake | None, Account | None, datetime | None, tuple[bool, str] | None]:
    """Validate a LIQUIDITY_WITHDRAW request.

    Returns ``(stake, sender_account, now, error)`` — ``error`` is the
    ``(False, message)`` result to return when validation fails.
    """
    stake = session.get(LiquidityStake, (stake_id, chain_id))
    if not stake:
        return None, None, None, (False, f"Stake {stake_id} not found")
    if stake.address != sender or stake.pool_id != pool_id:
        return None, None, None, (False, "Stake does not belong to sender")
    if stake.status != "active":
        return None, None, None, (False, f"Stake is not active: {stake.status}")
    now = _v18_apply_time(block_version, block_time) or datetime.now(UTC)
    lock_error = _withdraw_lock_error(stake, now)
    if lock_error is not None:
        return None, None, None, (False, lock_error)

    sender_account = session.get(Account, (chain_id, sender))
    if not sender_account:
        return None, None, None, (False, f"Sender account not found: {sender}")
    if v24_rules_is_active():
        _sbal, _snonce, _sexists = read_current_account(session, chain_id, sender)
        sender_fee_balance = _sbal if _sbal is not None else 0
    else:
        sender_fee_balance = sender_account.balance
    if sender_fee_balance < fee:
        return None, None, None, (False, f"Insufficient balance for fee: {sender_fee_balance} < {fee}")
    return stake, sender_account, now, None


def _pool_pair_balances(
    session: Session,
    chain_id: str,
    main_account: Account,
    treasury_account: Account,
) -> tuple[int, int]:
    """(main reserves, treasury rewards) balances under the v24 read rule."""
    if v24_rules_is_active():
        _mbal, _mnonce, _mexists = read_current_account(session, chain_id, pool_main_address())
        main_balance = _mbal if _mbal is not None else 0
        _tbal2, _tnonce2, _texists2 = read_current_account(session, chain_id, pool_treasury_address())
        treasury_balance2 = _tbal2 if _tbal2 is not None else 0
        return main_balance, treasury_balance2
    return main_account.balance, treasury_account.balance


def _payout_liquidity_withdraw(
    session: Session,
    chain_id: str,
    sender: str,
    stake: LiquidityStake,
    pool: Any,
    rewards: int,
    total_return: int,
    fee: int,
    now: datetime,
    cache: Any,
    tx_hash: str,
) -> tuple[bool, str]:
    """Settle a validated LIQUIDITY_WITHDRAW: fee debit, principal+rewards payout."""
    sender_account = session.get(Account, (chain_id, sender))
    if not sender_account:
        return False, f"Sender account not found: {sender}"
    accounts = _ensure_pool_accounts(session, chain_id)
    main_account = accounts[pool_main_address()]
    treasury_account = accounts[pool_treasury_address()]

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
    stake.updated_at = now
    pool.total_staked -= stake.amount
    if pool.total_staked <= 0:
        pool.total_staked = 0
        pool.reward_per_share = Decimal("0")
    pool.updated_at = now
    session.add(stake)
    session.add(pool)
    session.flush()

    _invalidate_account_cache(chain_id, sender, cache)
    _invalidate_account_cache(chain_id, pool_main_address(), cache)
    if rewards > 0:
        _invalidate_account_cache(chain_id, pool_treasury_address(), cache)
    logger.info("LIQUIDITY_WITHDRAW %s: %s withdrew %s + %s rewards", tx_hash, sender, stake.amount, rewards)
    return (True, f"Withdrew {total_return} compute-units")


def apply_liquidity_withdraw(
    session: Session,
    chain_id: str,
    tx_data: dict[str, Any],
    tx_hash: str,
    cache: Any,
    *,
    block_version: int | None = None,
    block_time: datetime | None = None,
) -> tuple[bool, str]:
    """Apply a LIQUIDITY_WITHDRAW transaction."""
    sender = _to_ait_address(tx_data.get("from", ""))
    payload = tx_data.get("payload") or {}
    pool_id = payload.get("pool_id", "main")
    stake_id = payload.get("stake_id", "")
    fee = tx_data.get("fee", 0)

    stake, sender_account, now, error = _validate_liquidity_withdraw(
        session, chain_id, sender, pool_id, stake_id, fee, block_version=block_version, block_time=block_time
    )
    if error is not None:
        return error
    if stake is None or sender_account is None or now is None:
        return False, "Liquidity withdraw validation failed"

    pool = _get_or_create_pool(session, chain_id, pool_id)

    # Realize fixed APY and compute total rewards
    _realize_fixed_apy(session, chain_id, pool, stake, now=now)
    rewards = _pending_rewards(stake, pool)

    accounts = _ensure_pool_accounts(session, chain_id)
    main_account = accounts[pool_main_address()]
    treasury_account = accounts[pool_treasury_address()]

    total_return = stake.amount + rewards
    main_balance, treasury_balance2 = _pool_pair_balances(session, chain_id, main_account, treasury_account)
    if main_balance < stake.amount:
        return (False, f"Pool main reserves insufficient: {main_balance} < {stake.amount}")
    if rewards > 0 and treasury_balance2 < rewards:
        return (False, f"Pool treasury has insufficient rewards: {treasury_balance2} < {rewards}")

    return _payout_liquidity_withdraw(session, chain_id, sender, stake, pool, rewards, total_return, fee, now, cache, tx_hash)
