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

from sqlmodel import Session, select
from sqlmodel import func as sql_func

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

    def record_transaction(
        self,
        session: Session,
        sender: str,
        recipient: str,
        amount: int,
        fee: int,
        tx_hash: str,
        chain_id: str,
        tx_type: str = "transfer"
    ) -> tuple[BalanceChange, BalanceChange]:
        """
        Record balance changes from a transaction.
        
        Returns sender and recipient balance changes.
        """
        # Get sender account
        sender_account = session.get(Account, (chain_id, sender))
        if not sender_account:
            raise ValueError(f"Sender account not found: {sender}")

        sender_balance_before = sender_account.balance

        # Deduct amount + fee from sender
        total_deduction = amount + fee
        if sender_account.balance < total_deduction:
            raise ValueError(
                f"Insufficient balance: {sender_account.balance} < {total_deduction}"
            )

        sender_account.balance -= total_deduction
        sender_account.nonce += 1
        session.add(sender_account)

        sender_change = BalanceChange(
            address=sender,
            chain_id=chain_id,
            change_type=BalanceChangeType.transaction_send,
            amount=-amount,
            fee=-fee,
            balance_before=sender_balance_before,
            balance_after=sender_account.balance,
            tx_hash=tx_hash,
            timestamp=datetime.now(UTC),
            details={"recipient": recipient, "tx_type": tx_type}
        )

        # Get or create recipient account
        recipient_account = session.get(Account, (chain_id, recipient))
        recipient_balance_before = 0

        if not recipient_account:
            recipient_account = Account(
                chain_id=chain_id,
                address=recipient,
                balance=0,
                nonce=0
            )
            session.add(recipient_account)
        else:
            recipient_balance_before = recipient_account.balance

        # Add amount to recipient
        recipient_account.balance += amount
        session.add(recipient_account)

        recipient_change = BalanceChange(
            address=recipient,
            chain_id=chain_id,
            change_type=BalanceChangeType.transaction_receive,
            amount=amount,
            fee=0,
            balance_before=recipient_balance_before,
            balance_after=recipient_account.balance,
            tx_hash=tx_hash,
            timestamp=datetime.now(UTC),
            details={"sender": sender, "tx_type": tx_type}
        )

        logger.info(
            f"Transaction recorded: {sender[:16]}... -> {recipient[:16]}... "
            f"Amount: {amount}, Fee: {fee}"
        )

        return sender_change, recipient_change

    def record_stake(
        self,
        session: Session,
        address: str,
        amount: int,
        chain_id: str,
        stake_id: int
    ) -> BalanceChange:
        """Record balance change from staking (lock tokens)"""
        account = session.get(Account, (chain_id, address))
        if not account:
            raise ValueError(f"Account not found: {address}")

        balance_before = account.balance

        if account.balance < amount:
            raise ValueError(f"Insufficient balance to stake: {account.balance} < {amount}")

        # Deduct staked amount
        account.balance -= amount
        session.add(account)

        change = BalanceChange(
            address=address,
            chain_id=chain_id,
            change_type=BalanceChangeType.staking_lock,
            amount=-amount,
            fee=0,
            balance_before=balance_before,
            balance_after=account.balance,
            tx_hash=None,
            timestamp=datetime.now(UTC),
            details={"stake_id": stake_id, "operation": "stake"}
        )

        logger.info(f"Stake recorded: {address[:16]}... staked {amount}")

        return change

    def record_unstake(
        self,
        session: Session,
        address: str,
        amount: int,
        chain_id: str,
        stake_id: int
    ) -> BalanceChange:
        """Record balance change from unstaking (return tokens)"""
        account = session.get(Account, (chain_id, address))
        if not account:
            # Recreate account if deleted
            account = Account(chain_id=chain_id, address=address, balance=0, nonce=0)
            session.add(account)

        balance_before = account.balance

        # Return staked amount
        account.balance += amount
        session.add(account)

        change = BalanceChange(
            address=address,
            chain_id=chain_id,
            change_type=BalanceChangeType.staking_unlock,
            amount=amount,
            fee=0,
            balance_before=balance_before,
            balance_after=account.balance,
            tx_hash=None,
            timestamp=datetime.now(UTC),
            details={"stake_id": stake_id, "operation": "unstake"}
        )

        logger.info(f"Unstake recorded: {address[:16]}... returned {amount}")

        return change

    def record_bridge_lock(
        self,
        session: Session,
        address: str,
        amount: int,
        fee: int,
        chain_id: str,
        transfer_id: str
    ) -> BalanceChange:
        """Record balance change from bridge lock"""
        account = session.get(Account, (chain_id, address))
        if not account:
            raise ValueError(f"Account not found: {address}")

        balance_before = account.balance

        total = amount + fee
        if account.balance < total:
            raise ValueError(f"Insufficient balance for bridge: {account.balance} < {total}")

        # Deduct amount + fee
        account.balance -= total
        session.add(account)

        change = BalanceChange(
            address=address,
            chain_id=chain_id,
            change_type=BalanceChangeType.bridge_lock,
            amount=-amount,
            fee=-fee,
            balance_before=balance_before,
            balance_after=account.balance,
            tx_hash=transfer_id,
            timestamp=datetime.now(UTC),
            details={"transfer_id": transfer_id, "operation": "lock"}
        )

        logger.info(f"Bridge lock recorded: {address[:16]}... locked {amount} (fee: {fee})")

        return change

    def record_bridge_release(
        self,
        session: Session,
        address: str,
        amount: int,
        chain_id: str,
        transfer_id: str
    ) -> BalanceChange:
        """Record balance change from bridge release (on target chain)"""
        account = session.get(Account, (chain_id, address))
        if not account:
            account = Account(chain_id=chain_id, address=address, balance=0, nonce=0)
            session.add(account)

        balance_before = account.balance

        # Add released amount
        account.balance += amount
        session.add(account)

        change = BalanceChange(
            address=address,
            chain_id=chain_id,
            change_type=BalanceChangeType.bridge_release,
            amount=amount,
            fee=0,
            balance_before=balance_before,
            balance_after=account.balance,
            tx_hash=transfer_id,
            timestamp=datetime.now(UTC),
            details={"transfer_id": transfer_id, "operation": "release"}
        )

        logger.info(f"Bridge release recorded: {address[:16]}... received {amount}")

        return change

    def get_balance(
        self,
        address: str,
        chain_id: str
    ) -> int | None:
        """Get current balance for an address"""
        with self._session_factory() as session:
            account = session.get(Account, (chain_id, address))
            return account.balance if account else None

    def get_balance_breakdown(
        self,
        address: str,
        chain_id: str
    ) -> dict[str, Any]:
        """
        Get detailed balance breakdown:
        - Available balance
        - Staked amount
        - Pending bridge locks
        """
        with self._session_factory() as session:
            # Get account balance
            account = session.get(Account, (chain_id, address))
            available = account.balance if account else 0

            # Get staked amount
            statement = select(sql_func.sum(Stake.amount)).where(
                Stake.chain_id == chain_id,
                Stake.address == address,
                Stake.status == "active"
            )
            staked = session.exec(statement).one() or 0

            # Get pending bridge locks
            statement = select(sql_func.sum(CrossChainTransfer.amount)).where(
                CrossChainTransfer.source_chain == chain_id,
                CrossChainTransfer.sender == address,
                CrossChainTransfer.status == "pending"
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
                "timestamp": datetime.now(UTC).isoformat()
            }

    def reconcile_balance(
        self,
        address: str,
        chain_id: str
    ) -> dict[str, Any]:
        """
        Reconcile balance by checking consistency across all operations.
        
        Verifies that the current balance matches what we'd expect
        based on all recorded operations.
        """
        with self._session_factory() as session:
            # Get current balance
            account = session.get(Account, (chain_id, address))
            current_balance = account.balance if account else 0

            # Calculate expected balance from all sources
            # 1. Initial balance (from account creation/faucet)
            initial = 0  # Would track from genesis

            # 2. Sum of all received amounts
            received_stmt = select(sql_func.sum(Transaction.value)).where(
                Transaction.chain_id == chain_id,
                Transaction.recipient == address
            )
            total_received = session.exec(received_stmt).one() or 0

            # 3. Sum of all sent amounts (including fees)
            sent_stmt = select(sql_func.sum(Transaction.value + Transaction.fee)).where(
                Transaction.chain_id == chain_id,
                Transaction.sender == address
            )
            total_sent = session.exec(sent_stmt).one() or 0

            # 4. Staking changes
            staked_stmt = select(sql_func.sum(Stake.amount)).where(
                Stake.chain_id == chain_id,
                Stake.address == address,
                Stake.status == "active"
            )
            total_staked = session.exec(staked_stmt).one() or 0

            # Calculate expected balance
            expected_balance = initial + total_received - total_sent - total_staked

            # Check for mismatch
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
                    "total_fees_paid": 0,  # Included in total_sent
                    "total_staked": total_staked
                }
            }

            if mismatch:
                logger.warning(
                    f"Balance mismatch for {address[:16]}...: "
                    f"current={current_balance}, expected={expected_balance}"
                )

            return result


# Global instance
_balance_tracker: BalanceTracker | None = None


def init_balance_tracker(session_factory: Any) -> BalanceTracker:
    """Initialize global balance tracker"""
    global _balance_tracker
    _balance_tracker = BalanceTracker(session_factory)
    return _balance_tracker


def get_balance_tracker() -> BalanceTracker | None:
    """Get global balance tracker"""
    return _balance_tracker
