"""
Balance Tracker Service - Real-time balance reconciliation

This module ensures account balances are properly tracked and reconciled
across all blockchain operations including:
- Transactions (send/receive)
- Staking (lock/unlock)
- Bridge transfers (lock/mint)
- Fees
- Rewards
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlmodel import select
from sqlmodel import func as sql_func

from ..base_models import address_spellings
from ..logger import get_logger
from ..models import Account, CrossChainTransfer, Stake, Transaction

logger = get_logger(__name__)


class BalanceChangeType(Enum):
    """Types of balance changes"""

    transaction_send = "transaction_send"
    transaction_receive = "transaction_receive"
    staking_lock = "staking_lock"
    staking_unlock = "staking_unlock"
    bridge_lock = "bridge_lock"
    bridge_release = "bridge_release"
    fee = "fee"
    reward = "reward"
    faucet = "faucet"


@dataclass
class BalanceChange:
    """Record of a balance change"""

    address: str
    chain_id: str
    change_type: BalanceChangeType
    amount: int
    fee: int
    balance_before: int
    balance_after: int
    tx_hash: str | None
    timestamp: datetime
    details: dict[str, Any]


class BalanceTracker:
    """
    Real-time balance tracking and reconciliation service.

    Ensures all balance changes are properly recorded and can be
    audited for consistency.
    """

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory
        self._pending_changes: list[BalanceChange] = []

    # The five record_* mutators that used to live here (record_transaction,
    # record_stake, record_unstake, record_bridge_lock, record_bridge_release)
    # were removed. They debited and credited ``account.balance`` directly,
    # outside block processing, which is exactly what desynchronises the
    # account table from the block headers -- the state root is a full scan of
    # that table. Nothing called them: the only live uses of this class are the
    # two read-only methods below. Balance movement belongs in the state
    # transition, reached by queueing a transfer; see ``protocol_escrow``.

    def get_balance(self, address: str, chain_id: str) -> int | None:
        """Get current balance for an address"""
        with self._session_factory() as session:
            account = session.get(Account, (chain_id, address))
            return account.balance if account else None

    def get_balance_breakdown(self, address: str, chain_id: str) -> dict[str, Any]:
        """
        Get detailed balance breakdown:
        - Available balance
        - Staked amount
        - Pending bridge locks
        """
        with self._session_factory() as session:
            account = session.get(Account, (chain_id, address))
            available = account.balance if account else 0
            statement = select(sql_func.sum(Stake.amount)).where(
                Stake.chain_id == chain_id, Stake.address == address, Stake.status == "active"
            )
            staked = session.exec(statement).one() or 0
            statement = select(sql_func.sum(CrossChainTransfer.amount)).where(
                CrossChainTransfer.source_chain == chain_id,
                CrossChainTransfer.sender == address,
                CrossChainTransfer.status == "pending",
            )
            bridge_locked = session.exec(statement).one() or 0
            total = available + staked + bridge_locked
            return {
                "address": address,
                "chain_id": chain_id,
                "available_balance": available,
                "staked": staked,
                "bridge_locked": bridge_locked,
                "total_balance": total,
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def reconcile_balance(self, address: str, chain_id: str) -> dict[str, Any]:
        """
        Reconcile balance by checking consistency across all operations.

        Verifies that the current balance matches what we'd expect
        based on all recorded operations.
        """
        with self._session_factory() as session:
            account = session.get(Account, (chain_id, address))
            current_balance = account.balance if account else 0
            initial = 0
            received_stmt = select(sql_func.sum(Transaction.value)).where(
                Transaction.chain_id == chain_id,
                # Verbatim column, so match every spelling of the account (V23-65).
                sql_func.lower(Transaction.recipient).in_(address_spellings(address)),
            )
            total_received = session.exec(received_stmt).one() or 0
            sent_stmt = select(sql_func.sum(Transaction.value + Transaction.fee)).where(
                Transaction.chain_id == chain_id,
                sql_func.lower(Transaction.sender).in_(address_spellings(address)),
            )
            total_sent = session.exec(sent_stmt).one() or 0
            staked_stmt = select(sql_func.sum(Stake.amount)).where(
                Stake.chain_id == chain_id, Stake.address == address, Stake.status == "active"
            )
            total_staked = session.exec(staked_stmt).one() or 0
            expected_balance = initial + total_received - total_sent - total_staked
            mismatch = current_balance != expected_balance
            result = {
                "address": address,
                "chain_id": chain_id,
                "current_balance": current_balance,
                "expected_balance": expected_balance,
                "mismatch": mismatch,
                "components": {
                    "initial": initial,
                    "total_received": total_received,
                    "total_sent": total_sent,
                    "total_fees_paid": 0,
                    "total_staked": total_staked,
                },
            }
            if mismatch:
                logger.warning(
                    "Balance mismatch for %s...: current=%s, expected=%s", address[:16], current_balance, expected_balance
                )
            return result


_balance_tracker: BalanceTracker | None = None


def init_balance_tracker(session_factory: Any) -> BalanceTracker:
    """Initialize global balance tracker"""
    global _balance_tracker
    _balance_tracker = BalanceTracker(session_factory)
    return _balance_tracker


def get_balance_tracker() -> BalanceTracker | None:
    """Get global balance tracker"""
    return _balance_tracker
