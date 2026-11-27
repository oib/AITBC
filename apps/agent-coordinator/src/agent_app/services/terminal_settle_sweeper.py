"""Reconcile terminal task escrows whose settle tx never sealed (#3026).

``PaymentEscrow.release()``/``refund()`` record RELEASED/REFUNDED at
*mempool admission*, not at seal — the same asymmetry #2744/#2926 pinned
for the lock and apply-rejected settle legs. The reconcile in
``_escrow_sweep_once`` only flips a terminal row on a *proven rejection*
(``transaction_status == "rejected"``); a settle tx EVICTED from the
mempool before ever being applied leaves no durable chain row at all, so
``_settle_tx_rejected`` answers ``None`` forever. The chain-side
``escrow_settlement_sweeper`` demotes its own unsealed mark after ~900 s,
but the LOCAL row stays RELEASED/REFUNDED permanently: the provider goes
unpaid (RELEASED) or the requester unpaid (REFUNDED) with the on-chain
escrow still locked, and the row is invisible to every worklist — the
orphan sweeper scans only PENDING/REJECTED, ``expire_stale`` only LOCKED.

This pass is the terminal-state sibling of ``OrphanedTaskEscrowSweeper``
(#2998): for each RELEASED/REFUNDED entry older than the grace horizon it
probes the settle hash the terminal state used (``tx_hash_release`` /
``tx_hash_refund``) through ``ChainEscrowClient.transaction_probe``, which
distinguishes the three answers ``transaction_status`` flattens into
``None``:

* **sealed** (durable confirmed row) → stamp
  ``metadata["settle_probe_confirmed_at"]`` so the row is never probed
  again (the store excludes stamped rows in SQL, #1515 keeps them out of
  the hot cache).
* **pending** (mempool view, ``state == "pending"``) → skip: the tx may
  still land; re-probe on the grace cadence via ``settle_probe_at``.
* **absent everywhere** (404 — the node checked both the sealed table and
  its mempool) or **rejected** (durable dead letter) → the settle never
  landed → *demote* the row back to LOCKED through
  ``PaymentEscrow.demote_unsealed_settle``, a CAS guarded by the expected
  terminal status so a concurrent transition wins. The row then re-enters
  the normal release/refund/expire paths: a retried ``complete``
  re-submits the release (chain-side idempotent per job id), and
  ``expire_stale`` refunds a REFUNDED-demoted row whose task never
  settles.
* **unknown** (probe failure, unreadable answer) → skip and stamp; unknown
  is never death.

Terminal rows that never recorded a settle hash (bookkeeping-only
escrows, or a submitter that returned nothing) cannot be probed by hash —
the chain escrow *record* is the fallback truth: settled record or no
record at all means nothing on-chain is owed (stamp confirmed); a live
unsettled lock means the settle never landed and the row is demoted with
the record's lock identity backfilled (same contract as ``refund_orphaned``,
#3006) so the expire sweep can build a real refund submitter.

Every chain answer is applied through an attempt-scoped CAS (#3035): the
probe runs outside the escrow manager lock, so between probe and write a
concurrent transition (the reject/expiry reconcile cycling a refund
LOCKED -> REFUNDED with a replacement tx) can land a *newer* settle
attempt under the same terminal status. Demotes, probe stamps, and the
permanent-confirmation marker therefore compare the settle tx hash the
probe observed — a stale verdict never applies to a newer attempt.

Synchronous throughout — the chain client and the escrow store are both
sync — so the lifespan loop runs ``run_once`` via ``asyncio.to_thread``
like the sibling sweeps (#1750).
"""

from __future__ import annotations

import time
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.payment_escrow import EscrowEntry, EscrowStatus
from aitbc.utils.tx_status import tx_sealed_for_money

from .chain_escrow import ChainEscrowClient, EscrowRPCError
from .orphan_escrow_sweeper import _record_is_settled, escrow_record_is_stranded

logger = get_logger(__name__)

# Local terminal states whose settle leg must be proven on-chain. EXPIRED
# and REJECTED carry no settle tx (REJECTED died at lock; nothing ever
# moved) and PENDING/LOCKED belong to the other sweepers.
_TERMINAL_SETTLE_STATUSES = (EscrowStatus.RELEASED, EscrowStatus.REFUNDED)

# Metadata keys: ``settle_probe_at`` stamps the last definitive probe so
# skipped candidates re-check on the grace cadence instead of every pass;
# ``settle_probe_confirmed_at`` marks a row resolved forever (sealed settle
# tx, settled chain record, or no on-chain escrow at all).
META_SETTLE_PROBE_AT = "settle_probe_at"
META_SETTLE_CONFIRMED_AT = "settle_probe_confirmed_at"


def _settle_tx_hash(entry: EscrowEntry, status: EscrowStatus | None = None) -> str | None:
    """The settle hash the entry's terminal state submitted, if recorded.

    ``status`` optionally pins which leg to read — the reconcile snapshot
    passes the status observed at listing time so a mid-flight mutation of
    the shared hot-cache object cannot pick the wrong leg (#3035).
    """
    leg = status if status is not None else entry.status
    if leg == EscrowStatus.RELEASED:
        return entry.tx_hash_release
    if leg == EscrowStatus.REFUNDED:
        return entry.tx_hash_refund
    return None


def _settle_recorded_at(entry: EscrowEntry) -> float:
    """Best timestamp for when the settle leg was recorded.

    ``released_at`` is a real column; refunds stamp ``metadata["refunded_at"]``
    (#3026). Rows refunded before that stamp fall back to ``locked_at`` /
    ``created_at`` — both predate the settle, so the grace horizon can only
    be reached *earlier* than ideal, and the pending/unknown classifications
    keep an over-eager probe harmless.
    """
    if entry.released_at:
        return float(entry.released_at)
    refunded_at = entry.metadata.get("refunded_at")
    if refunded_at is not None:
        try:
            return float(refunded_at)
        except (TypeError, ValueError):
            pass
    return float(entry.locked_at or entry.created_at or 0.0)


def _classify_probe(info: dict[str, Any] | None) -> str:
    """Classify a ``transaction_probe`` answer.

    ``sealed`` — confirmed AND sealed (``tx_sealed_for_money``: a
    ``status='failed'`` row carries a block_height but moved no value,
    #3049); ``failed_sealed`` — apply-failed durable row: sealed into a
    block but the apply reverted, so the settle never landed and the row
    must demote, not tombstone; ``rejected`` — durable dead letter;
    ``pending`` — mempool view (``state == "pending"``, incl.
    ``previously_rejected`` resubmissions that may still seal); ``absent``
    — the 404 sentinel the probe returns when neither the sealed table
    nor the mempool knows the hash; ``unknown`` — anything else, including
    ``None`` (probe failure).
    """
    if not isinstance(info, dict):
        return "unknown"
    if info.get("status") == "absent" or info.get("state") == "absent":
        return "absent"
    if info.get("state") == "pending":
        return "pending"
    status = str(info.get("status") or "").lower()
    if status == "rejected":
        return "rejected"
    if status == "failed":
        return "failed_sealed"
    if tx_sealed_for_money(info):
        return "sealed"
    return "unknown"


class TerminalSettleSweeper:
    """One reconciliation pass over terminal escrows with unproven settle txs (#3026).

    Synchronous throughout — see the module docstring; the lifespan loop
    runs ``run_once`` via ``asyncio.to_thread`` like the sibling sweeps.
    """

    def __init__(
        self,
        *,
        payment_escrow: Any = None,
        escrow_rpc: ChainEscrowClient | None = None,
        grace_seconds: float = 900.0,
        batch_size: int = 25,
        dry_run: bool = False,
    ) -> None:
        self._payment_escrow = payment_escrow
        self._escrow_rpc = escrow_rpc
        self.grace_seconds = grace_seconds
        self.batch_size = batch_size
        self.dry_run = dry_run

    def _probe_due(self, entry: EscrowEntry, cutoff: float) -> bool:
        """True when the settle is past grace and due for a (re)probe."""
        if _settle_recorded_at(entry) >= cutoff:
            return False
        last_probe = entry.metadata.get(META_SETTLE_PROBE_AT)
        try:
            last_probe_f = float(last_probe) if last_probe is not None else 0.0
        except (TypeError, ValueError):
            last_probe_f = 0.0
        # Re-probe on the same cadence as the grace period: a skipped row
        # waits ~grace_seconds before the next chain read.
        return last_probe_f < cutoff

    def _eligible(self, entry: EscrowEntry) -> bool:
        """True when the terminal row still needs its settle leg proven."""
        if entry.status not in _TERMINAL_SETTLE_STATUSES:
            return False
        # Resolved forever — sealed settle, settled chain record, or no
        # on-chain escrow at all. Hot-cache rows carry the same stamp the
        # store excludes in SQL.
        return not entry.metadata.get(META_SETTLE_CONFIRMED_AT)

    def _stamp_probe(
        self,
        entry: EscrowEntry,
        *,
        expected_status: EscrowStatus,
        expected_settle_tx_hash: str | None,
    ) -> None:
        """Record the probe time so skipped candidates rotate out of the batch.

        The stamp is a CAS on the probed attempt (#3035): it lands only if
        the row still sits in ``expected_status`` recording
        ``expected_settle_tx_hash`` — a replacement settle attempt that
        landed mid-probe must not inherit this probe's bookkeeping.
        """
        mgr = self._payment_escrow
        if mgr is None or self.dry_run:
            return
        try:
            mgr.stamp_terminal(
                entry,
                {META_SETTLE_PROBE_AT: time.time()},
                expected_status=expected_status,
                expected_settle_tx_hash=expected_settle_tx_hash,
            )
        except Exception:  # noqa: BLE001 - the stamp is best-effort bookkeeping
            logger.debug("Could not stamp settle probe for escrow %s", entry.escrow_id)

    def _mark_confirmed(
        self,
        entry: EscrowEntry,
        counts: dict[str, int],
        *,
        expected_status: EscrowStatus,
        expected_settle_tx_hash: str | None,
    ) -> None:
        """Stamp a resolved-forever marker: sealed settle or nothing owed on-chain.

        Same attempt-scoped CAS as the demote (#3035): a stale "confirmed"
        verdict must never mark a *newer* settle attempt resolved forever.
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Would confirm settle for escrow %s (task %s)", entry.escrow_id, entry.task_id)
            counts["confirmed"] += 1
            return
        mgr = self._payment_escrow
        if mgr is None:
            return
        try:
            stamped = mgr.stamp_terminal(
                entry,
                {META_SETTLE_CONFIRMED_AT: time.time()},
                expected_status=expected_status,
                expected_settle_tx_hash=expected_settle_tx_hash,
            )
        except Exception:  # noqa: BLE001 - the stamp is best-effort bookkeeping
            logger.debug("Could not confirm settle for escrow %s", entry.escrow_id)
            return
        if stamped:
            counts["confirmed"] += 1
        else:
            # CAS lost — the row moved to a different attempt mid-probe;
            # the verdict does not apply to it.
            counts["skipped"] += 1

    def _demote(
        self,
        entry: EscrowEntry,
        counts: dict[str, int],
        *,
        expected_status: EscrowStatus,
        expected_settle_tx_hash: str | None,
        reason: str,
        evidence: dict[str, Any],
        tx_hash_lock: str | None = None,
        contract_id: str | None = None,
    ) -> None:
        """Demote a terminal row to LOCKED — the settle leg never landed.

        ``expected_settle_tx_hash`` is the attempt the probe observed
        (#3035): the CAS applies only while the row still records that
        settle hash — a replacement attempt landing mid-probe wins.
        """
        if self.dry_run:
            logger.info(
                "[DRY-RUN] Would demote escrow %s (task %s) %s -> LOCKED: %s",
                entry.escrow_id,
                entry.task_id,
                expected_status,
                reason,
            )
            counts["demoted"] += 1
            return
        mgr = self._payment_escrow
        if mgr is None:
            return
        try:
            demoted = mgr.demote_unsealed_settle(
                entry,
                expected_status=expected_status,
                expected_settle_tx_hash=expected_settle_tx_hash,
                reason=reason,
                evidence=evidence,
                tx_hash_lock=tx_hash_lock,
                contract_id=contract_id,
            )
        except Exception:  # noqa: BLE001 - per-entry containment: a demote failure retries next pass
            counts["failed"] += 1
            logger.error("Terminal settle demote failed for escrow %s: %s", entry.escrow_id, reason)
            return
        if demoted:
            counts["demoted"] += 1
            logger.warning(
                "Demoted terminal escrow %s (task %s) %s -> LOCKED: %s",
                entry.escrow_id,
                entry.task_id,
                expected_status,
                reason,
            )
        else:
            # CAS lost — a concurrent transition (settle retry, operator
            # action) already moved the row, or a replacement settle
            # attempt landed mid-probe (#3035); it wins.
            counts["skipped"] += 1

    def _probe_settle_tx(
        self,
        entry: EscrowEntry,
        client: ChainEscrowClient,
        tx_hash: str,
        expected_status: EscrowStatus,
        counts: dict[str, int],
    ) -> None:
        """Classify the settle hash on-chain and act on proven outcomes."""
        try:
            info = client.transaction_probe(tx_hash, chain_id=entry.chain_id)
        except Exception:  # noqa: BLE001 - per-entry containment: a probe failure retries next pass
            counts["failed"] += 1
            self._stamp_probe(entry, expected_status=expected_status, expected_settle_tx_hash=tx_hash)
            return
        verdict = _classify_probe(info)
        if verdict == "sealed":
            self._mark_confirmed(entry, counts, expected_status=expected_status, expected_settle_tx_hash=tx_hash)
            return
        if verdict == "pending":
            # Still in the mempool — it may yet seal. Re-check on cadence.
            counts["skipped"] += 1
            self._stamp_probe(entry, expected_status=expected_status, expected_settle_tx_hash=tx_hash)
            return
        if verdict in ("absent", "rejected", "failed_sealed"):
            # A failed-sealed settle moved no value — same re-drive path
            # as absent/rejected: demote to LOCKED, never tombstone (#3049).
            reason = {
                "absent": "settle_tx_absent_from_chain",
                "rejected": "settle_tx_rejected_on_chain",
                "failed_sealed": "settle_tx_failed_sealed_on_chain",
            }[verdict]
            self._demote(
                entry,
                counts,
                expected_status=expected_status,
                expected_settle_tx_hash=tx_hash,
                reason=reason,
                evidence={
                    "tx_hash": tx_hash,
                    "probe": verdict,
                    "chain_answer": info if isinstance(info, dict) else None,
                    "probed_at": time.time(),
                },
            )
            return
        # unknown — probe failure or an unclassifiable durable row. Unknown
        # is never death: skip and re-probe on cadence.
        counts["failed"] += 1
        self._stamp_probe(entry, expected_status=expected_status, expected_settle_tx_hash=tx_hash)

    def _probe_chain_record(
        self, entry: EscrowEntry, client: ChainEscrowClient, expected_status: EscrowStatus, counts: dict[str, int]
    ) -> None:
        """Fallback truth for terminal rows that never recorded a settle hash.

        No hash means either a bookkeeping-only escrow (no on-chain lock at
        all) or a settle submitter that returned nothing. The chain escrow
        record decides: settled or missing record → nothing is owed
        (confirmed); a live unsettled lock → the settle never landed and the
        row demotes with the record's lock identity backfilled so the expire
        sweep can refund it.
        """
        try:
            record = client.get_escrow_record(entry.task_id)
        except EscrowRPCError as e:
            counts["failed"] += 1
            logger.warning("Terminal settle sweep could not read chain record for task %s: %s", entry.task_id, e)
            return
        # The probed attempt identity is "no settle hash recorded" (#3035):
        # the CAS applies only while the row still records none — a settle
        # attempt that landed mid-probe must not inherit this verdict.
        if record is None or _record_is_settled(record):
            # No on-chain escrow, or the chain shows it settled either way —
            # the local terminal row is the final truth.
            self._mark_confirmed(entry, counts, expected_status=expected_status, expected_settle_tx_hash=None)
            return
        if not escrow_record_is_stranded(record):
            # Mid-flight or unrecognised record shape — not proof of a dead
            # settle. Skip and re-probe on cadence.
            counts["skipped"] += 1
            self._stamp_probe(entry, expected_status=expected_status, expected_settle_tx_hash=None)
            return
        # Live on-chain lock under a terminal local row: the settle never
        # landed. Backfill the verified lock identity so the demoted LOCKED
        # row's expire refund builds a real chain submitter (#3006 contract).
        lock_tx_hash = record.get("lock_tx_hash") if isinstance(record, dict) else None
        contract_id = record.get("contract_id") if isinstance(record, dict) else None
        if not (entry.tx_hash_lock or lock_tx_hash):
            # No lock identity anywhere — a demoted row could only be
            # refunded bookkeeping-only and would re-strand. Skip + log.
            counts["skipped"] += 1
            logger.warning(
                "Terminal escrow %s (task %s) has a live chain lock but no lock identity; skipping demote",
                entry.escrow_id,
                entry.task_id,
            )
            self._stamp_probe(entry, expected_status=expected_status, expected_settle_tx_hash=None)
            return
        self._demote(
            entry,
            counts,
            expected_status=expected_status,
            expected_settle_tx_hash=None,
            reason="terminal_row_but_chain_lock_live",
            evidence={"chain_record": record, "probed_at": time.time()},
            tx_hash_lock=str(lock_tx_hash) if lock_tx_hash else None,
            contract_id=str(contract_id) if contract_id else None,
        )

    def _reconcile_candidate(self, entry: EscrowEntry, client: ChainEscrowClient, counts: dict[str, int]) -> None:
        # Snapshot the terminal status BEFORE the probe: the entry object is
        # shared with the hot cache, so a concurrent transition (the #2926
        # reconcile flipping RELEASED->LOCKED, an operator action) mutates it
        # mid-flight — the CAS must compare against the status at listing
        # time, not whatever the object reads after the probe.
        expected_status = entry.status
        tx_hash = _settle_tx_hash(entry, expected_status)
        if tx_hash:
            self._probe_settle_tx(entry, client, str(tx_hash), expected_status, counts)
        else:
            self._probe_chain_record(entry, client, expected_status, counts)

    def run_once(self) -> dict[str, int]:
        """One reconciliation pass. Returns counts for logging and tests."""
        counts = {
            "candidates": 0,
            "confirmed": 0,
            "demoted": 0,
            "failed": 0,
            "skipped": 0,
        }
        mgr = self._payment_escrow
        client = self._escrow_rpc
        if mgr is None or client is None:
            return counts
        cutoff = time.time() - self.grace_seconds
        candidates = sorted(
            (
                e
                for e in mgr.get_terminal_escrows(_TERMINAL_SETTLE_STATUSES)
                if self._eligible(e) and self._probe_due(e, cutoff)
            ),
            key=_settle_recorded_at,
        )[: self.batch_size]
        for entry in candidates:
            counts["candidates"] += 1
            self._reconcile_candidate(entry, client, counts)
        logger.debug(
            "Terminal settle sweep complete: candidates=%s confirmed=%s demoted=%s failed=%s skipped=%s",
            counts["candidates"],
            counts["confirmed"],
            counts["demoted"],
            counts["failed"],
            counts["skipped"],
        )
        return counts
