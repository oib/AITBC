"""Reconcile atask escrows whose on-chain lock outlived the local row (#2998).

``POST /v1/tasks/submit`` persists the escrow row PENDING *before* the
on-chain ``/rpc/escrow/create`` submit — but ``PaymentEscrow.lock`` only
flips the row to LOCKED after the chain answers. When the chain accepted
the ESCROW_LOCK and the answer was then lost (502 after submit, timeout,
exhausted 425 retries while the lock still sealed later), the row stays
PENDING with ``tx_hash_lock=None`` forever: ``expire_stale`` only refunds
LOCKED rows, the chain-side ``sw_job_*`` sweep does not cover ``atask_*``
ids, and the coordinator-api stranded-escrow sweeper only scans
``job_payments`` — never ``task_escrows``. The result is a funded on-chain
escrow invisible to every sweep until a manual RPC refund.

This pass is the agent-coordinator sibling of the coordinator-api
``StrandedEscrowRefundSweeper`` (#2996): the chain point-read
(``GET /rpc/escrow/{task_id}``) is the truth, the local row only selects
candidates. For each PENDING/REJECTED entry older than the grace period:

* chain record shows a live lock **and the task was distributed** (a
  load-balancer assignment exists) → *adopt*: flip the row to LOCKED with
  the chain's lock hash/contract id so the normal release/refund/expire
  paths settle it. This is the persist-failure heal — the task is live and
  refunding would steal a payable escrow.
* chain record shows a live lock **and no assignment exists** → the submit
  died before distribution, nobody can claim the escrow → *refund* it
  on-chain and mark the row REFUNDED. The chain refund is idempotent per
  job id and ``refund_orphaned`` re-checks the status under the manager
  lock, so concurrent workers/races cannot double-act.
* no record / settled record / record still mid-flight → skip and stamp
  ``metadata["orphan_probe_at"]`` so bookkeeping-only PENDING rows
  (payment without a lock payload — PENDING by design) rotate out of the
  candidate batch instead of starving it.

A genuinely row-less on-chain escrow cannot be enumerated — the chain RPC
exposes point reads only, no escrow list — so this sweeper covers every
case where a local row exists in a non-LOCKED state; the strict persist in
``_create_task_escrow`` prevents new row-less occurrences.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.payment_escrow import EscrowEntry, EscrowStatus

from .chain_escrow import ChainEscrowClient, EscrowRPCError, make_refund_submitter

logger = get_logger(__name__)

# Local states that can mask a live on-chain lock. PENDING is where an
# ambiguous submit leaves the row (``lock()`` flips only after the chain
# answers); REJECTED is terminal for the *recorded* lock tx, but a different
# sealed lock for the same job id can still hold funds.
_ORPHAN_ELIGIBLE_STATUSES = (EscrowStatus.PENDING, EscrowStatus.REJECTED)

# Same live-lock predicate the coordinator-api stranded pass uses (#2996):
# the record must be unsettled, carry no refund/release leg, have released
# nothing, and still read locked/funded. Anything settled or mid-work stays
# untouched — the chain refund endpoint's own state machine is the second
# gate, this list is the first.
_STRANDED_ESCROW_STATES = frozenset({"", "locked", "funded", "created", "job_started"})
_STRANDED_ESCROW_STATUSES = frozenset({"", "locked", "funded"})
_SETTLED_ESCROW_STATES = frozenset({"released", "refunded"})

# Metadata key stamping the last definitive chain probe, so skipped
# candidates re-probe on the grace cadence instead of every sweep.
META_ORPHAN_PROBE_AT = "orphan_probe_at"

ORPHAN_REFUND_REASON = "orphaned_lock_no_payment_row"

# The refund endpoint answers 425 while the lock is not yet sealed — same
# retryable deferral the submit path honours; the sweep just tries again.
_LOCK_NOT_CONFIRMED_STATUS = 425


def _record_is_settled(record: dict[str, Any]) -> bool:
    """True when the node's escrow record is already settled either way."""
    if record.get("released_at") or record.get("refunded_at"):
        return True
    state = str(record.get("state") or "").lower()
    status = str(record.get("status") or "").lower()
    return state in _SETTLED_ESCROW_STATES or status in _SETTLED_ESCROW_STATES


def _released_amount_is_zero(record: dict[str, Any]) -> bool:
    """True when the escrow record shows nothing was paid out to the provider."""
    raw = record.get("released_amount")
    if raw is None or raw == "":
        return True
    try:
        return Decimal(str(raw)) == 0
    except (InvalidOperation, ValueError):
        return False


def escrow_record_is_stranded(record: dict[str, Any] | None) -> bool:
    """True when the node's escrow record shows a live lock the local row never saw.

    A missing record (``None`` — the client's 404 mapping) is NOT stranded:
    nothing was ever locked. Mirrors ``_escrow_record_is_stranded`` in the
    coordinator-api stuck-escrow sweeper (#2996).
    """
    if not isinstance(record, dict):
        return False
    if _record_is_settled(record):
        return False
    if record.get("refund_tx_hash") or record.get("released_at") or record.get("refunded_at"):
        return False
    if not _released_amount_is_zero(record):
        return False
    state = str(record.get("state") or "").lower()
    status = str(record.get("status") or "").lower()
    if not state and not status:
        return False
    return state in _STRANDED_ESCROW_STATES and status in _STRANDED_ESCROW_STATUSES


class OrphanedTaskEscrowSweeper:
    """One reconciliation pass over PENDING/REJECTED task escrows (#2998).

    Synchronous throughout — the chain client and the escrow store are both
    sync — so the lifespan loop runs ``run_once`` via ``asyncio.to_thread``
    like the sibling expire sweep (#1750).
    """

    def __init__(
        self,
        *,
        payment_escrow: Any = None,
        escrow_rpc: ChainEscrowClient | None = None,
        load_balancer: Any = None,
        grace_seconds: float = 900.0,
        batch_size: int = 25,
        dry_run: bool = False,
    ) -> None:
        self._payment_escrow = payment_escrow
        self._escrow_rpc = escrow_rpc
        self._load_balancer = load_balancer
        self.grace_seconds = grace_seconds
        self.batch_size = batch_size
        self.dry_run = dry_run

    def _task_was_distributed(self, task_id: str) -> bool:
        """True when a load-balancer assignment exists for ``task_id``.

        An assignment is only created by ``task_distributor.submit_task`` —
        after ``_create_task_escrow`` returned LOCKED. Its presence means the
        escrow belongs to live (or settled) work and must be adopted, never
        refunded; its absence means the submit died before distribution.
        """
        lb = self._load_balancer
        if lb is None:
            return False
        try:
            assignment = lb.get_assignment(task_id)
        except Exception:  # noqa: BLE001 - an unreadable balancer must not refund; treat as distributed
            logger.warning("Orphan sweep could not read assignment for task %s", task_id)
            return True
        return assignment is not None

    def _stamp_probe(self, entry: EscrowEntry) -> None:
        """Record the probe time so skipped candidates rotate out of the batch."""
        mgr = self._payment_escrow
        if mgr is None:
            return
        try:
            entry.metadata[META_ORPHAN_PROBE_AT] = time.time()
            mgr.persist_entry(entry)
        except Exception:  # noqa: BLE001 - the stamp is best-effort bookkeeping
            logger.debug("Could not stamp orphan probe for escrow %s", entry.escrow_id)

    def _probe_due(self, entry: EscrowEntry, cutoff: float) -> bool:
        """True when the entry is past grace and due for a (re)probe."""
        created = entry.created_at or 0.0
        if created >= cutoff:
            return False
        last_probe = entry.metadata.get(META_ORPHAN_PROBE_AT)
        try:
            last_probe_f = float(last_probe) if last_probe is not None else 0.0
        except (TypeError, ValueError):
            last_probe_f = 0.0
        # Re-probe on the same cadence as the grace period: a skipped row
        # waits ~grace_seconds before the next chain read.
        return last_probe_f < cutoff

    def _reconcile_candidate(self, entry: EscrowEntry, client: ChainEscrowClient, counts: dict[str, int]) -> None:
        """Point-read the chain for one candidate and adopt or refund it."""
        try:
            record = client.get_escrow_record(entry.task_id)
        except EscrowRPCError as e:
            counts["failed"] += 1
            logger.warning("Orphan escrow sweep could not read chain record for task %s: %s", entry.task_id, e)
            return
        if not escrow_record_is_stranded(record):
            counts["skipped"] += 1
            self._stamp_probe(entry)
            return
        if self._task_was_distributed(entry.task_id):
            self._adopt_candidate(entry, record, counts)
        else:
            self._refund_candidate(entry, record, client, counts)

    def _adopt_candidate(self, entry: EscrowEntry, record: dict[str, Any] | None, counts: dict[str, int]) -> None:
        """Heal a distributed task's row to LOCKED from the chain record."""
        # Live work owns this escrow — flip the row to LOCKED so the normal
        # settle/expire paths can act on it.
        if self.dry_run:
            logger.info("[DRY-RUN] Would adopt chain lock for escrow %s (task %s)", entry.escrow_id, entry.task_id)
            counts["adopted"] += 1
            return
        prior_status = entry.status
        adopted = self._payment_escrow.adopt_chain_lock(
            entry,
            tx_hash_lock=record.get("lock_tx_hash") if isinstance(record, dict) else None,
            contract_id=record.get("contract_id") if isinstance(record, dict) else None,
        )
        if adopted:
            counts["adopted"] += 1
            logger.warning(
                "Adopted on-chain lock for escrow %s (task %s): local row was %s",
                entry.escrow_id,
                entry.task_id,
                prior_status,
            )
        else:
            counts["skipped"] += 1

    def _refund_candidate(
        self, entry: EscrowEntry, record: dict[str, Any] | None, client: ChainEscrowClient, counts: dict[str, int]
    ) -> None:
        """Refund an orphan whose submit died before distribution.

        The chain record's ``lock_tx_hash``/``contract_id`` are handed to
        ``refund_orphaned`` so the verified lock identity lands on the row
        *before* the refund tx is submitted (#3006): if that refund is
        apply-rejected, the reconcile restores LOCKED and the expire sweep
        can build a real chain submitter — without the backfill the row
        reads bookkeeping-only and gets marked REFUNDED with no transaction,
        stranding the on-chain funds.
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Would refund orphaned escrow %s (task %s)", entry.escrow_id, entry.task_id)
            counts["refunded"] += 1
            return
        submitter = make_refund_submitter(client, entry.task_id, reason=ORPHAN_REFUND_REASON)
        try:
            self._payment_escrow.refund_orphaned(
                entry,
                submitter=submitter,
                tx_hash_lock=record.get("lock_tx_hash") if isinstance(record, dict) else None,
                contract_id=record.get("contract_id") if isinstance(record, dict) else None,
            )
        except ValueError:
            # A concurrent transition (resubmit lock, settle path) won —
            # the CAS inside refund_orphaned already re-checked.
            counts["skipped"] += 1
            return
        except EscrowRPCError as e:
            if e.status_code == _LOCK_NOT_CONFIRMED_STATUS:
                counts["deferred"] += 1
            else:
                counts["failed"] += 1
                logger.error("Orphan escrow refund failed for task %s: %s", entry.task_id, e)
            return
        counts["refunded"] += 1
        logger.warning(
            "Refunded orphaned escrow %s for task %s: on-chain lock had no payment row",
            entry.escrow_id,
            entry.task_id,
        )

    def run_once(self) -> dict[str, int]:
        """One reconciliation pass. Returns counts for logging and tests."""
        counts = {"candidates": 0, "adopted": 0, "refunded": 0, "failed": 0, "deferred": 0, "skipped": 0}
        mgr = self._payment_escrow
        client = self._escrow_rpc
        if mgr is None or client is None:
            return counts
        cutoff = time.time() - self.grace_seconds
        candidates = sorted(
            (e for e in mgr.get_all_escrows() if e.status in _ORPHAN_ELIGIBLE_STATUSES and self._probe_due(e, cutoff)),
            key=lambda e: e.created_at or 0.0,
        )[: self.batch_size]
        for entry in candidates:
            counts["candidates"] += 1
            self._reconcile_candidate(entry, client, counts)
        logger.debug(
            "Orphaned escrow sweep complete: candidates=%s adopted=%s refunded=%s failed=%s deferred=%s skipped=%s",
            counts["candidates"],
            counts["adopted"],
            counts["refunded"],
            counts["failed"],
            counts["deferred"],
            counts["skipped"],
        )
        return counts
