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
import math
import threading
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
    REJECTED = "rejected"  # Lock tx was apply-rejected on-chain; nothing ever moved (#2744)


# #2866: upper bound for an escrow timeout — 30 days, the same horizon the
# market job TTL uses. An unbounded/NaN/negative timeout either refunds the
# moment it locks or is never swept.
_MAX_TIMEOUT_SECONDS = 2_592_000.0

# #3027: metadata key tombstoning "work was distributed for this task".
# The agent-coordinator stamps it when a load-balancer assignment is created
# (and the orphan sweeper re-stamps it on first observation); the orphan
# sweeper's distributed-check must survive the balancer's bounded
# ``task_assignments`` map, which evicts terminal records — the escrow row's
# own durable metadata is the signal that outlives that eviction.
META_WAS_DISTRIBUTED_AT = "was_distributed_at"


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


def _normalize_tx_hash(value: Any) -> str | None:
    """Normalize a recorded/provided tx hash for CAS comparison (#3035)."""
    return str(value) if value else None


def _recorded_settle_tx(entry: EscrowEntry) -> str | None:
    """The settle tx hash ``entry``'s *current* status recorded, normalized.

    This is the settlement-attempt identity the terminal-settle sweeper
    probes (#3026): RELEASED rows settle via ``tx_hash_release``, REFUNDED
    via ``tx_hash_refund``; any other status records no settle attempt.
    """
    if entry.status == EscrowStatus.RELEASED:
        return _normalize_tx_hash(entry.tx_hash_release)
    if entry.status == EscrowStatus.REFUNDED:
        return _normalize_tx_hash(entry.tx_hash_refund)
    return None


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
        """Return persisted entries, used to rehydrate on startup.

        Implementations may restrict this to non-terminal entries; point
        lookups for terminal rows go through the optional ``load`` /
        ``load_by_task`` hooks below.
        """
        ...

    def load(self, escrow_id: str) -> EscrowEntry | None:
        """Optional point lookup by escrow id (terminal rows included)."""
        ...

    def load_by_task(self, task_id: str) -> EscrowEntry | None:
        """Optional point lookup by task id (terminal rows included)."""
        ...

    def load_terminal(self, statuses: tuple[str, ...], *, limit: int = 500) -> list[EscrowEntry]:
        """Optional listing of terminal entries by ``EscrowStatus`` name.

        ``load_all`` deliberately rehydrates only active rows (#1515), so a
        terminal entry written by a previous process is invisible to
        ``get_all_escrows``. Implementations should exclude rows the caller
        has already resolved (e.g. via a metadata marker) so resolved
        history cannot crowd the batch.
        """
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
        # #1750: the agent-coordinator runs escrow transitions via
        # ``asyncio.to_thread`` (the chain submitters are synchronous httpx),
        # so the in-memory dict + store write-through must be safe against
        # concurrent endpoint/sweeper threads. RLock: expire_stale re-enters
        # refund() while holding it.
        self._lock = threading.RLock()
        self._lock_callback = lock_callback
        self._release_callback = release_callback
        self._refund_callback = refund_callback
        self._default_timeout = default_timeout
        self._store = store
        if store is not None:
            try:
                for persisted in store.load_all():
                    self._escrows[persisted.escrow_id] = persisted
            except Exception as e:  # noqa: BLE001 - fail-safe: any store.load_all failure degrades to empty view
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
        # #2866: the timeout lands directly in expires_at — a NaN/inf timeout
        # produces an un-sweepable row, a negative one refunds instantly, a
        # huge one strands funds effectively forever. Bound it here too: the
        # API layer validates, but this is the library's own money invariant.
        # Validate the effective timeout so a bad default_timeout can't slip
        # through the timeout=None path either.
        effective_timeout = timeout if timeout is not None else self._default_timeout
        if not math.isfinite(effective_timeout) or effective_timeout <= 0 or effective_timeout > _MAX_TIMEOUT_SECONDS:
            raise ValueError(
                f"Escrow timeout must be a finite value in (0, {_MAX_TIMEOUT_SECONDS}] seconds, got {effective_timeout!r}"
            )
        with self._lock:
            escrow_id = str(uuid.uuid4())
            expires_at = time.time() + effective_timeout
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
            # #3026: stamp the refund time — there is no ``refunded_at``
            # column, and the terminal-settle sweep needs the settle
            # timestamp to apply its grace horizon.
            entry.metadata["refunded_at"] = time.time()
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
        with self._lock:
            for entry in list(self._escrows.values()):
                if entry.status == EscrowStatus.LOCKED and entry.expires_at and now > entry.expires_at:
                    try:
                        submitter = refund_submitter_for(entry) if refund_submitter_for else None
                        self.refund(entry.escrow_id, submitter=submitter)
                        expired.append(entry)
                    except Exception as e:  # noqa: BLE001 - per-entry containment: any refund failure keeps entry LOCKED for the next sweep
                        # Keep the entry LOCKED so the next sweep retries the
                        # refund; a transient RPC failure must not strand funds.
                        logger.error("Failed to refund expired escrow %s: %s", entry.escrow_id, e)
        return expired

    def get_escrow(self, escrow_id: str) -> EscrowEntry | None:
        """Get an escrow entry by ID.

        ``load_all`` only rehydrates active (PENDING/LOCKED) rows, so a
        terminal escrow misses the in-memory dict after a restart — fall back
        to the store's point lookup and cache the hit (#1515).
        """
        with self._lock:
            entry = self._escrows.get(escrow_id)
            if entry is None and self._store is not None:
                load = getattr(self._store, "load", None)
                if load is not None:
                    try:
                        entry = load(escrow_id)
                    except Exception as e:  # noqa: BLE001 - fail-safe: store point-lookup failure reads as absent
                        logger.error("Failed to load escrow %s from store: %s", escrow_id, e)
                        entry = None
                    if entry is not None:
                        self._escrows[entry.escrow_id] = entry
            return entry

    def get_escrow_for_task(self, task_id: str) -> EscrowEntry | None:
        """Get the escrow entry for a task.

        ``task_id`` is caller-chosen, so a task can accumulate several rows
        over time (a terminal escrow followed by a resubmission). Prefer the
        newest *active* (PENDING/LOCKED) entry — otherwise the first-inserted
        terminal row shadows the live escrow and complete/fail/status keep
        operating on a dead record while the active one becomes unreachable.
        When nothing is active, return the newest entry overall.
        """
        with self._lock:
            matches = [entry for entry in self._escrows.values() if entry.task_id == task_id]
            if matches:
                active = [e for e in matches if e.status in (EscrowStatus.PENDING, EscrowStatus.LOCKED)]
                return max(active or matches, key=lambda e: e.created_at)
            if self._store is not None:
                load_by_task = getattr(self._store, "load_by_task", None)
                if load_by_task is not None:
                    persisted: EscrowEntry | None
                    try:
                        persisted = load_by_task(task_id)
                    except Exception as e:  # noqa: BLE001 - fail-safe: store point-lookup failure reads as absent
                        logger.error("Failed to load escrow for task %s from store: %s", task_id, e)
                        persisted = None
                    if persisted is not None:
                        self._escrows[persisted.escrow_id] = persisted
                        return persisted
            return None

    def mark_distributed(self, task_id: str) -> int:
        """Stamp every cached entry for ``task_id`` as distributed (#3027).

        Called when the load balancer creates an assignment for the task:
        every escrow row carrying that ``task_id`` — including terminal
        predecessors a same-task resubmission left behind — records that
        work was handed out, so the orphan sweeper's distributed-check no
        longer depends solely on the evictable assignment map. Idempotent
        per entry; ``_persist`` is best-effort so a store failure never
        raises. Returns the number of newly stamped entries.
        """
        stamped = 0
        with self._lock:
            for entry in self._escrows.values():
                if entry.task_id != task_id or entry.metadata.get(META_WAS_DISTRIBUTED_AT):
                    continue
                entry.metadata[META_WAS_DISTRIBUTED_AT] = time.time()
                self._persist(entry)
                stamped += 1
        return stamped

    def get_all_escrows(self) -> list[EscrowEntry]:
        """Return all escrow entries."""
        with self._lock:
            return list(self._escrows.values())

    def get_escrows_by_status(self, status: EscrowStatus) -> list[EscrowEntry]:
        """Return all escrows with a given status."""
        with self._lock:
            return [e for e in self._escrows.values() if e.status == status]

    def persist_entry(self, entry: EscrowEntry, *, strict: bool = False) -> None:
        """Flush a caller-mutated entry (e.g. metadata/contract_id) to the store.

        ``strict=True`` re-raises store failures instead of logging them —
        the task-submit path uses it so the durable row is proven before the
        on-chain lock is attempted (#2998): a swallowed write failure there
        is exactly how a funded escrow ends up with no payment row.
        """
        with self._lock:
            self._escrows[entry.escrow_id] = entry
            self._persist(entry, strict=strict)

    def adopt_chain_lock(
        self,
        entry: EscrowEntry,
        *,
        tx_hash_lock: str | None = None,
        contract_id: str | None = None,
    ) -> bool:
        """Flip a PENDING/REJECTED entry to LOCKED from chain truth (#2998).

        The node's escrow record is authoritative: a lock that sealed after
        an ambiguous submit — or after a bookkeeping-only persist — leaves
        the local row below LOCKED while funds are actually held. Adopting
        records the chain's lock hash/contract id so the normal
        release/refund/expire paths can settle it. Returns ``False`` when
        the stored entry is missing or no longer in an adoptable state (a
        concurrent transition wins; the caller must not mutate blindly).
        """
        with self._lock:
            current = self._escrows.get(entry.escrow_id)
            if current is None or current.status not in (EscrowStatus.PENDING, EscrowStatus.REJECTED):
                return False
            current.status = EscrowStatus.LOCKED
            current.locked_at = time.time()
            if tx_hash_lock:
                current.tx_hash_lock = str(tx_hash_lock)
            if contract_id:
                current.contract_id = str(contract_id)
                current.metadata["contract_id"] = str(contract_id)
            current.metadata["orphan_adopted_at"] = time.time()
            self._persist(current)
            logger.info("Adopted on-chain lock for escrow %s (task %s)", current.escrow_id, current.task_id)
            return True

    def refund_orphaned(
        self,
        entry: EscrowEntry,
        submitter: EscrowCallback | None = None,
        *,
        tx_hash_lock: str | None = None,
        contract_id: str | None = None,
    ) -> EscrowEntry:
        """Refund a PENDING/REJECTED escrow whose on-chain lock is live (#2998).

        Same callback signature and argument order as :meth:`refund`. The
        status check runs under the manager lock, so a concurrent
        transition (a same-task resubmit locking the entry, a settle path
        moving it) wins and this raises ``ValueError`` instead of
        double-acting. The chain refund itself is idempotent per job id.

        ``tx_hash_lock``/``contract_id`` carry the chain point-read's
        verified lock identity (#3006): the orphan's original submit died
        before ``lock()`` could record it, so the sweeper supplies what the
        chain proved. It is backfilled and persisted *before* the refund
        submitter runs — if the refund tx is later apply-rejected,
        ``reconcile_rejected_refund`` restores LOCKED and the expire sweep
        needs ``tx_hash_lock`` to build a real chain submitter instead of
        reading the row as bookkeeping-only and marking it REFUNDED with
        no transaction.
        """
        with self._lock:
            current = self._escrows.get(entry.escrow_id)
            if current is None:
                raise ValueError(f"Escrow {entry.escrow_id} not found")
            if current.status not in (EscrowStatus.PENDING, EscrowStatus.REJECTED):
                raise ValueError(f"Escrow {entry.escrow_id} is not orphan-eligible (status={current.status})")
            if tx_hash_lock and not current.tx_hash_lock:
                current.tx_hash_lock = str(tx_hash_lock)
            if contract_id and not current.contract_id:
                current.contract_id = str(contract_id)
                current.metadata["contract_id"] = str(contract_id)
            if tx_hash_lock or contract_id:
                self._persist(current)
            callback = submitter or self._refund_callback
            if callback:
                current.tx_hash_refund = callback(
                    current.chain_id,
                    current.agent,
                    current.requester,
                    current.amount,
                )
            current.status = EscrowStatus.REFUNDED
            current.metadata["orphan_refund"] = True
            current.metadata["refunded_at"] = time.time()
            self._persist(current)
            logger.info("Refunded orphaned escrow %s (tx=%s)", current.escrow_id, current.tx_hash_refund)
            return current

    def get_terminal_escrows(
        self,
        statuses: tuple[EscrowStatus, ...] = (EscrowStatus.RELEASED, EscrowStatus.REFUNDED),
    ) -> list[EscrowEntry]:
        """Return terminal entries in ``statuses`` — hot cache plus store-only rows.

        ``load_all`` rehydrates only active rows (#1515), so a terminal
        entry written by a previous process never reaches ``_escrows``.
        Stores may implement the optional ``load_terminal`` hook; its rows
        are merged in as detached copies — the hot-cache entry always wins.
        Detached entries are read-only for callers: mutate them only through
        :meth:`persist_terminal`, :meth:`stamp_terminal`, or
        :meth:`demote_unsealed_settle`.
        """
        with self._lock:
            merged = {e.escrow_id: e for e in self._escrows.values() if e.status in statuses}
            load_terminal = getattr(self._store, "load_terminal", None) if self._store is not None else None
            if load_terminal is not None:
                try:
                    for entry in load_terminal(tuple(s.name for s in statuses)):
                        merged.setdefault(entry.escrow_id, entry)
                except Exception as e:  # noqa: BLE001 - fail-safe: store read failure degrades to the hot view
                    logger.error("Failed to load terminal escrows: %s", e)
            return list(merged.values())

    def persist_terminal(self, entry: EscrowEntry, *, strict: bool = False) -> None:
        """Persist a (possibly detached) terminal entry WITHOUT pinning it in the hot cache.

        The #1515 split keeps terminal rows out of ``_escrows``; a sweeper
        stamping probe markers on a store-only row must not re-inflate the
        cache with history. When the entry IS cached the cache slot is
        refreshed so later reads agree — pass the freshest copy.
        """
        with self._lock:
            if entry.escrow_id in self._escrows:
                self._escrows[entry.escrow_id] = entry
            self._persist(entry, strict=strict)

    def _current_entry(self, escrow_id: str) -> EscrowEntry | None:
        """Resolve the live entry for ``escrow_id``: hot cache, else store point lookup.

        Callers must hold ``self._lock``. A store read failure degrades to
        ``None`` — an unreadable row reads as absent, never as permission
        to write.
        """
        current = self._escrows.get(escrow_id)
        if current is None and self._store is not None:
            load = getattr(self._store, "load", None)
            if load is not None:
                try:
                    current = load(escrow_id)
                except Exception as e:  # noqa: BLE001 - fail-safe: unreadable store row reads as absent
                    logger.error("Failed to load escrow %s: %s", escrow_id, e)
                    current = None
        return current

    def stamp_terminal(
        self,
        entry: EscrowEntry,
        updates: dict[str, Any],
        *,
        expected_status: EscrowStatus,
        expected_settle_tx_hash: str | None,
    ) -> bool:
        """Conditionally stamp metadata on a terminal entry — CAS on attempt identity (#3035).

        Probe sweeps hold a *detached* copy of a terminal row while the
        chain probe runs; by stamp time the live row may have moved on (a
        rejected settle reconciled to LOCKED and re-driven with a
        replacement tx under the same terminal status). The stamp must
        apply only to the attempt it observed: the stored entry must still
        be in ``expected_status`` AND still record
        ``expected_settle_tx_hash`` as its settle attempt (``None`` = no
        settle hash recorded, the chain-record probe path). On a match
        only ``updates`` merge into the *current* entry's metadata — the
        caller's possibly-stale copy is never written back wholesale, so a
        stale ``settle_probe_confirmed_at`` cannot resolve a newer
        attempt forever. Returns ``False`` when the CAS loses; nothing is
        persisted and store-only rows stay out of the hot cache (#1515).
        """
        with self._lock:
            current = self._current_entry(entry.escrow_id)
            if current is None or current.status != expected_status:
                return False
            if _recorded_settle_tx(current) != _normalize_tx_hash(expected_settle_tx_hash):
                return False
            current.metadata.update(updates)
            self._persist(current)
            return True

    def demote_unsealed_settle(
        self,
        entry: EscrowEntry,
        *,
        expected_status: EscrowStatus,
        expected_settle_tx_hash: str | None,
        reason: str,
        evidence: dict[str, Any] | None = None,
        tx_hash_lock: str | None = None,
        contract_id: str | None = None,
    ) -> bool:
        """CAS-flip a terminal entry back to LOCKED when its settle tx never landed (#3026).

        ``release()``/``refund()`` record RELEASED/REFUNDED at mempool
        admission; a settle tx evicted before sealing (or apply-rejected —
        the #2926 reconcile's case) leaves the row terminal while the
        on-chain escrow stays locked, invisible to every worklist. The
        caller must have proven the settle hash dead or absent on-chain;
        this performs only the guarded transition: the stored entry must
        still be in ``expected_status`` AND still record
        ``expected_settle_tx_hash`` as its settle attempt — a concurrent
        transition wins and this returns ``False``.

        The attempt check (#3035) is what makes the verdict attempt-scoped:
        the reject/expiry worker can cycle a row LOCKED -> REFUNDED with a
        REPLACEMENT settle tx between the caller's chain probe and this
        demote, landing back on the same terminal status with a different
        ``tx_hash_*``. A status-only CAS would apply the stale "the settle
        never landed" verdict to the newer attempt — demoting a row whose
        fresh settle tx may still seal. ``expected_settle_tx_hash=None``
        is the chain-record probe path: it matches only a row that still
        records no settle hash at all.

        On success the row is LOCKED again (active bookkeeping, so it
        re-enters the hot cache and ``expire_stale``/settle paths re-drive
        it), ``released_at`` is cleared for a RELEASED demote (mirroring
        ``reconcile_rejected_release``), the dead ``tx_hash_*`` is kept for
        audit, and the demote reason/evidence land in ``metadata``.
        ``tx_hash_lock``/``contract_id`` optionally backfill the lock
        identity from a chain point-read (same contract as
        ``refund_orphaned``, #3006) for terminal rows that never recorded
        one — only filled when empty.
        """
        with self._lock:
            current = self._current_entry(entry.escrow_id)
            if current is None or current.status != expected_status:
                return False
            if _recorded_settle_tx(current) != _normalize_tx_hash(expected_settle_tx_hash):
                return False
            if tx_hash_lock and not current.tx_hash_lock:
                current.tx_hash_lock = str(tx_hash_lock)
            if contract_id and not current.contract_id:
                current.contract_id = str(contract_id)
                current.metadata["contract_id"] = str(contract_id)
            if current.status == EscrowStatus.RELEASED:
                current.released_at = None
            current.status = EscrowStatus.LOCKED
            current.metadata["settle_demoted_reason"] = reason
            current.metadata["settle_demote_evidence"] = dict(evidence or {})
            current.metadata["settle_demoted_at"] = time.time()
            self._persist(current)
            # LOCKED is active bookkeeping — it belongs in the hot cache so
            # the expire sweep and settle paths see it without a store read.
            self._escrows[current.escrow_id] = current
            logger.info(
                "Demoted escrow %s (task %s) %s -> LOCKED: %s",
                current.escrow_id,
                current.task_id,
                expected_status,
                reason,
            )
            return True

    def _persist(self, entry: EscrowEntry, *, strict: bool = False) -> None:
        """Write ``entry`` through to the configured store (best effort).

        A store failure is logged but never raised: the chain operation the
        entry records has already happened, so failing the call would only
        mislead the caller into retrying a settled transaction. ``strict``
        callers (the pre-lock submit path, #2998) opt out of that — for them
        the write IS the precondition, not a post-hoc record.
        """
        if self._store is None:
            return
        try:
            self._store.save(entry)
        except Exception as e:  # noqa: BLE001 - fail-safe: store write-through failure is logged, never raised
            if strict:
                raise
            logger.error("Failed to persist escrow %s: %s", entry.escrow_id, e)

    def _get_entry(self, escrow_id: str) -> EscrowEntry:
        """Get an escrow entry or raise ValueError."""
        entry = self._escrows.get(escrow_id)
        if entry is None:
            raise ValueError(f"Escrow {escrow_id} not found")
        return entry
