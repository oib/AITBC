"""Payment escrow utility for blockchain-based task payments (v0.6.5 §A1).

Provides a blockchain-agnostic, in-memory escrow manager that tracks
``EscrowEntry`` records through a PENDING → LOCKED → RELEASED/REFUNDED
lifecycle. The actual on-chain transaction submission is delegated to
caller-supplied callbacks (Agent B wires these to the blockchain RPC
client in ``apps/agent-coordinator``).

The module is intentionally side-effect free with respect to the
blockchain: if no callback is supplied for a given action, the escrow
state still advances and the corresponding ``tx_hash_*`` field is left
as ``None``. This makes the utility trivially unit-testable without a
running node.

Durable bookkeeping is likewise opt-in: pass an ``EscrowStore`` to
``PaymentEscrow`` and every mutation is written through to the store
while previously persisted entries are reloaded at construction time
(so a service restart does not strand on-chain locks). Without a store
the manager stays purely in-memory.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class EscrowStatus(StrEnum):
    """Status of a payment escrow."""

    PENDING = "pending"  # Escrow created, not yet locked on-chain
    LOCKED = "locked"  # Funds locked on blockchain
    RELEASED = "released"  # Funds released to agent (task completed)
    REFUNDED = "refunded"  # Funds refunded to requester (task failed/timeout)
    EXPIRED = "expired"  # Escrow expired without completion


@dataclass
class EscrowEntry:
    """A single payment escrow entry."""

    escrow_id: str
    task_id: str
    chain_id: str
    requester: str  # Address paying for the task
    agent: str  # Address receiving payment
    amount: int  # Payment amount (in smallest units)
    fee: int = 0  # Transaction fee
    status: EscrowStatus = EscrowStatus.PENDING
    created_at: float = field(default_factory=time.time)
    locked_at: float | None = None
    released_at: float | None = None
    expires_at: float | None = None  # Timeout timestamp
    tx_hash_lock: str | None = None  # Blockchain tx hash for lock
    tx_hash_release: str | None = None  # Blockchain tx hash for release
    tx_hash_refund: str | None = None  # Blockchain tx hash for refund
    contract_id: str | None = None  # On-chain escrow contract id (when locked via /rpc/escrow/create)
    metadata: dict[str, Any] = field(default_factory=dict)


# Callback signature: (chain_id, from_addr, to_addr, amount) -> tx_hash
EscrowCallback = Callable[[str, str, str, int], str]


class EscrowStore(Protocol):
    """Durable backend for escrow bookkeeping entries.

    Implementations are synchronous and keyed by ``EscrowEntry.escrow_id``;
    ``save`` is an upsert. The agent-coordinator ships a SQLite
    implementation (``agent_app.storage.escrow_store.TaskEscrowStore``).
    """

    def save(self, entry: EscrowEntry) -> None:
        """Insert or update the durable record for ``entry``."""
        ...

    def load_all(self) -> list[EscrowEntry]:
        """Return every persisted entry, used to rehydrate on startup."""
        ...


class PaymentEscrow:
    """Manages payment escrows for task execution.

    Provides in-memory tracking of escrow entries with hooks for
    blockchain transaction submission (lock/release/refund).

    The actual blockchain transaction submission is delegated to a
    callback function provided by the caller (Agent B wires this to
    the blockchain RPC client).

    When a ``store`` is supplied the in-memory dict acts as a write-through
    cache: entries persisted by a previous process are loaded here and every
    state transition is saved back, so bookkeeping survives restarts.
    """

    def __init__(
        self,
        lock_callback: EscrowCallback | None = None,
        release_callback: EscrowCallback | None = None,
        refund_callback: EscrowCallback | None = None,
        default_timeout: float = 3600.0,
        store: EscrowStore | None = None,
    ) -> None:
        """Initialize the payment escrow manager.

        Args:
            lock_callback: Called to lock funds on-chain.
                Args: (chain_id, from_addr, to_addr, amount). Returns tx_hash.
            release_callback: Called to release funds to agent.
                Args: (chain_id, from_addr, to_addr, amount). Returns tx_hash.
            refund_callback: Called to refund funds to requester.
                Args: (chain_id, from_addr, to_addr, amount). Returns tx_hash.
            default_timeout: Default escrow timeout in seconds (default 3600).
            store: Optional durable backend; entries are reloaded from it at
                construction and every mutation is written through to it.
        """
        self._escrows: dict[str, EscrowEntry] = {}
        self._lock_callback = lock_callback
        self._release_callback = release_callback
        self._refund_callback = refund_callback
        self._default_timeout = default_timeout
        self._store = store
        if store is not None:
            try:
                for persisted in store.load_all():
                    self._escrows[persisted.escrow_id] = persisted
            except Exception as e:
                # Degrade to an empty view rather than refuse to start; the
                # error is loud in the logs and on-chain state is unaffected.
                logger.error("Failed to load persisted escrows: %s", e)
            else:
                if self._escrows:
                    logger.info("Reloaded %d persisted escrow(s)", len(self._escrows))

    def create_escrow(
        self,
        task_id: str,
        chain_id: str,
        requester: str,
        agent: str,
        amount: int,
        fee: int = 0,
        timeout: float | None = None,
    ) -> EscrowEntry:
        """Create a new payment escrow entry.

        Returns the created EscrowEntry. Does NOT lock funds yet —
        call lock() to submit the lock transaction.
        """
        if amount <= 0:
            raise ValueError(f"Escrow amount must be positive, got {amount}")
        escrow_id = str(uuid.uuid4())
        expires_at = time.time() + (timeout if timeout is not None else self._default_timeout)
        entry = EscrowEntry(
            escrow_id=escrow_id,
            task_id=task_id,
            chain_id=chain_id,
            requester=requester,
            agent=agent,
            amount=amount,
            fee=fee,
            expires_at=expires_at,
        )
        self._escrows[escrow_id] = entry
        self._persist(entry)
        logger.info(
            "Created escrow %s for task %s (amount=%d, chain=%s)",
            escrow_id,
            task_id,
            amount,
            chain_id,
        )
        return entry

    def lock(self, escrow_id: str, submitter: EscrowCallback | None = None) -> EscrowEntry:
        """Lock funds on-chain for an escrow.

        Calls the lock_callback (or the per-call ``submitter`` override when
        given) to submit a blockchain transaction.
        Raises ValueError if escrow not found or not in PENDING status.
        """
        entry = self._get_entry(escrow_id)
        if entry.status != EscrowStatus.PENDING:
            raise ValueError(f"Escrow {escrow_id} is not pending (status={entry.status})")
        callback = submitter or self._lock_callback
        if callback:
            entry.tx_hash_lock = callback(entry.chain_id, entry.requester, entry.agent, entry.amount)
        entry.status = EscrowStatus.LOCKED
        entry.locked_at = time.time()
        self._persist(entry)
        logger.info("Locked escrow %s (tx=%s)", escrow_id, entry.tx_hash_lock)
        return entry

    def release(self, escrow_id: str, submitter: EscrowCallback | None = None) -> EscrowEntry:
        """Release funds to agent on task completion.

        Calls the release_callback (or the per-call ``submitter`` override when
        given) to submit a blockchain transaction.
        Raises ValueError if escrow not found or not in LOCKED status.
        """
        entry = self._get_entry(escrow_id)
        if entry.status != EscrowStatus.LOCKED:
            raise ValueError(f"Escrow {escrow_id} is not locked (status={entry.status})")
        callback = submitter or self._release_callback
        if callback:
            entry.tx_hash_release = callback(
                entry.chain_id,
                entry.requester,
                entry.agent,
                entry.amount,
            )
        entry.status = EscrowStatus.RELEASED
        entry.released_at = time.time()
        self._persist(entry)
        logger.info("Released escrow %s (tx=%s)", escrow_id, entry.tx_hash_release)
        return entry

    def refund(self, escrow_id: str, submitter: EscrowCallback | None = None) -> EscrowEntry:
        """Refund funds to requester on task failure/timeout.

        Calls the refund_callback (or the per-call ``submitter`` override when
        given) to submit a blockchain transaction.
        Raises ValueError if escrow not found or not in LOCKED status.
        """
        entry = self._get_entry(escrow_id)
        if entry.status != EscrowStatus.LOCKED:
            raise ValueError(f"Escrow {escrow_id} is not locked (status={entry.status})")
        callback = submitter or self._refund_callback
        if callback:
            entry.tx_hash_refund = callback(
                entry.chain_id,
                entry.agent,
                entry.requester,
                entry.amount,
            )
        entry.status = EscrowStatus.REFUNDED
        self._persist(entry)
        logger.info("Refunded escrow %s (tx=%s)", escrow_id, entry.tx_hash_refund)
        return entry

    def expire_stale(
        self,
        refund_submitter_for: Callable[[EscrowEntry], EscrowCallback | None] | None = None,
    ) -> list[EscrowEntry]:
        """Expire and refund all escrows that have passed their timeout.

        ``refund_submitter_for`` optionally supplies a per-entry refund
        callback so on-chain escrows are refunded through the caller's
        transaction path while bookkeeping-only escrows stay off-chain.

        Returns list of expired/refunded entries.
        """
        now = time.time()
        expired: list[EscrowEntry] = []
        for entry in self._escrows.values():
            if entry.status == EscrowStatus.LOCKED and entry.expires_at and now > entry.expires_at:
                try:
                    submitter = refund_submitter_for(entry) if refund_submitter_for else None
                    self.refund(entry.escrow_id, submitter=submitter)
                    expired.append(entry)
                except Exception as e:
                    # Keep the entry LOCKED so the next sweep retries the
                    # refund; a transient RPC failure must not strand funds.
                    logger.error("Failed to refund expired escrow %s: %s", entry.escrow_id, e)
        return expired

    def get_escrow(self, escrow_id: str) -> EscrowEntry | None:
        """Get an escrow entry by ID."""
        return self._escrows.get(escrow_id)

    def get_escrow_for_task(self, task_id: str) -> EscrowEntry | None:
        """Get the escrow entry for a task."""
        for entry in self._escrows.values():
            if entry.task_id == task_id:
                return entry
        return None

    def get_all_escrows(self) -> list[EscrowEntry]:
        """Return all escrow entries."""
        return list(self._escrows.values())

    def get_escrows_by_status(self, status: EscrowStatus) -> list[EscrowEntry]:
        """Return all escrows with a given status."""
        return [e for e in self._escrows.values() if e.status == status]

    def persist_entry(self, entry: EscrowEntry) -> None:
        """Flush a caller-mutated entry (e.g. metadata/contract_id) to the store."""
        self._escrows[entry.escrow_id] = entry
        self._persist(entry)

    def _persist(self, entry: EscrowEntry) -> None:
        """Write ``entry`` through to the configured store (best effort).

        A store failure is logged but never raised: the chain operation the
        entry records has already happened, so failing the call would only
        mislead the caller into retrying a settled transaction.
        """
        if self._store is None:
            return
        try:
            self._store.save(entry)
        except Exception as e:
            logger.error("Failed to persist escrow %s: %s", entry.escrow_id, e)

    def _get_entry(self, escrow_id: str) -> EscrowEntry:
        """Get an escrow entry or raise ValueError."""
        entry = self._escrows.get(escrow_id)
        if entry is None:
            raise ValueError(f"Escrow {escrow_id} not found")
        return entry
