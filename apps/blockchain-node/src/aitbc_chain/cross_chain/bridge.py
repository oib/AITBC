"""
Cross-Chain Bridge - Real cross-island transaction bridging

This module implements atomic cross-chain transfers using a
lock-mint/burn-release pattern for secure value transfer
between islands (blockchain shards).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlmodel import select

from ..logger import get_logger
from ..models import Account, CrossChainTransfer, Transaction

logger = get_logger(__name__)


class BridgeStatus(Enum):
    """Status of a cross-chain transfer"""
    pending = "pending"
    locked = "locked"
    confirmed = "confirmed"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"


@dataclass
class BridgeTransfer:
    """Cross-chain transfer record"""
    transfer_id: str
    source_chain: str
    target_chain: str
    sender: str
    recipient: str
    amount: int
    asset: str
    status: BridgeStatus
    source_tx_hash: str | None
    target_tx_hash: str | None
    lock_time: datetime | None
    confirm_time: datetime | None
    proof: dict[str, Any] | None


class CrossChainBridge:
    """
    Cross-Chain Bridge for atomic transfers between islands.
    
    Implements the lock-mint/burn-release pattern:
    1. Lock funds on source chain
    2. Generate proof of lock
    3. Mint/burn equivalent on target chain
    4. Release funds on target
    """

    # Bridge fee (0.1%)
    BRIDGE_FEE_BASIS_POINTS = 10

    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._pending_transfers: dict[str, BridgeTransfer] = {}
        self._processed_proofs: set[str] = set()

    def initiate_transfer(
        self,
        source_chain: str,
        target_chain: str,
        sender: str,
        recipient: str,
        amount: int,
        asset: str = "native"
    ) -> BridgeTransfer:
        """
        Initiate a cross-chain transfer.
        
        Step 1: Lock funds on source chain
        """
        transfer_id = self._generate_transfer_id(
            source_chain, target_chain, sender, recipient, amount, int(time.time())
        )

        with self._session_factory() as session:
            # Verify sender has sufficient balance
            sender_account = session.get(Account, (source_chain, sender))
            if not sender_account:
                raise ValueError(f"Sender account not found: {sender}")

            # Calculate fee
            fee = (amount * self.BRIDGE_FEE_BASIS_POINTS) // 10000
            total_deduction = amount + fee

            if sender_account.balance < total_deduction:
                raise ValueError(
                    f"Insufficient balance: {sender_account.balance} < {total_deduction}"
                )

            # Lock funds (deduct from sender)
            sender_account.balance -= total_deduction
            session.add(sender_account)

            # Create lock transaction
            lock_tx = Transaction(
                chain_id=source_chain,
                tx_hash=transfer_id,
                sender=sender,
                recipient="bridge_lock",  # Special bridge address
                payload={
                    "type": "BRIDGE_LOCK",
                    "transfer_id": transfer_id,
                    "target_chain": target_chain,
                    "target_recipient": recipient,
                    "amount": amount,
                    "fee": fee,
                    "asset": asset
                },
                value=amount,
                fee=fee,
                nonce=sender_account.nonce,
                timestamp=datetime.now(UTC),
                block_height=None,  # Will be set when mined
                status="pending",
                type="BRIDGE_LOCK"
            )
            session.add(lock_tx)

            # Create cross-chain transfer record
            transfer_record = CrossChainTransfer(
                transfer_id=transfer_id,
                source_chain=source_chain,
                target_chain=target_chain,
                sender=sender,
                recipient=recipient,
                amount=amount,
                asset=asset,
                status="pending",
                source_tx_hash=transfer_id,
                lock_time=datetime.now(UTC)
            )
            session.add(transfer_record)
            session.commit()

            # Build transfer object
            transfer = BridgeTransfer(
                transfer_id=transfer_id,
                source_chain=source_chain,
                target_chain=target_chain,
                sender=sender,
                recipient=recipient,
                amount=amount,
                asset=asset,
                status=BridgeStatus.locked,
                source_tx_hash=transfer_id,
                target_tx_hash=None,
                lock_time=datetime.now(UTC),
                confirm_time=None,
                proof=None
            )

            self._pending_transfers[transfer_id] = transfer

            logger.info(
                f"Bridge transfer initiated: {transfer_id[:16]}... "
                f"{amount} from {source_chain} to {target_chain}"
            )

            return transfer

    def confirm_transfer(
        self,
        transfer_id: str,
        proof: dict[str, Any]
    ) -> BridgeTransfer:
        """
        Confirm a cross-chain transfer on target chain.
        
        Step 2: Validate proof and release funds on target chain
        """
        # Verify proof hasn't been used before (prevent double-spend)
        proof_hash = hashlib.sha256(
            json.dumps(proof, sort_keys=True).encode()
        ).hexdigest()

        if proof_hash in self._processed_proofs:
            raise ValueError("Proof already processed (double-spend attempt)")

        with self._session_factory() as session:
            # Get transfer record
            record = session.get(CrossChainTransfer, transfer_id)
            if not record:
                raise ValueError(f"Transfer not found: {transfer_id}")

            if record.status != "pending":
                raise ValueError(f"Transfer already processed: {record.status}")

            # Validate proof
            if not self._validate_proof(proof, record):
                raise ValueError("Invalid transfer proof")

            # Get or create recipient account on target chain
            recipient_account = session.get(Account, (record.target_chain, record.recipient))
            if not recipient_account:
                recipient_account = Account(
                    chain_id=record.target_chain,
                    address=record.recipient,
                    balance=0,
                    nonce=0
                )
                session.add(recipient_account)

            # Release funds (mint on target chain)
            recipient_account.balance += record.amount
            session.add(recipient_account)

            # Generate target chain transaction hash
            target_tx_hash = hashlib.sha256(
                f"{transfer_id}:{record.target_chain}:{int(time.time())}".encode()
            ).hexdigest()

            # Create release transaction
            release_tx = Transaction(
                chain_id=record.target_chain,
                tx_hash=target_tx_hash,
                sender="bridge_release",  # Special bridge address
                recipient=record.recipient,
                payload={
                    "type": "BRIDGE_RELEASE",
                    "transfer_id": transfer_id,
                    "source_chain": record.source_chain,
                    "source_sender": record.sender,
                    "amount": record.amount,
                    "asset": record.asset,
                    "proof": proof_hash
                },
                value=record.amount,
                fee=0,
                nonce=0,
                timestamp=datetime.now(UTC),
                block_height=None,
                status="confirmed",
                type="BRIDGE_RELEASE"
            )
            session.add(release_tx)

            # Update transfer record
            record.status = "completed"
            record.target_tx_hash = target_tx_hash
            record.confirm_time = datetime.now(UTC)
            session.add(record)
            session.commit()

            # Mark proof as processed
            self._processed_proofs.add(proof_hash)

            # Update transfer object
            transfer = self._pending_transfers.get(transfer_id)
            if transfer:
                transfer.status = BridgeStatus.completed
                transfer.target_tx_hash = target_tx_hash
                transfer.confirm_time = datetime.now(UTC)
                transfer.proof = proof

            logger.info(
                f"Bridge transfer completed: {transfer_id[:16]}... "
                f"released {record.amount} to {record.recipient[:20]}..."
            )

            return transfer or self._build_transfer_from_record(record, proof)

    def get_transfer(self, transfer_id: str) -> BridgeTransfer | None:
        """Get transfer by ID"""
        # Check cache first
        if transfer_id in self._pending_transfers:
            return self._pending_transfers[transfer_id]

        # Query database
        with self._session_factory() as session:
            record = session.get(CrossChainTransfer, transfer_id)
            if record:
                return self._build_transfer_from_record(record)
            return None

    def list_pending_transfers(self, chain_id: str | None = None) -> list[BridgeTransfer]:
        """List all pending transfers"""
        with self._session_factory() as session:
            query = select(CrossChainTransfer).where(CrossChainTransfer.status == "pending")
            if chain_id:
                query = query.where(
                    (CrossChainTransfer.source_chain == chain_id) |
                    (CrossChainTransfer.target_chain == chain_id)
                )

            records = session.exec(query).all()
            return [self._build_transfer_from_record(r) for r in records]

    def _generate_transfer_id(
        self,
        source_chain: str,
        target_chain: str,
        sender: str,
        recipient: str,
        amount: int,
        timestamp: int
    ) -> str:
        """Generate unique transfer ID"""
        data = f"{source_chain}:{target_chain}:{sender}:{recipient}:{amount}:{timestamp}"
        return "0x" + hashlib.sha256(data.encode()).hexdigest()

    def _validate_proof(
        self,
        proof: dict[str, Any],
        record: CrossChainTransfer
    ) -> bool:
        """Validate cross-chain transfer proof"""
        # Basic validation - in production, this would verify:
        # - Merkle proofs
        # - Signatures from validators
        # - Block confirmations

        required_fields = ["source_chain", "lock_tx_hash", "amount", "sender", "recipient"]
        for field in required_fields:
            if field not in proof:
                logger.warning(f"Proof missing field: {field}")
                return False

        # Verify proof matches transfer record
        if proof.get("source_chain") != record.source_chain:
            return False
        if proof.get("amount") != record.amount:
            return False
        if proof.get("recipient") != record.recipient:
            return False

        return True

    def _build_transfer_from_record(
        self,
        record: CrossChainTransfer,
        proof: dict | None = None
    ) -> BridgeTransfer:
        """Build BridgeTransfer from database record"""
        return BridgeTransfer(
            transfer_id=record.transfer_id,
            source_chain=record.source_chain,
            target_chain=record.target_chain,
            sender=record.sender,
            recipient=record.recipient,
            amount=record.amount,
            asset=record.asset,
            status=BridgeStatus(record.status),
            source_tx_hash=record.source_tx_hash,
            target_tx_hash=record.target_tx_hash,
            lock_time=record.lock_time,
            confirm_time=record.confirm_time,
            proof=proof
        )


# Global bridge instance
_bridge_instance: CrossChainBridge | None = None


def init_cross_chain_bridge(session_factory) -> CrossChainBridge:
    """Initialize the global cross-chain bridge"""
    global _bridge_instance
    _bridge_instance = CrossChainBridge(session_factory)
    return _bridge_instance


def get_cross_chain_bridge() -> CrossChainBridge | None:
    """Get the global bridge instance"""
    return _bridge_instance
