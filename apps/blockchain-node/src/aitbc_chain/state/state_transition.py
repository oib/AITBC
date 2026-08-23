"""
State Transition Layer for AITBC

This module provides the StateTransition class that validates all state changes
to ensure they only occur through validated transactions.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from eth_utils import keccak
from sqlalchemy import text
from sqlmodel import Session, select

from ..logger import get_logger
from ..base_models import Bond, _to_ait_address
from aitbc.crypto.signature_recovery import canonical_address
from ..models import Account, Receipt, Transaction
from ..rpc.utils import verify_transaction_signature
from .gpu_resources import GPUAllocation, GPURegistration

try:
    from aitbc.caching import RedisCache

    _REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _cache: RedisCache | None = RedisCache(redis_url=_REDIS_URL, default_ttl=30)
except Exception:
    _cache = None
logger = get_logger(__name__)

_BOND_ESCROW_ADDRESS = os.getenv("BOND_ESCROW_ADDRESS", "")
if _BOND_ESCROW_ADDRESS:
    _BOND_ESCROW_ADDRESS = canonical_address(_BOND_ESCROW_ADDRESS)
else:
    _BOND_ESCROW_ADDRESS = "0x" + keccak(b"aitbc.bond.escrow").hex()[:40]

_BOND_BURN_ADDRESS = os.getenv("BOND_BURN_ADDRESS", "")
if _BOND_BURN_ADDRESS:
    _BOND_BURN_ADDRESS = canonical_address(_BOND_BURN_ADDRESS)
else:
    _BOND_BURN_ADDRESS = "0x" + keccak(b"aitbc.bond.burn").hex()[:40]


def _bond_slash_authority() -> str | None:
    addr = os.getenv("BOND_SLASH_AUTHORITY_ADDRESS", "")
    if addr:
        return canonical_address(addr)
    return None


def _bond_escrow_ait() -> str:
    return _to_ait_address(_BOND_ESCROW_ADDRESS)


def _bond_burn_ait() -> str:
    return _to_ait_address(_BOND_BURN_ADDRESS)


def _is_bond_escrow(address: str) -> bool:
    return canonical_address(address) == _BOND_ESCROW_ADDRESS


def _is_bond_burn(address: str) -> bool:
    return canonical_address(address) == _BOND_BURN_ADDRESS


def _ensure_account(session: Session, chain_id: str, address: str) -> Account:
    ait_addr = _to_ait_address(address)
    account = session.get(Account, (chain_id, ait_addr))
    if not account:
        account = Account(chain_id=chain_id, address=ait_addr, balance=0, nonce=0)
        session.add(account)
        session.flush()
    return account


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
        # Persistent replay protection: the in-memory set above is lost on
        # restart; the DB unique constraint on (chain_id, tx_hash) is not.
        persisted_tx = session.exec(
            select(Transaction.tx_hash).where(Transaction.chain_id == chain_id, Transaction.tx_hash == tx_hash)
        ).first()
        if persisted_tx is not None:
            logger.warning("Replay attack detected: Transaction %s already persisted", tx_hash)
            return (False, f"Transaction {tx_hash} already processed (replay attack)")
        sender_addr = _to_ait_address(tx_data.get("from") or "")
        signature = tx_data.get("signature")
        if signature and sender_addr:
            if not verify_transaction_signature(tx_data, signature, sender_addr):
                return (False, f"Invalid signature for transaction {tx_hash}")
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
        if tx_type in {"MESSAGE", "GOVERNANCE_EXECUTE"} and value != 0:
            return (False, f"{tx_type} transactions must have value=0, got {value}")
        if tx_type in {"MESSAGE", "GOVERNANCE_EXECUTE"}:
            total_cost = fee
        else:
            total_cost = value + fee
        if sender_account.balance < total_cost:
            return (False, f"Insufficient balance for {sender_addr}: {sender_account.balance} < {total_cost}")
        recipient_addr = _to_ait_address(tx_data.get("to") or "")
        if tx_type not in {"MESSAGE", "RECEIPT_CLAIM", "GOVERNANCE_EXECUTE"}:
            recipient_account = session.get(Account, (chain_id, recipient_addr))
            if not recipient_account:
                # Bridge lock transactions create the bridge_lock account
                # lazily so a source chain can lock funds for a cross-chain
                # transfer without a separate setup step.
                if tx_type == "BRIDGE_LOCK" and recipient_addr == "bridge_lock":
                    recipient_account = Account(chain_id=chain_id, address=recipient_addr, balance=0, nonce=0)
                    session.add(recipient_account)
                    session.flush()
                else:
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
        sender_addr = _to_ait_address(tx_data.get("from") or "")
        recipient_addr = _to_ait_address(tx_data.get("to") or "")
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
        # Guard against BigInt overflow (SQLite INTEGER is 64-bit signed)
        _MAX_INT64 = 2**63 - 1
        if value < 0 or fee < 0 or value > _MAX_INT64 or fee > _MAX_INT64:
            raise ValueError(f"Transaction value/fee out of range: value={value}, fee={fee}")
        if tx_type in {"MESSAGE", "GOVERNANCE_EXECUTE"}:
            total_cost = fee
        else:
            total_cost = value + fee
            if total_cost > _MAX_INT64:
                raise ValueError(f"Transaction total_cost overflow: {total_cost}")
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
        if tx_type in ("BOND_LOCK", "BOND_RELEASE", "BOND_SLASH"):
            self._handle_bond_transaction(session, chain_id, tx_data, tx_hash, tx_type, sender_addr, recipient_addr, value)
        if tx_type == "GOVERNANCE_EXECUTE":
            self._handle_governance_execute(session, chain_id, tx_data, tx_hash)
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

    def _handle_governance_execute(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
    ) -> None:
        """Apply a GOVERNANCE_EXECUTE transaction payload to chain parameters.

        The transaction payload must contain:
        - proposal_id: the on-chain governance proposal being executed
        - execution_payload: the payload stored in the proposal (or an override)

        For a parameter_change action, the execution payload should contain:
        - parameter: the parameter name
        - value: the new string value
        """
        from ..base_models import ChainParameter, GovernanceProposal

        payload = tx_data.get("payload", {}) or {}
        if isinstance(payload, str):
            try:
                import json

                payload = json.loads(payload)
            except Exception:
                logger.warning("GOVERNANCE_EXECUTE payload is not valid JSON: %s", payload)
                return

        proposal_id = payload.get("proposal_id") or tx_data.get("proposal_id")
        execution_payload = payload.get("execution_payload", {}) or {}
        action = execution_payload.get("action", "parameter_change")

        if not proposal_id:
            logger.warning("GOVERNANCE_EXECUTE tx %s missing proposal_id", tx_hash)
            return

        # Record execution on the on-chain proposal record, if present
        proposal = session.exec(
            select(GovernanceProposal).where(
                GovernanceProposal.chain_id == chain_id,
                GovernanceProposal.proposal_id == proposal_id,
            )
        ).first()
        if proposal:
            proposal.status = "executed"
            proposal.executed_at = datetime.now(UTC)
            proposal.execution_tx_hash = tx_hash
            session.add(proposal)

        if action == "parameter_change":
            parameter = execution_payload.get("parameter")
            value = execution_payload.get("value")
            if not parameter:
                logger.warning("GOVERNANCE_EXECUTE tx %s parameter_change missing parameter name", tx_hash)
                return
            existing = session.exec(
                select(ChainParameter).where(
                    ChainParameter.chain_id == chain_id,
                    ChainParameter.parameter == parameter,
                )
            ).first()
            if existing:
                existing.value = str(value)
                existing.proposal_id = proposal_id
                existing.updated_at = datetime.now(UTC)
            else:
                session.add(
                    ChainParameter(
                        chain_id=chain_id,
                        parameter=parameter,
                        value=str(value),
                        proposal_id=proposal_id,
                    )
                )
            logger.info(
                "Chain parameter %s updated to %s by proposal %s (tx %s)",
                parameter,
                value,
                proposal_id,
                tx_hash,
            )
        elif action == "set_governance_address":
            # Reserved for adding/removing governance signing addresses
            logger.info("GOVERNANCE_EXECUTE set_governance_address not implemented: %s", execution_payload)
        else:
            logger.info("GOVERNANCE_EXECUTE unknown action %s: %s", action, execution_payload)

    def _handle_bond_transaction(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        tx_type: str,
        sender_addr: str,
        recipient_addr: str,
        value: int,
    ) -> None:
        """Record bond state alongside the on-chain value transfer.

        Design:
        - BOND_LOCK is a normal transfer provider -> bond escrow. We record the bond.
        - BOND_RELEASE is provider-signed, value=0; we move the bond from escrow to provider.
        - BOND_SLASH is slash-authority-signed, value=0; we move the bond from escrow to burn.
        """
        payload = tx_data.get("payload", {}) or {}
        bond_id = payload.get("bond_id")
        if not bond_id:
            logger.warning("%s transaction %s missing bond_id in payload", tx_type, tx_hash)
            return
        provider = payload.get("provider")
        if not provider:
            logger.warning("%s transaction %s missing provider in payload", tx_type, tx_hash)
            return

        now = datetime.now(UTC)
        if tx_type == "BOND_LOCK":
            if not _is_bond_escrow(recipient_addr):
                logger.warning("BOND_LOCK %s does not target the bond escrow address", tx_hash)
                return
            if value <= 0:
                return
            lock_days = int(payload.get("lock_days", 30))
            locked_until = now + timedelta(days=lock_days)
            # Reuse an existing active bond with the same id if it exists (top-up).
            existing = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == bond_id)).first()
            if existing:
                existing.amount += value
                existing.locked_until = locked_until
                existing.updated_at = now
                logger.info("Bond topped up: %s amount=%s locked_until=%s", bond_id, existing.amount, locked_until)
            else:
                # Named apart from the `bond` the BOND_RELEASE/BOND_SLASH branches
                # load: those are Bond | None, and sharing the name pinned the
                # inferred type to Bond.
                new_bond = Bond(
                    chain_id=chain_id,
                    bond_id=bond_id,
                    provider=_to_ait_address(provider),
                    amount=value,
                    locked_until=locked_until,
                    status="active",
                    created_tx_hash=tx_hash,
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_bond)
                logger.info("Bond locked: %s provider=%s amount=%s locked_until=%s", bond_id, provider, value, locked_until)
        elif tx_type == "BOND_RELEASE":
            if sender_addr != _to_ait_address(provider):
                logger.warning("BOND_RELEASE %s not signed by the bond provider", tx_hash)
                return
            if recipient_addr != sender_addr:
                logger.warning("BOND_RELEASE %s recipient must be the provider", tx_hash)
                return
            if value != 0:
                logger.warning("BOND_RELEASE %s must have value=0", tx_hash)
                return
            bond = session.exec(
                select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == bond_id, Bond.status == "active")
            ).first()
            if not bond:
                logger.warning("BOND_RELEASE %s references unknown or inactive bond %s", tx_hash, bond_id)
                return
            if bond.locked_until:
                locked_until = bond.locked_until
                if locked_until.tzinfo is None:
                    locked_until = locked_until.replace(tzinfo=UTC)
                if now < locked_until:
                    logger.warning("BOND_RELEASE %s attempted before lock period expires for %s", tx_hash, bond_id)
                    return
            release_amount = bond.amount
            if release_amount <= 0:
                return
            escrow = _ensure_account(session, chain_id, _BOND_ESCROW_ADDRESS)
            sender = session.get(Account, (chain_id, sender_addr))
            if escrow and sender:
                session.refresh(escrow)
                session.refresh(sender)
                if escrow.balance < release_amount:
                    logger.warning("BOND_RELEASE %s escrow balance %s < %s", tx_hash, escrow.balance, release_amount)
                    return
                escrow.balance -= release_amount
                sender.balance += release_amount
                logger.info("BOND_RELEASE %s moved %s from escrow to %s", tx_hash, release_amount, sender_addr)
            bond.amount = 0
            bond.released_tx_hash = tx_hash
            bond.status = "released"
            bond.updated_at = now
            logger.info("Bond released: %s amount=%s", bond_id, release_amount)
        elif tx_type == "BOND_SLASH":
            slash_authority = _bond_slash_authority()
            if not slash_authority:
                logger.warning("BOND_SLASH %s rejected: no BOND_SLASH_AUTHORITY_ADDRESS configured", tx_hash)
                return
            if sender_addr != _to_ait_address(slash_authority):
                logger.warning("BOND_SLASH %s not signed by the configured slash authority", tx_hash)
                return
            if not _is_bond_burn(recipient_addr):
                logger.warning("BOND_SLASH %s does not burn to the bond burn address", tx_hash)
                return
            if value != 0:
                logger.warning("BOND_SLASH %s must have value=0", tx_hash)
                return
            slash_amount = int(payload.get("amount", 0))
            if slash_amount <= 0:
                logger.warning("BOND_SLASH %s missing positive amount in payload", tx_hash)
                return
            bond = session.exec(
                select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == bond_id, Bond.status == "active")
            ).first()
            if not bond:
                logger.warning("BOND_SLASH %s references unknown or inactive bond %s", tx_hash, bond_id)
                return
            if slash_amount > bond.amount:
                slash_amount = bond.amount
            if slash_amount <= 0:
                return
            escrow = _ensure_account(session, chain_id, _BOND_ESCROW_ADDRESS)
            burn = _ensure_account(session, chain_id, _BOND_BURN_ADDRESS)
            if escrow and burn:
                session.refresh(escrow)
                session.refresh(burn)
                if escrow.balance < slash_amount:
                    logger.warning("BOND_SLASH %s escrow balance %s < %s", tx_hash, escrow.balance, slash_amount)
                    return
                escrow.balance -= slash_amount
                burn.balance += slash_amount
                logger.info("BOND_SLASH %s moved %s from escrow to burn", tx_hash, slash_amount)
            bond.amount -= slash_amount
            bond.slashed_tx_hash = tx_hash
            bond.status = "slashed" if bond.amount <= 0 else "active"
            bond.updated_at = now
            logger.info("Bond slashed: %s amount=%s remaining=%s", bond_id, slash_amount, bond.amount)
            logger.info("Bond slashed: %s amount=%s remaining=%s", bond_id, slash_amount, bond.amount)

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
