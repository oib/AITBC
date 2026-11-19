"""Single block import, append, and fork resolution.

``BlockImportMixin`` is assembled from sibling mixin modules
(``sync_block_import_validation``, ``sync_block_import_sequential``,
``sync_block_import_roots``, ``sync_block_import_mempool`` and
``sync_block_import_fork``) — the stage helpers moved there are
byte-identical and every ``self._…`` call resolves through the combined
class exactly as before the split (#1860). The methods kept here are the
import driver, the append/parallel apply path and the commit tail.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, text
from sqlmodel import Session, select

from aitbc.parallel import DependencyGraph, ParallelExecutor

from .base_models import Account, Block, _to_ait_address
from .base_models import Transaction as ChainTransaction
from .config import settings
from .logger import get_logger
from .metrics import (
    block_height,
    block_processing_duration,
    metrics_registry,
    sync_blocks_imported,
    sync_failures_total,
    sync_import_phase_seconds,
)
from .state import side_root_shadow
from .state.block_deltas import BlockDeltaJournal, revert_losing_segment
from .state.bridge_credit import BRIDGE_AUTHORITY_TX_TYPES
from .state.pure_state_transition import (
    SEQUENTIAL_ONLY_TX_TYPES,
    StateDelta,
    _determine_tx_type,
    _escrow_address,
    apply_delta_to_map,
    apply_deltas_to_db,
    compute_state_delta,
    extract_read_write_sets,
)
from .state.state_transition import (
    StateTransition,
    _bridge_release_authority,
    build_bridge_lock_context,
    build_escrow_context,
    get_block_version,
    get_state_transition,
    use_account_nonce_override,
)
from .mempool import compute_tx_hash
from .sync_base import SyncBase
from .sync_block_import_fork import ForkResolutionMixin
from .sync_block_import_mempool import ImportMempoolMixin
from .sync_block_import_roots import ImportRootsMixin
from .sync_block_import_sequential import SequentialApplyMixin
from .sync_block_import_validation import ImportValidationMixin
from .sync_validator import ImportResult

logger = get_logger(__name__)

# FORK-GUARD-1: keep False until a recipient-rule guard aligns the
# parallel path with pure_state_transition for zero-value fresh recipients.
_PARALLEL_V2V8_ENABLED: bool = False

# Transaction types whose side effects (pools, stakes, GPU tables, bond rows,
# governance parameters, burn semantics, etc.) are not modeled by the
# pure/parallel delta map. They must be applied through the full
# StateTransition.apply_transaction sequential path to keep state roots and
# side-effect tables consistent across nodes. The canonical list lives in
# pure_state_transition.SEQUENTIAL_ONLY_TX_TYPES (one list, one rule — the
# pure path returns requires_sequential=True for exactly these types).
_SEQUENTIAL_ONLY_TX_TYPES = SEQUENTIAL_ONLY_TX_TYPES


# #2261 SYNC-IMPORT-DB-BUSY-1: WAL snapshot conflicts (SQLITE_BUSY_SNAPSHOT)
# bypass the per-connection busy_timeout — the append loses the race against
# a concurrent writer (e.g. the rpc bridge-release finalizer) and fails
# immediately instead of waiting. Retry the whole append on a fresh NullPool
# session with linear backoff before taking the generic failure path.
_BUSY_APPEND_RETRIES = 3
_BUSY_APPEND_BACKOFF_S = 0.5


def _is_sqlite_lock_error(exc: BaseException) -> bool:
    """True for sqlite 'database is locked' through SQLAlchemy wrapping."""
    orig = getattr(exc, "orig", None) or exc
    text = f"{orig} {exc}".lower()
    return "database is locked" in text or "database table is locked" in text


@dataclass
class _AppendContext:
    """Shared stage parameters for ``BlockImportMixin._append_block``.

    The append path is split into ordered stage helpers; this object carries
    the values every stage needs so each helper keeps an explicit signature
    instead of a dozen positional arguments. The mutable fields
    (``tx_only_root``, ``gate_height``, the lock-hash sets) are filled by the
    era-prep stage and consumed by the apply/root stages — the mutation order
    is the same as the original inline sequence.
    """

    session: Session
    block_data: dict[str, Any]
    block_hash: str
    block_version: int
    timestamp: datetime
    tx_only_root: bool
    gate_height: int
    probe: bool
    reject_tag: str
    check_deadline: Callable[[], None]
    probe_deadline: float | None
    journal: BlockDeltaJournal | None
    skip_state_root_validation: bool
    declared_lock_hashes: set[str] = field(default_factory=set)
    successful_lock_hashes: set[str] = field(default_factory=set)


class BlockImportMixin(
    ImportValidationMixin,
    SequentialApplyMixin,
    ImportRootsMixin,
    ImportMempoolMixin,
    ForkResolutionMixin,
    SyncBase,
):
    """Import a single block, append it, and resolve chain forks."""

    def _make_import_result(self, **kwargs: Any) -> ImportResult:
        """Create an ImportResult and record Prometheus sync failures if rejected."""
        result = ImportResult(**kwargs)
        if not result.accepted:
            reason = result.reason.split(":")[0].strip()[:40]
            sync_failures_total.labels(chain_id=self._chain_id, reason=reason).inc()
        return result

    @staticmethod
    def _normalize_block_metadata(block_data: dict[str, Any]) -> dict[str, Any]:
        """#2156: ``block_metadata`` is a JSON string everywhere downstream
        (validators ``json.loads`` it, the column is text). Validators still
        running the pre-fix PBFT view-change re-seal gossip it as a dict;
        serialise it at the single import entry so every later parse, the
        strict-era gate and the DB write see the string they assume. Returns
        a copy — the caller's message is never mutated."""
        raw = block_data.get("block_metadata")
        if not isinstance(raw, dict):
            return block_data
        return {**block_data, "block_metadata": json.dumps(raw)}

    def import_block(
        self,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None = None,
        skip_state_root_validation: bool = False,
    ) -> ImportResult:
        """Import a block from a remote peer.

        Handles:
        - Normal append (block extends our chain)
        - Fork resolution (block is on a longer chain)
        - Duplicate detection
        - Signature validation

        Args:
            block_data: Block data dictionary
            transactions: Optional list of transactions
            skip_state_root_validation: Skip state root validation (for bulk import)
        """
        start = time.perf_counter()
        block_data = self._normalize_block_metadata(block_data)
        height = block_data.get("height", -1)
        block_hash = block_data.get("hash", "")
        if transactions is None:
            transactions = block_data.get("transactions") or []
        parent_hash = block_data.get("parent_hash", "")
        metrics_registry.increment("sync_blocks_received_total")
        # NOTE: kept inline — tests drive import_block on minimal stubs that
        # only carry _validate_signatures/_validator/_normalize_block_metadata.
        if self._validate_signatures:
            phase_start = time.perf_counter()
            valid, reason = self._validator.validate_block_signature(block_data)
            sync_import_phase_seconds.labels(phase="signature_validation").observe(time.perf_counter() - phase_start)
            if not valid:
                metrics_registry.increment("sync_blocks_rejected_total")
                logger.warning(
                    "Block rejected: signature validation failed for height %s: %s",
                    height,
                    reason,
                    extra={"height": height, "reason": reason},
                )
                return self._make_import_result(accepted=False, height=height, block_hash=block_hash, reason=reason)
        # The in-memory replay cache must be scoped to one block. A rejected
        # block is rolled back, but if the cache is not cleared the next import
        # attempt reports "replay attack" for transactions that were never
        # actually persisted.
        get_state_transition().reset_processed_cache()
        with self._session_factory() as session:
            return self._import_block_in_session(
                session,
                block_data,
                transactions,
                skip_state_root_validation,
                height,
                block_hash,
                parent_hash,
                start,
            )

    def _import_block_in_session(
        self,
        session: Session,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]],
        skip_state_root_validation: bool,
        height: int,
        block_hash: str,
        parent_hash: str,
        start: float,
    ) -> ImportResult:
        """Route an imported block by height: next-block append, same-height
        fork/stale resolution, or gap rejection."""
        from .database import ensure_chain_db_healthy

        phase_start = time.perf_counter()
        db_ok, db_reason = ensure_chain_db_healthy(self._chain_id, session=session)
        sync_import_phase_seconds.labels(phase="db_health_check").observe(time.perf_counter() - phase_start)
        if not db_ok:
            metrics_registry.increment("sync_blocks_rejected_total")
            logger.error(
                "Refusing block import at height %s for chain %s — chain.db integrity failure: %s",
                height,
                self._chain_id,
                db_reason,
            )
            return self._make_import_result(
                accepted=False,
                height=height,
                block_hash=block_hash,
                reason=f"chain.db integrity check failed: {db_reason}",
            )
        rejected = self._check_genesis_metadata(session, block_data, height, block_hash)
        if rejected is not None:
            return rejected
        lookup_start = time.perf_counter()
        rejected = self._check_duplicate_import(session, height, block_hash)
        if rejected is not None:
            return rejected
        our_head = session.exec(
            select(Block).where(Block.chain_id == self._chain_id).order_by(text("height DESC")).limit(1)
        ).first()
        our_height = our_head.height if our_head else -1
        gap = height - our_height
        logger.info(
            "Import block check: remote height=%s, local height=%s (gap=%s), parent=%s, block=%s",
            height,
            our_height,
            gap,
            parent_hash,
            block_hash,
        )
        if height == our_height + 1:
            return self._import_next_block(
                session,
                block_data,
                transactions,
                skip_state_root_validation,
                height,
                block_hash,
                parent_hash,
                our_head,
                our_height,
                lookup_start,
                start,
            )
        if height <= our_height:
            return self._import_at_or_below_head(session, block_data, transactions, our_head, height, block_hash, our_height)
        if height > our_height + 1:
            metrics_registry.increment("sync_blocks_gap_total")
            return self._make_import_result(
                accepted=False,
                height=height,
                block_hash=block_hash,
                reason=f"Gap detected (our height: {our_height}, received: {height})",
            )
        return self._make_import_result(accepted=False, height=height, block_hash=block_hash, reason="Unhandled import case")

    def _check_genesis_metadata(
        self, session: Session, block_data: dict[str, Any], height: int, block_hash: str
    ) -> ImportResult | None:
        """Genesis block metadata validation — runs before the local head is
        consulted."""
        if height == 0 and block_data.get("block_metadata"):
            is_valid, reason = self._validate_genesis_metadata(block_data, session)
            if not is_valid:
                metrics_registry.increment("sync_state_root_rejected_total")
                logger.error(
                    "Genesis block metadata validation failed: %s", reason, extra={"height": height, "hash": block_hash}
                )
                return self._make_import_result(accepted=False, height=height, block_hash=block_hash, reason=reason)
        return None

    def _check_duplicate_import(self, session: Session, height: int, block_hash: str) -> ImportResult | None:
        """Duplicate detection by block hash."""
        existing = session.exec(select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == block_hash)).first()
        if existing:
            metrics_registry.increment("sync_blocks_duplicate_total")
            return self._make_import_result(
                accepted=False, height=height, block_hash=block_hash, reason="Block already exists"
            )
        return None

    def _import_next_block(
        self,
        session: Session,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]],
        skip_state_root_validation: bool,
        height: int,
        block_hash: str,
        parent_hash: str,
        our_head: Block | None,
        our_height: int,
        lookup_start: float,
        start: float,
    ) -> ImportResult:
        """Peer is exactly one height ahead: append when the parent is our tip,
        otherwise the parent mismatch is a divergence (V23-90)."""
        parent_exists = session.exec(
            select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == parent_hash)
        ).first()
        parent_is_our_head = parent_exists is not None and our_head is not None and parent_exists.hash == our_head.hash
        sync_import_phase_seconds.labels(phase="block_lookup").observe(time.perf_counter() - lookup_start)
        if (height == 0 and parent_hash == "0x00") or (height > 0 and parent_is_our_head):
            return self._append_with_conflict_retry(
                session, block_data, transactions, skip_state_root_validation, height, block_hash, start
            )
        # Peer is one height ahead but the parent is not our tip: a fork
        # where the peer is *ahead* of us. `_resolve_fork` only runs when
        # height <= our_height, so this used to fall through to
        # "Unhandled import case" and stall catch-up forever (V23-90).
        metrics_registry.increment("sync_divergence_rejected_total")
        our_hash = our_head.hash if our_head else ""
        return self._make_import_result(
            accepted=False,
            height=height,
            block_hash=block_hash,
            reason=(
                f"Divergent chain: next block parent {parent_hash[:16]}... "
                f"is not our head {our_hash[:16]}... at height {our_height}"
            ),
            diverged=True,
        )

    def _import_at_or_below_head(
        self,
        session: Session,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]],
        our_head: Block | None,
        height: int,
        block_hash: str,
        our_height: int,
    ) -> ImportResult:
        """Same-height hash conflict goes to fork resolution; anything else at
        or below our head is stale."""
        existing_at_height = session.exec(
            select(Block).where(Block.chain_id == self._chain_id).where(Block.height == height)
        ).first()
        if existing_at_height and existing_at_height.hash != block_hash:
            if our_head:
                return self._resolve_fork(session, block_data, transactions, our_head)
        metrics_registry.increment("sync_blocks_stale_total")
        return self._make_import_result(
            accepted=False, height=height, block_hash=block_hash, reason=f"Stale block (our height: {our_height})"
        )

    def _append_with_conflict_retry(
        self,
        session: Session,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]],
        skip_state_root_validation: bool,
        height: int,
        block_hash: str,
        start: float,
    ) -> ImportResult:
        """Append the next block, classifying append failures: chain.db
        quarantine on storage errors (#1740), duplicate/concurrent-import
        detection and one retry on a phantom height marker (Refs #712),
        divergent-commit detection, and the generic failure path."""
        try:
            result = self._append_block(session, block_data, transactions, skip_state_root_validation)
            duration = time.perf_counter() - start
            metrics_registry.observe("sync_import_duration_seconds", duration)
            block_processing_duration.observe(duration)
            return result
        except Exception as append_exc:  # noqa: BLE001 - must-run rollback + quarantine classification boundary
            session.rollback()
            # #1740: SQLITE_FULL / IOERR / corrupt-store errors
            # leave quick_check green while every write fails —
            # quarantine on the error shape, not just on
            # integrity-check failures.
            from .database import quarantine_chain_db_for_error

            quarantined = quarantine_chain_db_for_error(self._chain_id, append_exc, session=session)
            if quarantined is not None:
                logger.error(
                    "Append block failed for height %s — chain.db quarantined: %s",
                    height,
                    quarantined,
                )
                return self._make_import_result(
                    accepted=False,
                    height=height,
                    block_hash=block_hash,
                    reason=f"chain.db unrecoverable error — quarantined: {quarantined}",
                )
            if _is_sqlite_lock_error(append_exc):
                # #2261: busy_timeout cannot cover WAL snapshot conflicts —
                # retry on fresh sessions before failing the import.
                return self._append_with_busy_retry(
                    block_data, transactions, skip_state_root_validation, height, block_hash, start
                )
            reason = str(append_exc).lower()
            if "unique" in reason and "constraint" in reason:
                return self._handle_append_unique_conflict(
                    session, append_exc, block_data, transactions, skip_state_root_validation, height, block_hash, start
                )
            logger.exception("Append block failed for height %s", height)
            return self._make_import_result(
                accepted=False,
                height=height,
                block_hash=block_hash,
                reason=f"Append block failed: {append_exc}",
            )

    def _append_with_busy_retry(
        self,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]],
        skip_state_root_validation: bool,
        height: int,
        block_hash: str,
        start: float,
    ) -> ImportResult:
        """Retry ``_append_block`` on fresh sessions after a sqlite lock error.

        #2261: the failed session's read snapshot is poisoned
        (SQLITE_BUSY_SNAPSHOT bypasses busy_timeout), so each attempt opens a
        new NullPool session and re-verifies the append preconditions — no
        duplicate hash, height still next, parent still our tip — before
        re-appending. If the chain moved meanwhile the block is routed
        through the normal at-or-below-head / gap classification instead of
        blind-appending onto a moved tip.
        """
        parent_hash = str(block_data.get("parent_hash") or "")
        last_exc: BaseException | None = None
        for attempt in range(_BUSY_APPEND_RETRIES):
            time.sleep(_BUSY_APPEND_BACKOFF_S * (attempt + 1))
            metrics_registry.increment("sync_import_busy_retry_total")
            try:
                with self._session_factory() as session:
                    existing = session.exec(
                        select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == block_hash)
                    ).first()
                    if existing is not None:
                        metrics_registry.increment("sync_blocks_duplicate_total")
                        return self._make_import_result(
                            accepted=False,
                            height=height,
                            block_hash=block_hash,
                            reason="Block already exists (concurrent import during lock retry)",
                        )
                    head = session.exec(
                        select(Block).where(Block.chain_id == self._chain_id).order_by(text("height DESC")).limit(1)
                    ).first()
                    our_height = head.height if head else -1
                    if height == our_height + 1:
                        parent_is_head = (height == 0 and parent_hash == "0x00") or (
                            head is not None and head.hash == parent_hash
                        )
                        if not parent_is_head:
                            metrics_registry.increment("sync_divergence_rejected_total")
                            our_hash = head.hash if head else ""
                            return self._make_import_result(
                                accepted=False,
                                height=height,
                                block_hash=block_hash,
                                reason=(
                                    f"Divergent chain: next block parent {parent_hash[:16]}... "
                                    f"is not our head {our_hash[:16]}... at height {our_height}"
                                ),
                                diverged=True,
                            )
                        result = self._append_block(session, block_data, transactions, skip_state_root_validation)
                        duration = time.perf_counter() - start
                        metrics_registry.observe("sync_import_duration_seconds", duration)
                        block_processing_duration.observe(duration)
                        return result
                    if height <= our_height:
                        return self._import_at_or_below_head(
                            session, block_data, transactions, head, height, block_hash, our_height
                        )
                    metrics_registry.increment("sync_blocks_gap_total")
                    return self._make_import_result(
                        accepted=False,
                        height=height,
                        block_hash=block_hash,
                        reason=f"Gap detected (our height: {our_height}, received: {height})",
                    )
            except Exception as retry_exc:  # noqa: BLE001 - classify lock vs terminal before deciding
                last_exc = retry_exc
                if not _is_sqlite_lock_error(retry_exc) or attempt == _BUSY_APPEND_RETRIES - 1:
                    break
        reason = f"Append block failed after {_BUSY_APPEND_RETRIES} lock retries: {last_exc}"
        logger.error("Append block failed for height %s: %s", height, last_exc)
        return self._make_import_result(accepted=False, height=height, block_hash=block_hash, reason=reason)

    def _handle_append_unique_conflict(
        self,
        session: Session,
        append_exc: Exception,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]],
        skip_state_root_validation: bool,
        height: int,
        block_hash: str,
        start: float,
    ) -> ImportResult:
        """Unique-violation classification after a rolled-back append.

        A unique violation here is not automatically a committed duplicate: a
        concurrent import can mark the height and roll back afterwards, and a
        tx-row collision surfaces the same error text. Roll back the dead
        transaction and check the committed view before deciding (Refs #712).
        """
        session.rollback()
        committed = session.exec(select(Block).where(Block.chain_id == self._chain_id).where(Block.height == height)).first()
        if committed is not None and committed.hash == block_hash:
            metrics_registry.increment("sync_blocks_duplicate_total")
            logger.info("Concurrent block import: height %s already inserted, treating as duplicate", height)
            return self._make_import_result(
                accepted=False,
                height=height,
                block_hash=block_hash,
                reason="Block already exists (concurrent import)",
            )
        if committed is None:
            # Phantom marker: the concurrent attempt that
            # claimed the height has rolled back. Retry the
            # append once — without this the block is
            # permanently reported as already present and
            # the importer stalls (Refs #712).
            try:
                result = self._append_block(session, block_data, transactions, skip_state_root_validation)
                duration = time.perf_counter() - start
                metrics_registry.observe("sync_import_duration_seconds", duration)
                block_processing_duration.observe(duration)
                return result
            except Exception as retry_exc:  # noqa: BLE001 - must-run rollback boundary on append retry
                session.rollback()
                logger.warning(
                    "Retry after phantom height marker failed for height %s: %s",
                    height,
                    retry_exc,
                )
                return self._make_import_result(
                    accepted=False,
                    height=height,
                    block_hash=block_hash,
                    reason=f"Import conflict (retryable): {retry_exc}",
                )
        logger.warning(
            "Unique violation importing height %s but committed block %s differs from %s",
            height,
            committed.hash,
            block_hash,
        )
        return self._make_import_result(
            accepted=False,
            height=height,
            block_hash=block_hash,
            reason=f"Divergent committed block at height {height}",
            diverged=True,
        )

    def _probe_peer_segment(
        self,
        session: Session,
        our_segment: list[Block],
        ancestor: Block | None,
        peer_blocks: list[dict[str, Any]],
    ) -> str:
        """#1322 tentative reorg: ``"ok"``, ``"apply_invalid"`` or ``"inconclusive"``.

        Reverts our segment through the delta journal and applies the peer's
        blocks in order inside the caller's session, then ALWAYS rolls back, so
        no durable trace remains. The process-global replay cache is saved and
        restored around the probe (no await inside, so nothing else applies a
        block meanwhile). A revert that cannot be done, or any unexpected
        error, is ``inconclusive`` -- never a veto.
        """
        st = get_state_transition()
        saved_nonces, saved_hashes = dict(st._processed_nonces), set(st._processed_tx_hashes)
        verdict = "inconclusive"
        try:
            if our_segment and self._blocks_provably_empty(session, list(our_segment)):
                # Same branch as the real reorg: an empty losing segment is
                # simply deleted (rolled back below), no journal revert.
                for old_block in our_segment:
                    for tx in session.exec(
                        select(ChainTransaction)
                        .where(ChainTransaction.chain_id == self._chain_id)
                        .where(ChainTransaction.block_height == old_block.height)
                    ).all():
                        session.delete(tx)
                    session.delete(old_block)
                session.flush()
            elif our_segment:
                if ancestor is None:
                    return "inconclusive"
                reverted = revert_losing_segment(
                    session, self._chain_id, list(our_segment), ancestor, self._blocks_provably_empty, reverted_accounts=set()
                )
                if reverted is None:
                    return "inconclusive"
                session.flush()
            for bd in peer_blocks:
                st.reset_processed_cache()
                try:
                    result = self._append_block(session, bd, bd.get("transactions"), _probe=True)
                except Exception:  # noqa: BLE001 - fork probe must classify ANY append failure as inconclusive
                    logger.exception("Fork probe errored at height %s", bd.get("height"))
                    return "inconclusive"
                if not result.accepted:
                    logger.warning("Fork probe: peer block %s refused on apply: %s", bd.get("height"), result.reason)
                    return "apply_invalid"
            verdict = "ok"
            return verdict
        finally:
            session.rollback()
            st._processed_nonces.clear()
            st._processed_nonces.update(saved_nonces)
            st._processed_tx_hashes.clear()
            st._processed_tx_hashes.update(saved_hashes)

    def _append_block(
        self,
        session: Session,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None = None,
        skip_state_root_validation: bool = False,
        _probe: bool = False,
        _state_transition: StateTransition | None = None,
        _probe_deadline: float | None = None,
    ) -> ImportResult:
        """Append a block to the chain tip.

        ``_probe`` (#1322) is reachable only from ``_probe_peer_segment`` and
        the #1940 F4 attestation post-state probe: the apply runs but the
        transaction is flushed, never committed, and no post-commit side
        effect (mempool eviction, shadow roots, counters, journal persist,
        rejection metrics) runs. ``_state_transition`` lets a probe supply a
        fresh, cache-isolated ``StateTransition``; every other caller keeps
        the process singleton. ``_probe_deadline`` (#2003) is an optional
        absolute ``time.monotonic()`` budget threaded from the attestation
        probe: every check below is gated on it being non-None, so
        production import is byte-identical, while a probe apply raises
        ``TimeoutError`` at coarse loop boundaries instead of holding the
        single-flight probe lock past its budget on pure-Python work the
        sqlite progress handler cannot preempt.

        Args:
            session: Database session
            block_data: Block data dictionary
            transactions: Optional list of transactions
            skip_state_root_validation: Skip state root validation (for bulk import)
        """
        apply_start = time.perf_counter()

        def _check_probe_deadline() -> None:
            # #2003 F1: probe-only deadline checks at coarse apply-loop
            # boundaries. ``None`` (every non-probe caller) makes this a
            # no-op so production import is unchanged.
            if _probe_deadline is not None and time.monotonic() > _probe_deadline:
                raise TimeoutError("post-state apply deadline")

        # #1940 F4: probe refusals are logged under their own prefix so a
        # speculative check never masquerades as a real import rejection.
        reject_tag = "[ATTEST-PROBE]" if _probe else "[SYNC]"
        block_hash = block_data["hash"]
        # Validation-only call sites (tests) may pass session=None — no journal
        # then; nothing reaches the DB anyway.
        journal = BlockDeltaJournal.attach(session, self._chain_id, int(block_data["height"])) if session is not None else None

        # Normalize transaction data from blocks-range (Transaction model dumps use
        # sender/recipient/value/tx_hash) to the signed transaction shape the state
        # transition expects (from/to/amount/fee/nonce/type/chain_id/signature/payload).
        transactions = self._normalize_import_txs(transactions, _check_probe_deadline)

        timestamp, tx_count = self._block_header_fields(block_data, transactions)

        block = self._build_import_block(block_data, timestamp, tx_count)

        # v0.25.6: when multi-validator consensus is configured, ensure the
        # proposer is an active validator scheduled for this height.  This wires
        # MultiValidatorPoA.validate_block into the import path on the follower.
        self._validate_proposer_schedule(session, block_data, block)

        # v0.25.7: determine the state-transition rule version for this block.
        # New blocks carry an explicit version in block_metadata; unversioned
        # legacy blocks fall back to the configured v2 activation height.
        block_version = get_block_version(block_data, block_data["height"])

        ctx = _AppendContext(
            session=session,
            block_data=block_data,
            block_hash=block_hash,
            block_version=block_version,
            timestamp=timestamp,
            tx_only_root=False,
            gate_height=0,
            probe=_probe,
            reject_tag=reject_tag,
            check_deadline=_check_probe_deadline,
            probe_deadline=_probe_deadline,
            journal=journal,
            skip_state_root_validation=skip_state_root_validation,
        )

        # #1940 F5 era gate + declared-lock scan, then the v20 signed
        # tx-list hash check — both reject before any state is mutated.
        rejected = self._prepare_tx_root_era(ctx, transactions) or self._verify_signed_tx_list_hash(ctx, transactions)
        if rejected is not None:
            return rejected

        if transactions:
            parallel_applied = self._apply_parallel_transactions(ctx, transactions, timestamp)
            if not parallel_applied:
                # Sequential path (fallback when parallel_tx_validation is off
                # or the conflict rate exceeds the threshold).
                self._apply_sequential_transactions(ctx, transactions, _state_transition)

        rejected = (
            self._check_lock_apply_evidence(ctx)
            or self._finalize_block_roots(ctx, block, transactions)
            or self._check_required_state_root(ctx)
            or self._verify_state_root(ctx)
            or self._verify_aux_root(ctx)
        )
        if rejected is not None:
            return rejected
        return self._commit_import(ctx, block, transactions, tx_count, apply_start)

    # ------------------------------------------------------------------
    # _append_block stage helpers — each preserves the original statement
    # order and side effects of the inline sequence they were extracted from.
    # ------------------------------------------------------------------

    @staticmethod
    def _block_header_fields(block_data: dict[str, Any], transactions: list[dict[str, Any]] | None) -> tuple[datetime, int]:
        """Parse the header timestamp and resolve ``tx_count`` for the Block row."""
        timestamp_str = block_data.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now(UTC)
        except (ValueError, TypeError):
            timestamp = datetime.now(UTC)
        tx_count = block_data.get("tx_count", 0)
        if transactions and get_block_version(block_data, block_data.get("height", 0)) < 20:
            tx_count = len(transactions)
        return timestamp, tx_count

    def _build_import_block(self, block_data: dict[str, Any], timestamp: datetime, tx_count: int) -> Block:
        """Build the Block object early so proposer-schedule validation can run
        before any state is mutated.  Only block_metadata is filled in after
        transactions have been applied.

        The state and bridge roots are carried over from the incoming block
        here rather than left unset, because the schedule check below verifies
        the proposer signature and both roots are part of the canonical header
        that was signed.  Leaving them empty made every multi-validator block
        fail that check: the follower rebuilt the header with empty roots, the
        signature recovered to an unrelated address, and the block was rejected
        with "signature does not match the declared proposer" even though it
        was correctly signed.  These fields are re-assigned below (state_root
        from the same source, bridge_state_root via _derive_bridge_state_root)
        once transactions have been applied, so nothing downstream changes.
        """
        return Block(
            chain_id=self._chain_id,
            height=block_data["height"],
            hash=block_data["hash"],
            parent_hash=block_data["parent_hash"],
            proposer=block_data.get("proposer", "unknown"),
            timestamp=timestamp,
            tx_count=tx_count,
            state_root=block_data.get("state_root"),
            bridge_state_root=block_data.get("bridge_state_root"),
            # Persist the signature this block was just validated against. Dropping
            # it made the check single-use: the block verified once on the way in and
            # was then stored unsigned, so this node could never re-serve proof of who
            # proposed it. One sync hop stripped authorship from the whole chain.
            signature=block_data.get("signature", ""),
        )

    def _normalize_import_txs(
        self,
        transactions: list[dict[str, Any]] | None,
        check_deadline: Callable[[], None],
    ) -> list[dict[str, Any]] | None:
        """Normalize raw block tx payloads to the signed shape the state
        transition expects (from/to/amount/fee/nonce/type/chain_id/signature/
        payload). Returns the input unchanged when there is nothing to do."""
        if not transactions:
            return transactions
        return [self._normalize_import_tx(raw_tx, check_deadline) for raw_tx in transactions]

    def _normalize_import_tx(self, raw_tx: dict[str, Any], check_deadline: Callable[[], None]) -> dict[str, Any]:
        """Normalize one raw block tx payload to the signed shape."""
        check_deadline()
        norm = self._hoist_signed_envelope(dict(raw_tx))
        self._fill_normalized_tx_defaults(norm)
        # Block broadcasts carry the proposer's pre-computed tx_hash —
        # it is authoritative: the same hash is what later transactions
        # (e.g. STAKE_RELEASE lock_tx_hashes) and local lookups resolve.
        # Recompute only as a fallback for legacy hashless payloads; the
        # recompute runs over normalized content and may differ from the
        # proposer's hash, so it must not overwrite a carried value.
        if not norm.get("tx_hash"):
            norm["tx_hash"] = compute_tx_hash(norm)
        return norm

    @staticmethod
    def _hoist_signed_envelope(norm: dict[str, Any]) -> dict[str, Any]:
        """Hoist a nested envelope: a peer serving a row stored before
        the fix can send a column dump with an empty top-level
        signature and the real signed envelope under "envelope".
        Without this the import stores and re-serves an unsigned tx
        — and a signature that exists anywhere must never end up ""."""
        nested = norm.get("envelope")
        if not norm.get("signature") and isinstance(nested, dict) and nested.get("signature"):
            kept_hash = norm.get("tx_hash")
            norm = dict(nested)
            if kept_hash:
                norm["tx_hash"] = kept_hash
        return norm

    def _fill_normalized_tx_defaults(self, norm: dict[str, Any]) -> None:
        """Alias stored-row field names onto the signed-tx shape and fill
        defaults the state transition requires."""
        if "from" not in norm and "sender" in norm:
            norm["from"] = norm["sender"]
        if "to" not in norm and "recipient" in norm:
            norm["to"] = norm["recipient"]
        if "amount" not in norm and "value" in norm:
            norm["amount"] = norm["value"]
        if "signature" not in norm:
            norm["signature"] = ""
        if "chain_id" not in norm:
            norm["chain_id"] = self._chain_id

    def _apply_parallel_transactions(
        self, ctx: _AppendContext, transactions: list[dict[str, Any]], timestamp: datetime
    ) -> bool:
        """Parallel transaction validation path (v0.6.1).

        When enabled and the conflict rate is low enough, transactions are
        partitioned into conflict-free groups and their state deltas are
        computed in parallel using pure functions (no DB access). Deltas are
        applied to an in-memory account_map in tx-index order (deterministic)
        so the resulting state root matches the sequential path exactly.

        Returns True when the parallel path applied the block; False falls
        through to the sequential path.
        """
        escrow_context, bridge_lock_context = self._parallel_tx_contexts(ctx, transactions)
        if not self._parallel_path_eligible(ctx, transactions, escrow_context, bridge_lock_context):
            return False
        # Build dependency graph from read/write sets.
        graph = DependencyGraph()
        tx_hash_to_data: dict[str, dict[str, Any]] = {}
        tx_hash_to_index: dict[str, int] = {}
        for idx, tx_data in enumerate(transactions):
            ctx.check_deadline()
            tx_hash = tx_data.get("tx_hash", "")
            tx_hash_to_data[tx_hash] = tx_data
            tx_hash_to_index[tx_hash] = idx
            read_set, write_set = extract_read_write_sets(tx_data)
            graph.add_transaction(tx_hash, read_set, write_set, index=idx)
        groups = graph.get_conflict_groups()
        # Fall back to sequential if too many transactions conflict.
        if not groups or graph.conflict_rate() > settings.conflict_threshold:
            return False
        # Bridge-signed txs (credits v5, locks v9) need the bridge release
        # authority for the signature gate — resolved once here.
        bridge_authority = self._parallel_bridge_authority(ctx, transactions)
        unique_addresses = self._parallel_unique_addresses(ctx, transactions, escrow_context)
        account_map = self._parallel_account_map(ctx, unique_addresses)
        existing_tx_hashes = self._parallel_existing_tx_hashes(ctx, transactions)
        all_deltas = self._parallel_execute_groups(
            ctx,
            groups,
            tx_hash_to_data,
            tx_hash_to_index,
            account_map,
            existing_tx_hashes,
            escrow_context,
            bridge_authority,
            bridge_lock_context,
            timestamp,
        )
        # Collect successful deltas in tx-index order (deterministic).
        successful_deltas = sorted(
            [d for d in all_deltas if d.success],
            key=lambda d: tx_hash_to_index.get(d.tx_hash, 0),
        )
        # Batch-write all deltas to the DB.
        apply_deltas_to_db(
            ctx.session,
            successful_deltas,
            self._chain_id,
            ctx.block_version,
            block_height=ctx.block_data["height"],
            block_time=timestamp,
        )
        self._persist_parallel_tx_rows(ctx, successful_deltas, all_deltas, tx_hash_to_data)
        return True

    def _parallel_tx_contexts(
        self, ctx: _AppendContext, transactions: list[dict[str, Any]]
    ) -> tuple[dict[str, dict[str, Any]] | None, dict[str, dict[str, Any]] | None]:
        """Prefetch contexts for the parallel path. Historical v1 blocks
        (pre state-transition fix) use the sequential path so the v1/v2
        account-creation gating is applied correctly. S-4: v2/v3 blocks may
        use the parallel path once per-job escrow lock metadata is prefetched.
        A release/refund with no resolvable lock returns None and the block
        stays sequential."""
        if not (settings.parallel_tx_validation and 2 <= ctx.block_version <= 8):
            return None, None
        escrow_context = build_escrow_context(ctx.session, self._chain_id, transactions, block_height=ctx.block_data["height"])
        bridge_lock_context: dict[str, dict[str, Any]] | None = None
        # v6: refunds need their named BRIDGE_LOCK records prefetched —
        # a batch with two refunds for one lock returns None and the
        # block goes sequential so the double-refund rule applies in order.
        if (
            ctx.block_version >= 6
            and escrow_context is not None
            and any(_determine_tx_type(tx) == "BRIDGE_REFUND" for tx in transactions)
        ):
            bridge_lock_context = build_bridge_lock_context(ctx.session, self._chain_id, transactions)
        return escrow_context, bridge_lock_context

    def _parallel_path_eligible(
        self,
        ctx: _AppendContext,
        transactions: list[dict[str, Any]],
        escrow_context: dict[str, dict[str, Any]] | None,
        bridge_lock_context: dict[str, dict[str, Any]] | None,
    ) -> bool:
        """Eligibility gate for the parallel apply path."""
        return (
            settings.parallel_tx_validation
            # FORK-GUARD-1: parallel import is disabled at v2-v8 — its
            # prefetch pre-creates every raw `to` and apply_deltas
            # creates recipients for non-MESSAGE deltas, so zero-value
            # fresh-recipient txs diverge from the proposer's serial
            # path (state-root mismatch; #432 pins GPU_MARKET->0x0 and
            # MESSAGE->fresh). The sequential path reproduces
            # pure_state_transition exactly; the divergence can only
            # re-enable after a recipient-rule guard lands.
            and _PARALLEL_V2V8_ENABLED
            and escrow_context is not None
            and (
                ctx.block_version < 6
                or bridge_lock_context is not None
                or not any(_determine_tx_type(tx) == "BRIDGE_REFUND" for tx in transactions)
            )
            and not any(_determine_tx_type(tx) in _SEQUENTIAL_ONLY_TX_TYPES for tx in transactions)
        )

    def _parallel_bridge_authority(self, ctx: _AppendContext, transactions: list[dict[str, Any]]) -> str | None:
        """Only queried when a v5+ block actually contains a bridge-signed tx."""
        if ctx.block_version >= 5 and any(_determine_tx_type(tx) in BRIDGE_AUTHORITY_TX_TYPES for tx in transactions):
            return _bridge_release_authority(ctx.session, self._chain_id, ctx.block_data["height"])
        return None

    def _parallel_unique_addresses(
        self,
        ctx: _AppendContext,
        transactions: list[dict[str, Any]],
        escrow_context: dict[str, dict[str, Any]] | None,
    ) -> set[str]:
        """Collect every account address the parallel deltas may touch,
        including per-escrow accounts for v3+ escrow locks."""
        unique_addresses: set[str] = set()
        for tx_data in transactions:
            ctx.check_deadline()
            raw_from = tx_data.get("from", "")
            raw_to = tx_data.get("to", "")
            sender_addr = _to_ait_address(raw_from)
            recipient_addr = _to_ait_address(raw_to)
            if sender_addr and raw_from not in {"bridge_release", "bridge_refund"}:
                unique_addresses.add(sender_addr)
            if recipient_addr and raw_to != "bridge_lock":
                unique_addresses.add(recipient_addr)
            tx_type = _determine_tx_type(tx_data)
            if tx_type in ("ESCROW_RELEASE", "ESCROW_REFUND"):
                payload = tx_data.get("payload", {}) or {}
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except (
                        RecursionError,
                        TypeError,
                        ValueError,
                    ):  # malformed payload JSON decodes to the empty/default branch
                        payload = {}
                job_id = payload.get("job_id", "")
                if job_id:
                    esc_ctx = (escrow_context or {}).get(job_id, {})
                    lock_version = esc_ctx.get("lock_version")
                    # Only pre-fetch the per-escrow account when the
                    # lock itself was a v3 per-escrow lock; v2 locks
                    # keep the generic sender->recipient transfer.
                    if lock_version is not None and lock_version >= 3:
                        unique_addresses.add(_escrow_address(job_id))
        return unique_addresses

    def _parallel_account_map(self, ctx: _AppendContext, unique_addresses: set[str]) -> dict[str, Account]:
        """Batch-fetch all sender/recipient/v3-escrow accounts into
        account_map. Pre-create any missing accounts with zero balance so that
        ``compute_state_delta`` does not fail on followers that have not yet
        replayed the blocks that created those accounts."""
        account_map: dict[str, Account] = {}
        if unique_addresses:
            existing_accounts = ctx.session.exec(
                select(Account).where(
                    Account.chain_id == self._chain_id,
                    Account.address.in_(unique_addresses),  # type: ignore[attr-defined]
                )
            ).all()
            account_map = {acc.address: acc for acc in existing_accounts}
        for addr in unique_addresses:
            if addr not in account_map:
                acct = Account(chain_id=self._chain_id, address=addr, balance=0, nonce=0)
                ctx.session.add(acct)
                ctx.session.flush()
                account_map[acct.address] = acct
        return account_map

    def _parallel_existing_tx_hashes(self, ctx: _AppendContext, transactions: list[dict[str, Any]]) -> set[str]:
        """Batch-fetch tx hashes already in the DB (duplicate detection)."""
        existing_tx_hashes: set[str] = set()
        all_tx_hashes = [tx_data.get("tx_hash", "") for tx_data in transactions]
        if all_tx_hashes:
            existing_rows = ctx.session.exec(
                select(ChainTransaction.tx_hash).where(
                    ChainTransaction.chain_id == self._chain_id,
                    ChainTransaction.tx_hash.in_(all_tx_hashes),  # type: ignore[attr-defined]
                    ChainTransaction.status != "rejected",
                )
            ).all()
            existing_tx_hashes = set(existing_rows)
        return existing_tx_hashes

    def _parallel_execute_groups(
        self,
        ctx: _AppendContext,
        groups: list[list[str]],
        tx_hash_to_data: dict[str, dict[str, Any]],
        tx_hash_to_index: dict[str, int],
        account_map: dict[str, Account],
        existing_tx_hashes: set[str],
        escrow_context: dict[str, dict[str, Any]] | None,
        bridge_authority: str | None,
        bridge_lock_context: dict[str, dict[str, Any]] | None,
        timestamp: datetime,
    ) -> list[StateDelta]:
        """Execute conflict groups sequentially; within each group, deltas are
        computed in parallel (group members are conflict-free)."""

        def _compute_delta(tx_data: dict[str, Any]) -> StateDelta:
            txh = tx_data.get("tx_hash", "")
            return compute_state_delta(
                account_map,
                tx_data,
                self._chain_id,
                txh,
                existing_tx_hashes,
                block_version=ctx.block_version,
                escrow_context=escrow_context,
                bridge_authority=bridge_authority,
                bridge_lock_context=bridge_lock_context,
                block_time=timestamp,
            )

        executor = ParallelExecutor(max_workers=settings.parallel_workers)
        all_deltas: list[StateDelta] = []
        try:
            for group in groups:
                ctx.check_deadline()
                # Update nonces from account_map before processing each group
                # (conflicting txs in later groups need updated nonces)
                for txh in group:
                    tx_data = tx_hash_to_data[txh]
                    sender = _to_ait_address(tx_data.get("from", ""))
                    sender_account = account_map.get(sender)
                    if sender_account:
                        # Bridge credits sign their nonce at
                        # issuance (v5) — the pseudo-sender
                        # account's nonce must not replace it.
                        if _determine_tx_type(tx_data) not in (
                            "BRIDGE_RELEASE",
                            "BRIDGE_REFUND",
                        ) and use_account_nonce_override(tx_data, ctx.block_version):
                            tx_data["nonce"] = sender_account.nonce
                        tx_data["value"] = tx_data.get("amount", 0)
                group_txs = [tx_hash_to_data[txh] for txh in group]
                group_results = executor.execute_groups([group_txs], _compute_delta, deadline=ctx.probe_deadline)[0]
                # Apply successful deltas to account_map in tx-index
                # order within the group (deterministic). Group members
                # are conflict-free so application order does not affect
                # the final state, but we keep index order for safety.
                group_results_sorted = sorted(group_results, key=lambda d: tx_hash_to_index.get(d.tx_hash, 0))
                for delta in group_results_sorted:
                    if delta.success:
                        apply_delta_to_map(account_map, delta, self._chain_id, ctx.block_version)
                        existing_tx_hashes.add(delta.tx_hash)
                all_deltas.extend(group_results_sorted)
        finally:
            executor.close()
        return all_deltas

    def _upsert_import_tx_row(self, session: Session, db_tx: ChainTransaction, tx_only_root: bool) -> ChainTransaction | None:
        """Insert the sealed tx row, or upgrade an existing pending/rejected
        writeback row to the sealed record rather than collide on the unique
        constraint (Refs #712 follow-up). Returns the pre-existing row when
        one was upgraded (None on fresh insert) so callers can keep the same
        identity-map lifetime the inline loop had."""
        existing_tx = session.exec(
            select(ChainTransaction)
            .where(ChainTransaction.chain_id == self._chain_id)
            .where(ChainTransaction.tx_hash == db_tx.tx_hash)
        ).first()
        if existing_tx is not None:
            existing_tx.block_height = db_tx.block_height
            existing_tx.status = db_tx.status
            if tx_only_root and db_tx.type == "BRIDGE_LOCK":
                # #1940 F5: the upgraded row must carry the exact
                # accepted body — semantic columns and envelope —
                # so proof reconstruction never replays a stale
                # pre-seal envelope. (Same semantic refresh as the
                # parallel-path upgrade.)
                existing_tx.sender = db_tx.sender
                existing_tx.recipient = db_tx.recipient
                existing_tx.value = db_tx.value
                existing_tx.fee = db_tx.fee
                existing_tx.nonce = db_tx.nonce
                existing_tx.type = db_tx.type
                existing_tx.payload = db_tx.payload
                existing_tx.envelope = db_tx.envelope
            session.add(existing_tx)
        else:
            session.add(db_tx)
        return existing_tx

    def _persist_parallel_tx_rows(
        self,
        ctx: _AppendContext,
        successful_deltas: list[StateDelta],
        all_deltas: list[StateDelta],
        tx_hash_to_data: dict[str, dict[str, Any]],
    ) -> None:
        """Create Transaction records for all successful parallel txs, log
        failures, and record tx-derived-era lock apply successes."""
        for delta in successful_deltas:
            tx_data = tx_hash_to_data.get(delta.tx_hash, {})
            db_tx = ChainTransaction(
                chain_id=self._chain_id,
                tx_hash=delta.tx_hash,
                block_height=ctx.block_data["height"],
                # Raw, not the canonicalised delta: these are signed (V23-65).
                sender=tx_data.get("from", delta.sender),
                recipient=tx_data.get("to", delta.recipient),
                payload=tx_data.get("payload", {}),
                envelope=dict(tx_data),
                type=delta.tx_type,
                value=tx_data.get("value", tx_data.get("amount", 0)),
                fee=tx_data.get("fee", 0),
                nonce=tx_data.get("nonce", 0),
                status="confirmed",
            )
            self._upsert_import_tx_row(ctx.session, db_tx, ctx.tx_only_root)
        # Log failed transactions.
        for delta in all_deltas:
            if not delta.success:
                logger.warning(ctx.reject_tag + " Failed to apply transaction %s: %s", delta.tx_hash, delta.error)
        if ctx.tx_only_root:
            # #1940 F5: actual apply success is the only evidence
            # a lock may contribute a trie leaf — persisted or
            # claimed status is never consulted.
            for delta in all_deltas:
                if delta.tx_hash in ctx.declared_lock_hashes and delta.success:
                    ctx.successful_lock_hashes.add(delta.tx_hash)

    def _commit_import(
        self,
        ctx: _AppendContext,
        block: Block,
        transactions: list[dict[str, Any]] | None,
        tx_count: int,
        apply_start: float,
    ) -> ImportResult:
        """Persist import rejections and the delta journal, commit the block,
        then run the post-commit side effects (shadow roots, mempool eviction,
        rejection counter, metrics, logging)."""
        block_data = ctx.block_data
        self._persist_import_rejections(ctx.session, block_data)
        if ctx.journal is not None and not ctx.probe:
            # #1940 F4: persist also advances the process-global prune
            # watermark — a speculative apply must not move it.
            ctx.journal.persist(ctx.session)
        if not ctx.probe:
            sync_import_phase_seconds.labels(phase="tx_apply").observe(time.perf_counter() - apply_start)
        phase_start = time.perf_counter()
        if ctx.probe:
            ctx.session.flush()
            return self._make_import_result(
                accepted=True, height=int(block_data["height"]), block_hash=ctx.block_hash, reason="probe"
            )
        ctx.session.commit()
        sync_import_phase_seconds.labels(phase="commit").observe(time.perf_counter() - phase_start)
        # V-3 shadow (flag-gated, compare-only — never affects the imported block).
        side_root_shadow.on_block_sealed(
            ctx.session, self._chain_id, int(block_data["height"]), block_version=ctx.block_version
        )
        if transactions:
            self._evict_included_from_mempool(transactions)
        self._evict_rejected_from_mempool(block_data)
        self._reset_rejection_counter(self._chain_id)
        metrics_registry.increment("sync_blocks_accepted_total")
        sync_blocks_imported.inc()
        block_height.set(int(block_data["height"]))
        metrics_registry.set_gauge("sync_chain_height", float(block_data["height"]))
        logger.info(
            "Imported block",
            extra={
                "height": block_data["height"],
                "hash": block_data["hash"],
                "proposer": block_data.get("proposer"),
                "tx_count": tx_count,
            },
        )
        return self._make_import_result(
            accepted=True, height=block_data["height"], block_hash=block_data["hash"], reason="Appended to chain"
        )

    def get_sync_status(self) -> dict[str, Any]:
        """Get current sync status and metrics."""
        with self._session_factory() as session:
            head = session.exec(
                select(Block.height, Block.hash, Block.proposer, Block.timestamp)
                .where(Block.chain_id == self._chain_id)
                .order_by(text("height DESC"))
                .limit(1)
            ).first()
            # COUNT queries — the previous .all() loads hydrated every Block
            # entity (plus selectin transactions/receipts) just to call len().
            total_blocks = session.exec(select(func.count()).select_from(Block).where(Block.chain_id == self._chain_id)).one()
            total_txs = session.exec(
                select(func.count()).select_from(ChainTransaction).where(ChainTransaction.chain_id == self._chain_id)
            ).one()
        return {
            "chain_id": self._chain_id,
            "head_height": head[0] if head else -1,
            "head_hash": head[1] if head else None,
            "head_proposer": head[2] if head else None,
            "head_timestamp": head[3].isoformat() if head else None,
            "total_blocks": total_blocks,
            "total_transactions": total_txs,
            "validate_signatures": self._validate_signatures,
            "trusted_proposers": list(self._validator.trusted_proposers),
            "max_reorg_depth": self._max_reorg_depth,
        }
