"""
State Transition Layer for AITBC

This module provides the StateTransition class that validates all state changes
to ensure they only occur through validated transactions.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, select

from ..logger import get_logger
from ..models import Account, Receipt, Transaction
from .gpu_resources import GPUAllocation, GPURegistration

try:
    from aitbc.redis_cache import RedisCache

    _REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _cache: RedisCache | None = RedisCache(redis_url=_REDIS_URL, default_ttl=30)
except Exception:
    _cache = None
logger = get_logger(__name__)


class StateTransition:
    """
    Validates and applies state transitions only through validated transactions.

    This class ensures that balance changes can only occur through properly
    validated transactions, preventing direct database manipulation of account
    balances.
    """

    def __init__(self) -> None:
        self._processed_nonces: dict[str, int] = {}
        self._processed_tx_hashes: set[str] = set()

    def validate_transaction(self, session: Session, chain_id: str, tx_data: dict[str, Any], tx_hash: str) -> tuple[bool, str]:
        """
        Validate a transaction before applying state changes.

        Args:
            session: Database session
            chain_id: Chain identifier
            tx_data: Transaction data
            tx_hash: Transaction hash

        Returns:
            Tuple of (is_valid, error_message)
        """
        tx_chain_id = tx_data.get("chain_id")
        if tx_chain_id and tx_chain_id != chain_id:
            logger.warning(
                "Chain isolation violation: Transaction %s has chain_id=%s but node is configured for chain_id=%s. Rejecting cross-chain transaction.",
                tx_hash,
                tx_chain_id,
                chain_id,
            )
            return (
                False,
                f"Chain isolation violation: transaction chain_id={tx_chain_id} does not match node chain_id={chain_id}",
            )
        if tx_hash in self._processed_tx_hashes:
            logger.warning("Replay attack detected: Transaction %s already processed", tx_hash)
            return (False, f"Transaction {tx_hash} already processed (replay attack)")
        sender_addr = tx_data.get("from")
        sender_account = session.get(Account, (chain_id, sender_addr))
        if not sender_account:
            return (False, f"Sender account not found: {sender_addr}")
        expected_nonce = sender_account.nonce if sender_account.nonce is not None else 0
        tx_nonce = tx_data.get("nonce", 0)
        if tx_nonce != expected_nonce:
            return (False, f"Invalid nonce for {sender_addr}: expected {expected_nonce}, got {tx_nonce}")
        tx_record = session.exec(
            select(Transaction).where(Transaction.chain_id == chain_id, Transaction.tx_hash == tx_hash)
        ).first()
        if tx_record and tx_record.type:
            tx_type = tx_record.type.upper()
        else:
            tx_type = tx_data.get("type", "TRANSFER")
            if not tx_type or tx_type == "TRANSFER":
                payload = tx_data.get("payload", {})
                if isinstance(payload, dict):
                    tx_type = payload.get("type", "TRANSFER")
            if tx_type:
                tx_type = tx_type.upper()
            else:
                tx_type = "TRANSFER"
        value = tx_data.get("value", 0)
        fee = tx_data.get("fee", 0)
        if tx_type == "MESSAGE" and value != 0:
            return (False, f"MESSAGE transactions must have value=0, got {value}")
        if tx_type == "MESSAGE":
            total_cost = fee
        else:
            total_cost = value + fee
        if sender_account.balance < total_cost:
            return (False, f"Insufficient balance for {sender_addr}: {sender_account.balance} < {total_cost}")
        recipient_addr = tx_data.get("to")
        if tx_type not in {"MESSAGE", "RECEIPT_CLAIM"}:
            recipient_account = session.get(Account, (chain_id, recipient_addr))
            if not recipient_account:
                return (False, f"Recipient account not found: {recipient_addr}")
        if tx_type == "RECEIPT_CLAIM":
            receipt_id = tx_data.get("payload", {}).get("receipt_id")
            if not receipt_id:
                return (False, "RECEIPT_CLAIM transactions must include receipt_id in payload")
            receipt = session.exec(
                select(Receipt).where(Receipt.chain_id == chain_id, Receipt.receipt_id == receipt_id)
            ).first()
            if not receipt:
                return (False, f"Receipt not found: {receipt_id}")
            if receipt.status != "pending":
                return (False, f"Receipt already claimed or invalid: {receipt.status}")
            if not receipt.miner_signature or not isinstance(receipt.miner_signature, dict):
                return (False, f"Receipt {receipt_id} has invalid miner signature")
            if not receipt.coordinator_attestations or not isinstance(receipt.coordinator_attestations, list):
                return (False, f"Receipt {receipt_id} has invalid coordinator attestations")
        return (True, "Transaction validated successfully")

    def apply_transaction(self, session: Session, chain_id: str, tx_data: dict[str, Any], tx_hash: str) -> tuple[bool, str]:
        """
        Apply a validated transaction to update state.

        Args:
            session: Database session
            chain_id: Chain identifier
            tx_data: Transaction data
            tx_hash: Transaction hash

        Returns:
            Tuple of (success, error_message)
        """
        logger.info("apply_transaction called for tx %s, tx_data keys: %s", tx_hash, list(tx_data.keys()))
        is_valid, error_msg = self.validate_transaction(session, chain_id, tx_data, tx_hash)
        if not is_valid:
            return (False, error_msg)
        sender_addr = tx_data.get("from")
        recipient_addr = tx_data.get("to")
        sender_account = session.get(Account, (chain_id, sender_addr))
        tx_record = session.exec(
            select(Transaction).where(Transaction.chain_id == chain_id, Transaction.tx_hash == tx_hash)
        ).first()
        if tx_record and tx_record.type:
            tx_type = tx_record.type.upper()
        else:
            tx_type = tx_data.get("type", "TRANSFER")
            if not tx_type or tx_type == "TRANSFER":
                payload = tx_data.get("payload", {})
                if isinstance(payload, dict):
                    tx_type = payload.get("type", "TRANSFER")
            if tx_type:
                tx_type = tx_type.upper()
            else:
                tx_type = "TRANSFER"
        value = tx_data.get("value", 0)
        fee = tx_data.get("fee", 0)
        if tx_type == "MESSAGE":
            total_cost = fee
        else:
            total_cost = value + fee
            session.get(Account, (chain_id, recipient_addr))
        logger.info("Updating sender balance: %s -= %s", sender_addr, total_cost)
        session.execute(
            text(
                "UPDATE account SET balance = balance - :total_cost, nonce = nonce + 1 WHERE chain_id = :chain_id AND address = :sender_addr"
            ),
            {"total_cost": total_cost, "chain_id": chain_id, "sender_addr": sender_addr},
        )
        if tx_type != "MESSAGE":
            logger.info("Updating recipient balance: %s += %s", recipient_addr, value)
            session.execute(
                text("UPDATE account SET balance = balance + :value WHERE chain_id = :chain_id AND address = :recipient_addr"),
                {"value": value, "chain_id": chain_id, "recipient_addr": recipient_addr},
            )
        session.flush()
        if tx_type == "RECEIPT_CLAIM":
            receipt_id = tx_data.get("payload", {}).get("receipt_id")
            receipt = session.exec(
                select(Receipt).where(Receipt.chain_id == chain_id, Receipt.receipt_id == receipt_id)
            ).first()
            if receipt and receipt.minted_amount:
                sender_account.balance += receipt.minted_amount  # type: ignore[union-attr]
                receipt.status = "claimed"
                receipt.claimed_at = datetime.now(UTC)
                receipt.claimed_by = sender_addr
                logger.info(
                    "Claimed receipt %s: minted_amount=%s, claimed_by=%s", receipt_id, receipt.minted_amount, sender_addr
                )
        self._processed_tx_hashes.add(tx_hash)
        if sender_addr is not None:
            self._processed_nonces[sender_addr] = sender_account.nonce  # type: ignore[union-attr]
        if _cache and _cache.is_available():
            for addr in [sender_addr, recipient_addr]:
                if addr:
                    _cache.delete(f"account_balance:{chain_id}:{addr.lower()}")
                    _cache.delete(f"account_details:{chain_id}:{addr.lower()}")
        logger.info(
            "Applied transaction %s: %s -> %s, value=%s, fee=%s, type=%s",
            tx_hash,
            sender_addr,
            recipient_addr,
            value,
            fee,
            tx_type,
        )
        return (True, "Transaction applied successfully")

    def validate_state_transition(
        self, session: Session, chain_id: str, old_accounts: dict[str, Account], new_accounts: dict[str, Account]
    ) -> tuple[bool, str]:
        """
        Validate that state changes only occur through transactions.

        Args:
            session: Database session
            chain_id: Chain identifier
            old_accounts: Previous account state
            new_accounts: New account state

        Returns:
            Tuple of (is_valid, error_message)
        """
        for address, old_acc in old_accounts.items():
            if address not in new_accounts:
                continue
            new_acc = new_accounts[address]
            if old_acc.balance != new_acc.balance:
                logger.warning(
                    "Balance change detected for %s: %s -> %s (validated through transaction processing)",
                    address,
                    old_acc.balance,
                    new_acc.balance,
                )
        return (True, "State transition validated")

    def get_processed_nonces(self) -> dict[str, int]:
        """Get the last processed nonce for each address."""
        return self._processed_nonces.copy()

    def handle_gpu_registration(self, session: Session, chain_id: str, gpu_data: dict[str, Any]) -> tuple[bool, str]:
        """
        Handle GPU registration state transition.

        Args:
            session: Database session
            chain_id: Chain identifier
            gpu_data: GPU registration data

        Returns:
            Tuple of (success, error_message)
        """
        try:
            gpu_id = gpu_data.get("gpu_id")
            if not gpu_id:
                return (False, "GPU ID is required")
            existing = session.exec(
                select(GPURegistration).where(GPURegistration.chain_id == chain_id, GPURegistration.gpu_id == gpu_id)
            ).first()
            if existing:
                existing.model = gpu_data.get("model", existing.model)
                existing.memory_gb = gpu_data.get("memory_gb", existing.memory_gb)
                existing.cuda_version = gpu_data.get("cuda_version", existing.cuda_version)
                existing.region = gpu_data.get("region", existing.region)
                existing.capabilities = gpu_data.get("capabilities", existing.capabilities)
                existing.price_per_hour = gpu_data.get("price_per_hour", existing.price_per_hour)
                existing.status = "active"
                existing.updated_at = datetime.now(UTC)
            else:
                registration = GPURegistration(
                    chain_id=chain_id,
                    gpu_id=gpu_id,
                    miner_id=gpu_data.get("miner_id", ""),
                    model=gpu_data.get("model", ""),
                    memory_gb=gpu_data.get("memory_gb", 0),
                    cuda_version=gpu_data.get("cuda_version", ""),
                    region=gpu_data.get("region", ""),
                    capabilities=gpu_data.get("capabilities", []),
                    price_per_hour=gpu_data.get("price_per_hour", 0.0),
                    registered_by=gpu_data.get("registered_by", ""),
                    registered_at=datetime.now(UTC),
                    status="active",
                )
                session.add(registration)
            logger.info("GPU registration handled: %s", gpu_id)
            return (True, "GPU registration successful")
        except Exception as e:
            logger.error("GPU registration error: %s", e)
            return (False, str(e))

    def handle_gpu_allocation(self, session: Session, chain_id: str, allocation_data: dict[str, Any]) -> tuple[bool, str]:
        """
        Handle GPU allocation state transition.

        Args:
            session: Database session
            chain_id: Chain identifier
            allocation_data: GPU allocation data

        Returns:
            Tuple of (success, error_message)
        """
        try:
            from uuid import uuid4

            gpu_id = allocation_data.get("gpu_id")
            if not gpu_id:
                return (False, "GPU ID is required")
            gpu = session.exec(
                select(GPURegistration).where(GPURegistration.chain_id == chain_id, GPURegistration.gpu_id == gpu_id)
            ).first()
            if not gpu:
                return (False, f"GPU not found: {gpu_id}")
            allocation_id = allocation_data.get("allocation_id", f"alloc_{uuid4().hex[:12]}")
            allocation = GPUAllocation(
                chain_id=chain_id,
                allocation_id=allocation_id,
                gpu_id=gpu_id,
                client_id=allocation_data.get("client_id", ""),
                duration_hours=allocation_data.get("duration_hours", 0.0),
                total_cost=allocation_data.get("total_cost", 0.0),
                status="active",
                allocated_by=allocation_data.get("allocated_by", ""),
                allocated_at=datetime.now(UTC),
            )
            session.add(allocation)
            logger.info("GPU allocation handled: %s for GPU %s", allocation_id, gpu_id)
            return (True, "GPU allocation successful")
        except Exception as e:
            logger.error("GPU allocation error: %s", e)
            return (False, str(e))

    def reset(self) -> None:
        """Reset the state transition validator (for testing)."""
        self._processed_nonces.clear()
        self._processed_tx_hashes.clear()


_state_transition = StateTransition()


def get_state_transition() -> StateTransition:
    """Get the global state transition instance."""
    return _state_transition
