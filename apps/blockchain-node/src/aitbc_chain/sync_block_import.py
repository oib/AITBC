"""Single block import, append, and fork resolution."""

from __future__ import annotations

import json
import time
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
from .cross_chain import bridge_lock_guard, bridge_root_shadow
from .cross_chain.bridge_leaf import lock_leaf_value, unknown_lock_leaf
from .cross_chain.bridge_tx_root import (
    assert_lock_debit,
    build_tx_bridge_trie,
    canonical_lock_fields,
    effective_lock_debit,
    resolve_lock_type,
    tx_only_root_active,
)
from .state import side_root_shadow, state_root_utils
from .state.authoritative_reads import read_current_account
from .state.block_deltas import (
    BlockDeltaJournal,
    reconcile_orphaned_transactions,
    requeue_orphaned_transactions,
    revert_losing_segment,
)
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
from .consensus.multi_validator_poa import MultiValidatorPoA, proposer_round
from aitbc.crypto.signature_recovery import canonical_address
from .mempool import compute_tx_hash
from .sync_base import SyncBase
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


class BlockImportMixin(SyncBase):
    """Import a single block, append it, and resolve chain forks."""

    # Protocol base declares the attributes the concrete ChainSync sets.
    def _make_import_result(self, **kwargs: Any) -> ImportResult:
        """Create an ImportResult and record Prometheus sync failures if rejected."""
        result = ImportResult(**kwargs)
        if not result.accepted:
            reason = result.reason.split(":")[0].strip()[:40]
            sync_failures_total.labels(chain_id=self._chain_id, reason=reason).inc()
        return result

    def _get_multi_validator(self) -> MultiValidatorPoA | None:
        """Return a settings-only MultiValidatorPoA for schedule/role checks."""
        if not getattr(settings, "multi_validator_consensus_enabled", False):
            return None
        if not getattr(settings, "validator_set", ""):
            return None
        cache: MultiValidatorPoA | None = getattr(self, "_multi_validator_cache", None)
        if cache is not None:
            return cache
        multi_validator: MultiValidatorPoA | None
        try:
            multi_validator = MultiValidatorPoA.from_settings(self._chain_id)
        except Exception:
            logger.exception("Failed to build MultiValidatorPoA from settings for chain %s", self._chain_id)
            multi_validator = None
        self._multi_validator_cache = multi_validator
        return self._multi_validator_cache

    def _validate_proposer_schedule(
        self,
        session: Session,
        block_data: dict[str, Any],
        block: Block,
    ) -> None:
        """Verify the block proposer is an active validator scheduled for this height.

        Raises ValueError when the block should be rejected, allowing the caller
        to return an ImportResult without committing the block.
        """
        mv = self._get_multi_validator()
        if mv is None or not mv.validators:
            return

        # Only enforce the schedule for proposers that are actually in the
        # configured validator set.  Unknown proposers are still subject to the
        # signature and attestation checks in ProposerSignatureValidator.
        try:
            proposer_canonical = canonical_address(block.proposer)
        except (TypeError, ValueError):
            return
        if not any(canonical_address(v) == proposer_canonical for v in mv.validators):
            return

        parent_hash = block_data.get("parent_hash", "")
        parent_timestamp: Any = None
        if parent_hash and parent_hash != "0x00":
            parent_block = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == parent_hash)
            ).first()
            if parent_block:
                parent_timestamp = parent_block.timestamp

        if not mv.validate_block(block, block.proposer, parent_timestamp):
            raise ValueError(f"Proposer {block.proposer} is not the scheduled/authorized proposer for height {block.height}")

    def _derive_bridge_state_root(
        self,
        session: Session,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None,
        _probe: bool = False,
        *,
        tx_only_era: bool = False,
        successful_lock_hashes: set[str] | None = None,
        tx_height: int = 0,
    ) -> str:
        """Return the bridge event trie root for an imported block.

        Prefer the value carried in the P2P/bulk payload. If it is missing,
        rebuild it from the BRIDGE_LOCK transactions and CrossChainTransfer
        records so P2P-synced blocks do not store a NULL bridge_state_root.

        #1940 F5: in the tx-derived era the root is computed purely from the
        delivered (normalized) lock bodies through the shared contract —
        no CrossChainTransfer lookup, no synthesize-on-missing. Every lock
        body must carry actual apply-success evidence supplied by the caller;
        the carried root must be present and exactly equal or ValueError is
        raised so the caller rejects and rolls back the whole block.
        """
        if tx_only_era:
            return self._derive_bridge_state_root_tx_only(block_data, transactions, successful_lock_hashes, tx_height)
        return self._derive_bridge_state_root_legacy(session, block_data, transactions, _probe=_probe)

    def _derive_bridge_state_root_legacy(
        self,
        session: Session,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None,
        *,
        _probe: bool = False,
    ) -> str:
        """Legacy (pre-F5-era) bridge root: carried value or CCT-rebuild."""
        existing = block_data.get("bridge_state_root")
        if existing:
            if not _probe:
                # #1940 F4: the shadow root is observational — a speculative
                # probe apply must not run it.
                bridge_root_shadow.run_shadow_check(block_data, transactions, chain_id=self._chain_id, log=logger)
            return str(existing)
        from .base_models import CrossChainTransfer
        from .state.merkle_patricia_trie import MerklePatriciaTrie

        trie = MerklePatriciaTrie()
        lock_txs: list[dict[str, Any]] = []
        if transactions:
            for tx in transactions:
                tx_type = (tx.get("type") or (tx.get("payload") or {}).get("type", "")).upper()
                if tx_type == "BRIDGE_LOCK":
                    lock_txs.append(tx)
        if not lock_txs:
            return "0x" + trie.get_root().hex()
        # V-4 dry-run missing-data guard (flag-gated, logs/counts only —
        # the derived root below is computed exactly as before).
        block_height = int(block_data.get("height") or 0)
        if not _probe:
            bridge_lock_guard.run_guard_dryrun_dicts(lock_txs, height=block_height, chain_id=self._chain_id, log=logger)
        transfer_ids = [tx.get("tx_hash", "") for tx in lock_txs]
        records = session.exec(
            select(CrossChainTransfer).where(
                CrossChainTransfer.source_chain == self._chain_id,
                CrossChainTransfer.transfer_id.in_(transfer_ids),  # type: ignore[attr-defined]
            )
        ).all()
        record_map = {r.transfer_id: r for r in records}
        for tx in lock_txs:
            tx_hash = tx.get("tx_hash", "")
            record = record_map.get(tx_hash)
            if record is None:
                value = unknown_lock_leaf(tx_hash)
            else:
                value = lock_leaf_value(record.transfer_id, record.amount, record.target_chain, record.recipient, block_height)
            trie.put(tx_hash.encode(), value.encode())
        return "0x" + trie.get_root().hex()

    def _derive_bridge_state_root_tx_only(
        self,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None,
        successful_lock_hashes: set[str] | None,
        tx_height: int,
    ) -> str:
        """#1940 F5 tx-derived era: root from delivered lock bodies only."""
        bodies: list[dict[str, Any]] = []
        for tx in transactions or []:
            tx_any: Any = tx
            if not isinstance(tx_any, dict):
                continue
            body = dict(tx_any)
            body["tx_hash"] = str(tx.get("tx_hash") or "")
            bodies.append(body)
        lock_hashes = {str(b.get("tx_hash") or "") for b in bodies if _determine_tx_type(b) == "BRIDGE_LOCK"}
        lock_hashes.discard("")
        if lock_hashes:
            if successful_lock_hashes is None:
                raise ValueError("BRIDGE_LOCK present without actual-success evidence")
            missing = lock_hashes - set(successful_lock_hashes)
            if missing:
                raise ValueError(f"BRIDGE_LOCK without actual apply success: {sorted(missing)}")
        trie = build_tx_bridge_trie(bodies, self._chain_id, tx_height)
        computed = "0x" + trie.get_root().hex()
        carried = block_data.get("bridge_state_root")
        if not carried:
            raise ValueError("missing bridge_state_root in tx-derived era")
        if str(carried) != computed:
            raise ValueError(f"bridge_state_root mismatch: carried {carried} != computed {computed}")
        return str(carried)

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
        height = block_data.get("height", -1)
        block_hash = block_data.get("hash", "")
        if transactions is None:
            transactions = block_data.get("transactions") or []
        parent_hash = block_data.get("parent_hash", "")
        metrics_registry.increment("sync_blocks_received_total")
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
            if height == 0 and block_data.get("block_metadata"):
                is_valid, reason = self._validate_genesis_metadata(block_data, session)
                if not is_valid:
                    metrics_registry.increment("sync_state_root_rejected_total")
                    logger.error(
                        "Genesis block metadata validation failed: %s", reason, extra={"height": height, "hash": block_hash}
                    )
                    return self._make_import_result(accepted=False, height=height, block_hash=block_hash, reason=reason)
            phase_start = time.perf_counter()
            existing = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == block_hash)
            ).first()
            if existing:
                metrics_registry.increment("sync_blocks_duplicate_total")
                return self._make_import_result(
                    accepted=False, height=height, block_hash=block_hash, reason="Block already exists"
                )
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
                parent_exists = session.exec(
                    select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == parent_hash)
                ).first()
                parent_is_our_head = parent_exists is not None and our_head is not None and parent_exists.hash == our_head.hash
                sync_import_phase_seconds.labels(phase="block_lookup").observe(time.perf_counter() - phase_start)
                if (height == 0 and parent_hash == "0x00") or (height > 0 and parent_is_our_head):
                    try:
                        result = self._append_block(session, block_data, transactions, skip_state_root_validation)
                        duration = time.perf_counter() - start
                        metrics_registry.observe("sync_import_duration_seconds", duration)
                        block_processing_duration.observe(duration)
                        return result
                    except Exception as append_exc:
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
                        reason = str(append_exc).lower()
                        if "unique" in reason and "constraint" in reason:
                            # A unique violation here is not automatically a
                            # committed duplicate: a concurrent import can mark
                            # the height and roll back afterwards, and a
                            # tx-row collision surfaces the same error text.
                            # Roll back the dead transaction and check the
                            # committed view before deciding (Refs #712).
                            session.rollback()
                            committed = session.exec(
                                select(Block).where(Block.chain_id == self._chain_id).where(Block.height == height)
                            ).first()
                            if committed is not None and committed.hash == block_hash:
                                metrics_registry.increment("sync_blocks_duplicate_total")
                                logger.info(
                                    "Concurrent block import: height %s already inserted, treating as duplicate", height
                                )
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
                                except Exception as retry_exc:
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
                        logger.exception("Append block failed for height %s", height)
                        return self._make_import_result(
                            accepted=False,
                            height=height,
                            block_hash=block_hash,
                            reason=f"Append block failed: {append_exc}",
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
            if height <= our_height:
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
            if height > our_height + 1:
                metrics_registry.increment("sync_blocks_gap_total")
                return self._make_import_result(
                    accepted=False,
                    height=height,
                    block_hash=block_hash,
                    reason=f"Gap detected (our height: {our_height}, received: {height})",
                )
        return self._make_import_result(accepted=False, height=height, block_hash=block_hash, reason="Unhandled import case")

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
                except Exception:
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
        from datetime import UTC, datetime

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
        if transactions:
            normalized = []
            for raw_tx in transactions:
                _check_probe_deadline()
                norm = dict(raw_tx)
                # Hoist a nested envelope: a peer serving a row stored before
                # the fix can send a column dump with an empty top-level
                # signature and the real signed envelope under "envelope".
                # Without this the import stores and re-serves an unsigned tx
                # — and a signature that exists anywhere must never end up "".
                nested = norm.get("envelope")
                if not norm.get("signature") and isinstance(nested, dict) and nested.get("signature"):
                    kept_hash = norm.get("tx_hash")
                    norm = dict(nested)
                    if kept_hash:
                        norm["tx_hash"] = kept_hash
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
                # Block broadcasts carry the proposer's pre-computed tx_hash —
                # it is authoritative: the same hash is what later transactions
                # (e.g. STAKE_RELEASE lock_tx_hashes) and local lookups resolve.
                # Recompute only as a fallback for legacy hashless payloads; the
                # recompute runs over normalized content and may differ from the
                # proposer's hash, so it must not overwrite a carried value.
                if not norm.get("tx_hash"):
                    norm["tx_hash"] = compute_tx_hash(norm)
                normalized.append(norm)
            transactions = normalized

        timestamp_str = block_data.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now(UTC)
        except (ValueError, TypeError):
            timestamp = datetime.now(UTC)
        tx_count = block_data.get("tx_count", 0)
        if transactions and get_block_version(block_data, block_data.get("height", 0)) < 20:
            tx_count = len(transactions)

        # Build the Block object early so we can run proposer-schedule validation
        # before any state is mutated.  Only block_metadata is filled in after
        # transactions have been applied.
        #
        # The state and bridge roots are carried over from the incoming block
        # here rather than left unset, because the schedule check below verifies
        # the proposer signature and both roots are part of the canonical header
        # that was signed.  Leaving them empty made every multi-validator block
        # fail that check: the follower rebuilt the header with empty roots, the
        # signature recovered to an unrelated address, and the block was rejected
        # with "signature does not match the declared proposer" even though it
        # was correctly signed.  These fields are re-assigned below (state_root
        # from the same source, bridge_state_root via _derive_bridge_state_root)
        # once transactions have been applied, so nothing downstream changes.
        block = Block(
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

        # v0.25.6: when multi-validator consensus is configured, ensure the
        # proposer is an active validator scheduled for this height.  This wires
        # MultiValidatorPoA.validate_block into the import path on the follower.
        self._validate_proposer_schedule(session, block_data, block)

        # v0.25.7: determine the state-transition rule version for this block.
        # New blocks carry an explicit version in block_metadata; unversioned
        # legacy blocks fall back to the configured v2 activation height.
        block_version = get_block_version(block_data, block_data["height"])

        # #1940 F5: tx-derived bridge-root era — history-only gate resolved
        # at block_height - 1. The gate decision uses an int-convertible
        # header height; once active a non-strict-int/bool height refuses.
        tx_only_root = False
        declared_lock_hashes: set[str] = set()
        successful_lock_hashes: set[str] = set()
        _height_raw = block_data.get("height")
        try:
            _gate_height = int(_height_raw or 0)
        except (TypeError, ValueError):
            _gate_height = 0
        tx_only_root = tx_only_root_active(session, self._chain_id, _gate_height)
        if tx_only_root:
            if not (isinstance(_height_raw, int) and not isinstance(_height_raw, bool)):
                if not _probe:
                    metrics_registry.increment("sync_blocks_rejected_total")
                logger.warning(
                    "[SYNC] Block rejected: non-integer height %r in tx-derived bridge-root era",
                    _height_raw,
                )
                return self._make_import_result(
                    accepted=False,
                    height=block_data.get("height", 0),
                    block_hash=block_data.get("hash", ""),
                    reason="non_integer_height_tx_root_era",
                )
            if transactions:
                # Normalization already ran above, but it only adds equal
                # amount/value aliases and hoists the signed envelope — it
                # can neither create nor hide an alias conflict, so the
                # authoritative signed body still reaches these checks.
                # Stored-row type disagreements involving BRIDGE_LOCK,
                # canonical signed fields, and the outer amount/value debit
                # alias all reject the whole sealed block here — it is
                # never partially applied.
                _tx_hashes = [str(tx.get("tx_hash") or "") for tx in transactions if isinstance(tx, dict)]
                _stored_types: dict[str, str] = {}
                if _tx_hashes:
                    for _h, _t in session.exec(
                        select(ChainTransaction.tx_hash, ChainTransaction.type).where(
                            ChainTransaction.chain_id == self._chain_id,
                            ChainTransaction.tx_hash.in_(_tx_hashes),  # type: ignore[attr-defined]
                        )
                    ).all():
                        _stored_types[_h] = _t
                for _tx_raw in transactions:
                    _tx: Any = _tx_raw
                    if not isinstance(_tx, dict):
                        continue
                    _tx_hash = str(_tx.get("tx_hash") or "")
                    try:
                        _eff = resolve_lock_type(_tx, _stored_types.get(_tx_hash))
                        if _eff == "BRIDGE_LOCK":
                            if _tx_hash in declared_lock_hashes:
                                raise ValueError(f"duplicate BRIDGE_LOCK tx_hash {_tx_hash}")
                            declared_lock_hashes.add(_tx_hash)
                            _fields = canonical_lock_fields(
                                {**_tx, "tx_hash": _tx_hash}, _tx_hash, self._chain_id, _gate_height
                            )
                            assert_lock_debit(_fields, effective_lock_debit(_tx))
                    except (TypeError, ValueError) as _e:
                        if not _probe:
                            metrics_registry.increment("sync_blocks_rejected_total")
                        logger.warning(
                            "[SYNC] Block rejected: bridge lock contract violation at height %s: %s",
                            block_data.get("height"),
                            _e,
                        )
                        return self._make_import_result(
                            accepted=False,
                            height=block_data.get("height", 0),
                            block_hash=block_data.get("hash", ""),
                            reason=f"bridge_lock_contract_violation: {_e}",
                        )

        if block_version >= 20 and block_data.get("hash"):
            # v20+: the signed block hash must reproduce over the delivered tx
            # list — a relayed list that does not hash to it is rejected (#1064).
            from .consensus.block_hash import compute_block_hash

            delivered_hashes = [str(tx.get("tx_hash", "")) for tx in transactions or []]
            recomputed = compute_block_hash(
                self._chain_id,
                int(block_data["height"]),
                str(block_data.get("parent_hash", "")),
                timestamp_str,
                delivered_hashes,
                str(block_data.get("proposer", "")),
                str(block_data.get("state_root") or ""),
                str(block_data.get("bridge_state_root") or ""),
                str(block_data.get("aux_state_root") or ""),
            )
            if recomputed != str(block_data["hash"]):
                if not _probe:
                    metrics_registry.increment("sync_blocks_rejected_total")
                logger.warning(
                    ("[ATTEST-PROBE] " if _probe else "")
                    + "Block rejected at v20+: delivered tx list does not hash to the signed block hash at height %s",
                    block_data["height"],
                )
                return self._make_import_result(
                    accepted=False,
                    height=block_data["height"],
                    block_hash=block_data.get("hash", ""),
                    reason="tx_list_hash_mismatch",
                )

        if transactions:
            # Parallel transaction validation path (v0.6.1).
            # When enabled and the conflict rate is low enough, transactions are
            # partitioned into conflict-free groups and their state deltas are
            # computed in parallel using pure functions (no DB access). Deltas are
            # applied to an in-memory account_map in tx-index order (deterministic)
            # so the resulting state root matches the sequential path exactly.
            parallel_applied = False
            # Historical v1 blocks (pre state-transition fix) use the sequential
            # path so the v1/v2 account-creation gating is applied correctly.
            # S-4: v2/v3 blocks may use the parallel path once per-job escrow
            # lock metadata is prefetched. A release/refund with no resolvable
            # lock returns None and the block stays sequential.
            escrow_context: dict[str, dict[str, Any]] | None = None
            bridge_lock_context: dict[str, dict[str, Any]] | None = None
            if settings.parallel_tx_validation and 2 <= block_version <= 8:
                escrow_context = build_escrow_context(session, self._chain_id, transactions, block_height=block_data["height"])
                # v6: refunds need their named BRIDGE_LOCK records prefetched —
                # a batch with two refunds for one lock returns None and the
                # block goes sequential so the double-refund rule applies in order.
                if (
                    block_version >= 6
                    and escrow_context is not None
                    and any(_determine_tx_type(tx) == "BRIDGE_REFUND" for tx in transactions)
                ):
                    bridge_lock_context = build_bridge_lock_context(session, self._chain_id, transactions)
            if (
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
                    block_version < 6
                    or bridge_lock_context is not None
                    or not any(_determine_tx_type(tx) == "BRIDGE_REFUND" for tx in transactions)
                )
                and not any(_determine_tx_type(tx) in _SEQUENTIAL_ONLY_TX_TYPES for tx in transactions)
            ):
                # Build dependency graph from read/write sets.
                graph = DependencyGraph()
                tx_hash_to_data: dict[str, dict[str, Any]] = {}
                tx_hash_to_index: dict[str, int] = {}
                for idx, tx_data in enumerate(transactions):
                    _check_probe_deadline()
                    tx_hash = tx_data.get("tx_hash", "")
                    tx_hash_to_data[tx_hash] = tx_data
                    tx_hash_to_index[tx_hash] = idx
                    read_set, write_set = extract_read_write_sets(tx_data)
                    graph.add_transaction(tx_hash, read_set, write_set, index=idx)
                groups = graph.get_conflict_groups()
                # Fall back to sequential if too many transactions conflict.
                if groups and graph.conflict_rate() <= settings.conflict_threshold:
                    # Bridge-signed txs (credits v5, locks v9) need the bridge
                    # release authority for the signature gate — resolve the
                    # on-chain parameter once so the pure path applies the same
                    # rule as the sequential one. Only queried when a v5+ block
                    # actually contains a bridge-signed tx.
                    bridge_authority: str | None = None
                    if block_version >= 5 and any(_determine_tx_type(tx) in BRIDGE_AUTHORITY_TX_TYPES for tx in transactions):
                        bridge_authority = _bridge_release_authority(session, self._chain_id, block_data["height"])
                    # Batch-fetch all sender/recipient/v3-escrow accounts into
                    # account_map. Pre-create any missing accounts with zero
                    # balance so that `compute_state_delta` does not fail on
                    # followers that have not yet replayed the blocks that created
                    # those accounts.
                    unique_addresses: set[str] = set()
                    for tx_data in transactions:
                        _check_probe_deadline()
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
                                ctx = (escrow_context or {}).get(job_id, {})
                                lock_version = ctx.get("lock_version")
                                # Only pre-fetch the per-escrow account when the
                                # lock itself was a v3 per-escrow lock; v2 locks
                                # keep the generic sender->recipient transfer.
                                if lock_version is not None and lock_version >= 3:
                                    unique_addresses.add(_escrow_address(job_id))
                    account_map: dict[str, Account] = {}
                    if unique_addresses:
                        existing_accounts = session.exec(
                            select(Account).where(
                                Account.chain_id == self._chain_id,
                                Account.address.in_(unique_addresses),  # type: ignore[attr-defined]
                            )
                        ).all()
                        account_map = {acc.address: acc for acc in existing_accounts}
                    for addr in unique_addresses:
                        if addr not in account_map:
                            acct = Account(chain_id=self._chain_id, address=addr, balance=0, nonce=0)
                            session.add(acct)
                            session.flush()
                            account_map[acct.address] = acct
                    # Batch-fetch tx hashes already in the DB (duplicate detection).
                    existing_tx_hashes: set[str] = set()
                    all_tx_hashes = [tx_data.get("tx_hash", "") for tx_data in transactions]
                    if all_tx_hashes:
                        existing_rows = session.exec(
                            select(ChainTransaction.tx_hash).where(
                                ChainTransaction.chain_id == self._chain_id,
                                ChainTransaction.tx_hash.in_(all_tx_hashes),  # type: ignore[attr-defined]
                                ChainTransaction.status != "rejected",
                            )
                        ).all()
                        existing_tx_hashes = set(existing_rows)
                    # Execute groups sequentially; within each group, deltas are
                    # computed in parallel (group members are conflict-free).
                    executor = ParallelExecutor(max_workers=settings.parallel_workers)
                    all_deltas: list[StateDelta] = []
                    try:

                        def _compute_delta(tx_data: dict[str, Any]) -> StateDelta:
                            txh = tx_data.get("tx_hash", "")
                            return compute_state_delta(
                                account_map,
                                tx_data,
                                self._chain_id,
                                txh,
                                existing_tx_hashes,
                                block_version=block_version,
                                escrow_context=escrow_context,
                                bridge_authority=bridge_authority,
                                bridge_lock_context=bridge_lock_context,
                                block_time=timestamp,
                            )

                        for group in groups:
                            _check_probe_deadline()
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
                                    ) and use_account_nonce_override(tx_data, block_version):
                                        tx_data["nonce"] = sender_account.nonce
                                    tx_data["value"] = tx_data.get("amount", 0)
                            group_txs = [tx_hash_to_data[txh] for txh in group]
                            group_results = executor.execute_groups([group_txs], _compute_delta, deadline=_probe_deadline)[0]
                            # Apply successful deltas to account_map in tx-index
                            # order within the group (deterministic). Group members
                            # are conflict-free so application order does not affect
                            # the final state, but we keep index order for safety.
                            group_results_sorted = sorted(group_results, key=lambda d: tx_hash_to_index.get(d.tx_hash, 0))
                            for delta in group_results_sorted:
                                if delta.success:
                                    apply_delta_to_map(account_map, delta, self._chain_id, block_version)
                                    existing_tx_hashes.add(delta.tx_hash)
                            all_deltas.extend(group_results_sorted)
                    finally:
                        executor.close()
                    # Collect successful deltas in tx-index order (deterministic).
                    successful_deltas = sorted(
                        [d for d in all_deltas if d.success],
                        key=lambda d: tx_hash_to_index.get(d.tx_hash, 0),
                    )
                    # Batch-write all deltas to the DB.
                    apply_deltas_to_db(
                        session,
                        successful_deltas,
                        self._chain_id,
                        block_version,
                        block_height=block_data["height"],
                        block_time=timestamp,
                    )
                    # Create Transaction records for all successful txs.
                    for delta in successful_deltas:
                        tx_data = tx_hash_to_data.get(delta.tx_hash, {})
                        db_tx = ChainTransaction(
                            chain_id=self._chain_id,
                            tx_hash=delta.tx_hash,
                            block_height=block_data["height"],
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
                        existing_tx = session.exec(
                            select(ChainTransaction)
                            .where(ChainTransaction.chain_id == self._chain_id)
                            .where(ChainTransaction.tx_hash == db_tx.tx_hash)
                        ).first()
                        if existing_tx is not None:
                            # A pending/rejected writeback already owns the row —
                            # upgrade it to the sealed record rather than collide
                            # on the unique constraint (Refs #712 follow-up).
                            existing_tx.block_height = db_tx.block_height
                            existing_tx.status = db_tx.status
                            if tx_only_root and db_tx.type == "BRIDGE_LOCK":
                                # #1940 F5: same semantic refresh as the
                                # sequential upgrade — stale envelopes must
                                # not diverge the proof builder.
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
                    # Log failed transactions.
                    for delta in all_deltas:
                        if not delta.success:
                            logger.warning(reject_tag + " Failed to apply transaction %s: %s", delta.tx_hash, delta.error)
                    if tx_only_root:
                        # #1940 F5: actual apply success is the only evidence
                        # a lock may contribute a trie leaf — persisted or
                        # claimed status is never consulted.
                        for delta in all_deltas:
                            if delta.tx_hash in declared_lock_hashes and delta.success:
                                successful_lock_hashes.add(delta.tx_hash)
                    parallel_applied = True
            if not parallel_applied:
                # Sequential path (fallback when parallel_tx_validation is off
                # or the conflict rate exceeds the threshold).
                for tx_data in transactions:
                    _check_probe_deadline()
                    sender_addr = _to_ait_address(tx_data.get("from", ""))
                    recipient_addr = _to_ait_address(tx_data.get("to", ""))
                    int(tx_data.get("amount", 0) or 0)
                    int(tx_data.get("fee", 0) or 0)
                    tx_hash = tx_data.get("tx_hash", "")
                    raw_from = tx_data.get("from", "")
                    if raw_from not in {"bridge_release", "bridge_refund"}:
                        sender_acct = session.get(Account, (self._chain_id, sender_addr))
                        # v22 (CONSENSUS-STATE-001, #1169): no pre-apply sender
                        # insert — a tx that validate/apply rejects must leave
                        # zero mutation, and a phantom account row is committed
                        # state. apply_transaction creates accounts only on its
                        # success paths; a same-block-earlier credit is already
                        # visible via session.get above.
                        if sender_acct is None and 2 <= block_version < 22:
                            sender_acct = Account(chain_id=self._chain_id, address=sender_addr, balance=0, nonce=0)
                            session.add(sender_acct)
                            session.flush()
                    # Do not create the recipient account here, matching the
                    # proposer (poa.py): apply_transaction ensures the recipient
                    # itself on the paths that credit it. Pre-creating left a
                    # phantom row for zero-value types (GPU_MARKET offers carry
                    # to=0x0000…0000), so the importer computed a state root the
                    # committed header never had — every validator rejected the
                    # block (bc-2 fork at height 1462).
                    # Bump tx_data nonce/value to the live account state before
                    # applying, mirroring the block producer.  Blocks may contain
                    # multiple same-sender transactions that share the stored nonce
                    # (e.g. parallel-validated GPU_MARKET offers); the follower
                    # must apply them with the current account nonce, not the stored
                    # one, or the second transaction fails and the state root diverges.
                    if raw_from not in {"bridge_release", "bridge_refund"} and use_account_nonce_override(
                        tx_data, block_version
                    ):
                        if block_version >= 24:
                            # #1314 V5 mirror: authoritative scalar read — the
                            # identity-mapped sender_acct can be stale after
                            # raw-SQL writes earlier in this block.
                            _, auth_nonce, auth_exists = read_current_account(session, self._chain_id, sender_addr)
                            if auth_exists:
                                tx_data["nonce"] = auth_nonce
                        elif sender_acct is not None:
                            tx_data["nonce"] = sender_acct.nonce
                    if block_version >= 20:
                        # v20+: value is unsigned — the signed amount always
                        # wins, exactly as the proposer does (#1066).
                        if "amount" in tx_data:
                            tx_data["value"] = tx_data["amount"]
                    elif "value" not in tx_data and "amount" in tx_data:
                        tx_data["value"] = tx_data["amount"]
                    state_transition = _state_transition if _state_transition is not None else get_state_transition()
                    success, error_msg = state_transition.apply_transaction_guarded(
                        session,
                        self._chain_id,
                        tx_data,
                        tx_hash,
                        block_version=block_version,
                        block_height=block_data["height"],
                        # v18: the sealed header timestamp drives the
                        # deterministic apply paths — identical to the
                        # ``timestamp`` the proposer threaded through.
                        block_time=timestamp,
                    )
                    if not success:
                        logger.warning(reject_tag + " Failed to apply transaction %s: %s", tx_hash, error_msg)
                    if tx_only_root and tx_hash in declared_lock_hashes and success:
                        # #1940 F5: only an actually-applied lock may be
                        # certified by the tx-derived root — below v20 the
                        # persisted "confirmed" status proves nothing.
                        successful_lock_hashes.add(tx_hash)
                    tx_type = tx_data.get("type", "TRANSFER")
                    if tx_type:
                        tx_type = tx_type.upper()
                    else:
                        tx_type = "TRANSFER"
                    if tx_only_root and _determine_tx_type(tx_data) == "BRIDGE_LOCK":
                        # #1940 F5: payload-typed locks store their real
                        # resolved type, matching the producer.
                        tx_type = "BRIDGE_LOCK"
                    db_tx = ChainTransaction(
                        chain_id=self._chain_id,
                        tx_hash=tx_hash,
                        block_height=block_data["height"],
                        # Raw, not the canonicalised locals: these are signed (V23-65).
                        sender=tx_data.get("from", sender_addr),
                        recipient=tx_data.get("to", recipient_addr),
                        payload=tx_data.get("payload", {}),
                        envelope=dict(tx_data),
                        type=tx_type,
                        value=tx_data.get("value", tx_data.get("amount", 0)),
                        fee=tx_data.get("fee", 0),
                        nonce=tx_data.get("nonce", 0),
                        status="confirmed" if success or block_version < 20 else "failed",
                    )
                    existing_tx = session.exec(
                        select(ChainTransaction)
                        .where(ChainTransaction.chain_id == self._chain_id)
                        .where(ChainTransaction.tx_hash == db_tx.tx_hash)
                    ).first()
                    if existing_tx is not None:
                        # A pending/rejected writeback already owns the row —
                        # upgrade it to the sealed record rather than collide
                        # on the unique constraint (Refs #712 follow-up).
                        existing_tx.block_height = db_tx.block_height
                        existing_tx.status = db_tx.status
                        if tx_only_root and db_tx.type == "BRIDGE_LOCK":
                            # #1940 F5: the upgraded row must carry the exact
                            # accepted body — semantic columns and envelope —
                            # so proof reconstruction never replays a stale
                            # pre-seal envelope.
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
                    if block_version >= 24:
                        # #1314 R2 importer mirror: prod sessions run
                        # autoflush=False, so without this flush the sealed
                        # row stays pending and later same-block applies
                        # (escrow-lock/refund Transaction-row reads) cannot
                        # see it — diverging from the proposer's in-loop
                        # flush schedule.
                        session.flush()

        # Fill in the state/bridge roots and metadata now that transactions have
        # been applied, then persist the block.  This keeps the schedule check
        # above from touching any state.
        if tx_only_root and declared_lock_hashes != successful_lock_hashes:
            # #1940 F5: every declared/effectively-typed lock must have
            # actually applied — a failed, skipped or hidden lock rejects
            # the whole block and rolls back every write above.
            _failed = sorted(declared_lock_hashes - successful_lock_hashes)
            if not _probe:
                metrics_registry.increment("sync_blocks_rejected_total")
            session.rollback()
            if not _probe:
                self._track_rejection(self._chain_id)
            logger.warning(
                "[SYNC] Block rejected: BRIDGE_LOCK without actual apply success at height %s: %s",
                block_data.get("height"),
                _failed,
            )
            return self._make_import_result(
                accepted=False,
                height=block_data.get("height", 0),
                block_hash=block_hash,
                reason=f"bridge_lock_apply_failed: {_failed}",
            )
        block.state_root = block_data.get("state_root")
        if tx_only_root:
            try:
                block.bridge_state_root = self._derive_bridge_state_root(
                    session,
                    block_data,
                    transactions,
                    tx_only_era=True,
                    successful_lock_hashes=successful_lock_hashes,
                    tx_height=_gate_height,
                )
            except ValueError as _bridge_err:
                # #1940 F5: missing/mismatched carried root or missing
                # success evidence — reject and roll back, never synthesize.
                if not _probe:
                    metrics_registry.increment("sync_blocks_rejected_total")
                session.rollback()
                if not _probe:
                    self._track_rejection(self._chain_id)
                logger.warning(
                    "[SYNC] Block rejected: tx-derived bridge root violation at height %s: %s",
                    block_data.get("height"),
                    _bridge_err,
                )
                return self._make_import_result(
                    accepted=False,
                    height=block_data.get("height", 0),
                    block_hash=block_hash,
                    reason=f"bridge_root_violation: {_bridge_err}",
                )
        else:
            # Gate-off: the original three-argument derive call, outside the
            # new-era ValueError catch — legacy behavior byte-identical.
            block.bridge_state_root = self._derive_bridge_state_root(session, block_data, transactions, _probe=_probe)
        # v14 (V-3): the header's committed side-table root. Stored only at
        # v14+ — below the activation the field does not exist and any value a
        # peer supplies is ignored, so replayed pre-v14 blocks keep NULL.
        block.aux_state_root = (
            str(block_data["aux_state_root"]) if block_version >= 14 and block_data.get("aux_state_root") else None
        )
        block.block_metadata = block_data.get("block_metadata")
        session.add(block)

        require_root_height = getattr(settings, "sync_require_state_root_height", None)
        if (
            require_root_height is not None
            and not block_data.get("state_root")
            and not skip_state_root_validation
            and int(block_data["height"]) >= int(require_root_height)
        ):
            # #1325 (e): vote-only attestation leans on this comparison, so a
            # block that omits its root cannot be allowed to skip it.
            if not _probe:
                metrics_registry.increment("sync_state_root_missing_rejected_total")
            session.rollback()
            self._track_rejection(self._chain_id)
            logger.error(
                reject_tag + " Missing state root at height %s (required from %s) - BLOCK REJECTED",
                block_data["height"],
                require_root_height,
            )
            return self._make_import_result(
                accepted=False,
                height=block_data["height"],
                block_hash=block_hash,
                reason="Missing state root",
            )

        _check_probe_deadline()
        if block_data.get("state_root") and (not skip_state_root_validation):
            session.flush()
            # Compute state root from the full account state. The previous
            # "incremental" approach created a fresh trie per call but only
            # populated it with accounts touched in this block — producing an
            # empty trie (root=0x00..00) for blocks with no transactions and a
            # wrong root for blocks with transactions. Since the trie is not
            # persisted across blocks, a full recompute is the only correct option.
            computed_hex = state_root_utils.compute_state_root_full(session, self._chain_id, deadline=_probe_deadline)
            computed_root = bytes.fromhex(computed_hex.replace("0x", "")) if computed_hex else None
            try:
                expected_root = bytes.fromhex(str(block_data.get("state_root")).replace("0x", ""))
            except ValueError:
                expected_root = None
            if expected_root is None or len(expected_root) != 32:
                if not _probe:
                    metrics_registry.increment("sync_state_root_rejected_total")
                session.rollback()
                self._track_rejection(self._chain_id)
                logger.error(
                    reject_tag + " Invalid state root at height %s: %s - BLOCK REJECTED",
                    block_data["height"],
                    block_data.get("state_root"),
                )

                return self._make_import_result(
                    accepted=False,
                    height=block_data["height"],
                    block_hash=block_hash,
                    reason=f"Invalid state root: {block_data.get('state_root')}",
                )
            elif computed_root != expected_root:
                if not _probe:
                    metrics_registry.increment("sync_state_root_rejected_total")
                session.rollback()
                self._track_rejection(self._chain_id)
                # Two very different faults produced this same message before, and only
                # one of them is about the incoming block. If our own account state has
                # drifted away from our head, re-applying the block on top of state that
                # already contains it can never reproduce the expected root, so the node
                # retries forever. hub2 emitted 866 identical "BLOCK REJECTED" lines over
                # six hours pointing at block 1300 while the actual fault was a single
                # local account row one transaction ahead of its own head.
                divergence = self._describe_local_state_divergence(session, block_data["height"] - 1)
                if divergence:
                    if not _probe:
                        metrics_registry.increment("sync_local_state_divergence_total")
                    logger.error(
                        reject_tag + " Local state diverged from our own head %s: %s. "
                        "Block %s cannot be imported until local state is repaired; "
                        "retrying will not help - BLOCK REJECTED",
                        block_data["height"] - 1,
                        divergence,
                        block_data["height"],
                    )
                    return self._make_import_result(
                        accepted=False,
                        height=block_data["height"],
                        block_hash=block_hash,
                        reason=(f"Local state diverged from head {block_data['height'] - 1}: {divergence}"),
                        diverged=True,
                    )
                logger.error(
                    reject_tag + " State root mismatch at height %s: expected %s, computed %s - BLOCK REJECTED",
                    block_data["height"],
                    expected_root.hex(),
                    computed_root.hex(),  # type: ignore[union-attr]
                )

                return self._make_import_result(
                    accepted=False,
                    height=block_data["height"],
                    block_hash=block_hash,
                    reason=f"State root mismatch: expected {expected_root.hex()}, computed {computed_root.hex()}",  # type: ignore[union-attr]
                )
        # v14 (V-3): the block commits to the 13-table side-table root over the
        # committed set after this block's transactions applied. Recompute it
        # against local state — a mismatch means the proposer's committed state
        # and ours disagree in a way the account-level state_root does not see,
        # so the block is rejected rather than sealing a divergence.
        if (not skip_state_root_validation) and block_version >= 14:
            session.flush()
            computed_aux = side_root_shadow.committed_fingerprint(
                session.connection().connection, block_version, deadline=_probe_deadline
            )["fingerprint"]
            recorded_aux = block_data.get("aux_state_root")
            if not recorded_aux or computed_aux != str(recorded_aux):
                if not side_root_shadow.aux_check_verifiable(block_version):
                    # The era set includes tables whose only writers were
                    # node-local RPC/aux paths (stake, edge_node_registration):
                    # the sealed digest mixed the sealer's own local rows and
                    # cannot be reproduced here — a mismatch cannot distinguish
                    # real divergence from legitimate local rows, so the check
                    # runs compare-only for these eras rather than stalling
                    # replay of history no node can re-verify.
                    if not _probe:
                        metrics_registry.increment("sync_aux_root_unverifiable_total")
                    logger.warning(
                        reject_tag + " Aux state root mismatch at height %s on an "
                        "unverifiable era (v%s): expected %s, computed %s - "
                        "compare-only, block not rejected",
                        block_data["height"],
                        block_version,
                        recorded_aux,
                        computed_aux,
                    )
                else:
                    if not _probe:
                        metrics_registry.increment("sync_aux_root_rejected_total")
                    session.rollback()
                    self._track_rejection(self._chain_id)
                    logger.error(
                        reject_tag + " Aux state root mismatch at height %s: expected %s, computed %s - BLOCK REJECTED",
                        block_data["height"],
                        recorded_aux,
                        computed_aux,
                    )
                    return self._make_import_result(
                        accepted=False,
                        height=block_data["height"],
                        block_hash=block_hash,
                        reason=f"Aux state root mismatch: expected {recorded_aux}, computed {computed_aux}",
                    )
        self._persist_import_rejections(session, block_data)
        if journal is not None and not _probe:
            # #1940 F4: persist also advances the process-global prune
            # watermark — a speculative apply must not move it.
            journal.persist(session)
        if not _probe:
            sync_import_phase_seconds.labels(phase="tx_apply").observe(time.perf_counter() - apply_start)
        phase_start = time.perf_counter()
        if _probe:
            session.flush()
            return self._make_import_result(
                accepted=True, height=int(block_data["height"]), block_hash=block_hash, reason="probe"
            )
        session.commit()
        sync_import_phase_seconds.labels(phase="commit").observe(time.perf_counter() - phase_start)
        # V-3 shadow (flag-gated, compare-only — never affects the imported block).
        side_root_shadow.on_block_sealed(session, self._chain_id, int(block_data["height"]), block_version=block_version)
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

    def _evict_included_from_mempool(self, transactions: list[dict[str, Any]]) -> None:
        """Drop just-included transactions from the local mempool.

        Only proposers drain the mempool (poa.py); on followers a confirmed
        transaction would sit there until size-cap eviction, evicting real
        pending txs ahead of dead ones. ``tx_hash`` is always populated by the
        normalization loop above. Best-effort: a mempool failure must never
        turn into a block-import failure.
        """
        try:
            from .mempool import get_mempool, _tx_slot_key

            mempool = get_mempool()
            evicted = 0
            for tx in transactions:
                tx_hash = tx.get("tx_hash")
                if tx_hash and mempool.remove(tx_hash, self._chain_id):
                    evicted += 1
                # A sealed (sender, nonce) kills any different-hash pending
                # row on that slot — release it now instead of refusing
                # resubmits for the full TTL (Refs #717). Only a sealed tx
                # that itself held a slot can consume one: unsigned
                # protocol-internal txs carry a placeholder nonce and must
                # not trigger the sweep (#796).
                sender = tx.get("from") or tx.get("sender")
                nonce = tx.get("nonce")
                if isinstance(sender, str) and sender and isinstance(nonce, int) and _tx_slot_key(tx) is not None:
                    superseded = mempool.remove_superseded(self._chain_id, sender, nonce)
                    if superseded:
                        logger.info(
                            "Dropped %d superseded pending tx(s) for (%s, nonce %d)",
                            superseded,
                            sender,
                            nonce,
                        )
            if evicted:
                logger.info("Evicted %s included transaction(s) from mempool", evicted)
        except Exception as exc:
            logger.warning("Mempool eviction after block import failed: %s", exc)

    @staticmethod
    def _block_rejected_txs(block_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Apply-rejected tx identities the proposer stamped in block_metadata (#1248)."""
        raw = block_data.get("block_metadata")
        if not raw:
            return []
        try:
            metadata = json.loads(raw) if isinstance(raw, str) else raw
        except (RecursionError, TypeError, ValueError):
            return []
        entries = metadata.get("rejected_txs") if isinstance(metadata, dict) else None
        if not isinstance(entries, list):
            return []
        return [e for e in entries if isinstance(e, dict) and isinstance(e.get("tx_hash"), str) and e["tx_hash"]]

    def _persist_import_rejections(self, session: Session, block_data: dict[str, Any]) -> None:
        """Write service-state ``rejected`` rows for txs the proposer reports as
        apply-rejected, so every host's chain.db carries the terminal marker
        the mempool admission and sweeper paths consult (R14-M1, #1248).

        Sparse rows: the full envelope never left the proposer's mempool, so
        only the slot-identifying fields travel in block_metadata. A row
        already ``confirmed`` is left untouched — sealing beats rejection.
        Best-effort per entry: a malformed metadata entry must not fail the
        block import.
        """
        entries = self._block_rejected_txs(block_data)
        if not entries:
            return
        height = int(block_data.get("height") or 0)
        proposer = str(block_data.get("proposer") or "")
        for e in entries:
            tx_hash = e["tx_hash"]
            nonce = e.get("nonce")
            try:
                existing = session.exec(
                    select(ChainTransaction).where(
                        ChainTransaction.chain_id == self._chain_id,
                        ChainTransaction.tx_hash == tx_hash,
                    )
                ).first()
                metadata_note = f"apply-rejected by proposer {proposer} at height {height}: {e.get('reason', '')}"
                if existing is not None:
                    if existing.status != "confirmed":
                        existing.status = "rejected"
                        existing.tx_metadata = metadata_note
                        session.add(existing)
                    continue
                session.add(
                    ChainTransaction(
                        chain_id=self._chain_id,
                        tx_hash=tx_hash,
                        sender=str(e.get("sender") or ""),
                        recipient="",
                        payload={},
                        nonce=nonce if isinstance(nonce, int) and not isinstance(nonce, bool) else 0,
                        value=0,
                        fee=0,
                        type=str(e.get("type") or "TRANSFER").upper(),
                        status="rejected",
                        block_height=None,
                        tx_metadata=metadata_note,
                    )
                )
            except Exception as exc:
                logger.warning("Failed to record import-side rejection for tx %s: %s", tx_hash, exc)

    def _evict_rejected_from_mempool(self, block_data: dict[str, Any]) -> None:
        """Drop apply-rejected txs this block's metadata names from the local
        mempool — they can never seal and otherwise squat their (sender,
        nonce) slot until TTL (R14-M1, #1248). Best-effort: a mempool failure
        must never turn into a block-import failure."""
        entries = self._block_rejected_txs(block_data)
        if not entries:
            return
        try:
            from .mempool import get_mempool

            mempool = get_mempool()
            evicted = 0
            for e in entries:
                if mempool.remove(e["tx_hash"], self._chain_id):
                    evicted += 1
                    # #1999: name the tx and the proposer's verdict reason —
                    # the count-only summary left probes unable to tell which
                    # rejection fired.
                    logger.info(
                        "Evicted apply-rejected tx %s from mempool at height %s (reason: %s)",
                        e["tx_hash"],
                        block_data.get("height"),
                        e.get("reason") or "unspecified",
                    )
            if evicted:
                logger.info(
                    "Evicted %d apply-rejected tx(s) from mempool at height %s",
                    evicted,
                    block_data.get("height"),
                )
        except Exception as exc:
            logger.warning("Rejected-tx mempool eviction failed: %s", exc)

    def _describe_local_state_divergence(self, session: Session, parent_height: int) -> str | None:
        """Describe how our account state differs from the state root our own head records.

        Only called after a state-root rejection has already rolled the session back, so
        the accounts read here are our committed pre-block state. That state must hash to
        the state root stored in our head block. When it does not, the fault is local --
        state was mutated outside block import, or a block was applied without being
        recorded -- and no number of retries of the incoming block will resolve it.

        Returns None when the local state is consistent with our head (in which case the
        incoming block itself is at fault), or when the comparison cannot be made.
        """
        parent = session.exec(select(Block).where(Block.chain_id == self._chain_id, Block.height == parent_height)).first()
        if parent is None or not parent.state_root:
            return None
        actual = state_root_utils.compute_state_root_full(session, self._chain_id)
        if actual is None:
            return None
        recorded = str(parent.state_root)
        if actual.replace("0x", "").lower() == recorded.replace("0x", "").lower():
            return None
        return f"head records state root {recorded}, our accounts hash to {actual}"

    def _fork_choice_key(self, block_timestamp: Any, parent_timestamp: Any, block_hash: str) -> tuple[int, str]:
        """Deterministic fork-choice key: (proposer round, block hash).

        The lower key wins. The round is derived from the same header fields
        the proposer used (``block_ts - parent_ts`` against the proposer round
        window), so every node that sees the same two headers picks the same
        winner — including the node that produced the losing block. The hash
        is a deterministic tie-break for two blocks produced in the same
        round (e.g. a partition where both sides were schedule-valid).
        """
        round_seconds = getattr(settings, "consensus_proposer_round_seconds", 60) or 60
        ts = block_timestamp
        if isinstance(ts, str):
            from datetime import datetime

            ts = datetime.fromisoformat(ts)
        return (proposer_round(parent_timestamp, ts, round_seconds), str(block_hash).lower())

    def _validate_rival_header(self, session: Session, block_data: dict[str, Any], parent_ts: Any) -> tuple[str | None, Any]:
        """Header checks a rival fork block must pass before it may displace ours.

        Returns ``(error_reason, parsed_timestamp)`` — reason is None when the
        header is usable. Everything that can be checked without mutating
        state runs here: timestamp sanity (parsable, at or after the parent's,
        not beyond one proposer window of clock skew into the future) and the
        proposer schedule for the round that timestamp claims. The signature
        was already verified in ``import_block``; the state root is validated
        by ``_append_block`` inside the same transaction as the delete, so a
        failure there still leaves our rows intact.
        """
        from datetime import UTC, datetime

        raw_ts = block_data.get("timestamp")
        try:
            ts = datetime.fromisoformat(str(raw_ts)) if raw_ts else None
        except (ValueError, TypeError):
            ts = None
        if ts is None:
            return f"rival block has no valid timestamp: {raw_ts!r}", None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if parent_ts is not None:
            pts = parent_ts if parent_ts.tzinfo is not None else parent_ts.replace(tzinfo=UTC)
            if ts < pts:
                return "rival block timestamp precedes its parent", ts
        skew = getattr(settings, "consensus_proposer_round_seconds", 60) or 60
        if (ts - datetime.now(UTC)).total_seconds() > skew:
            return "rival block timestamp is in the future", ts

        if self._validate_signatures:
            sig_ok, sig_reason = self._validator.validate_block_signature(block_data)
            if not sig_ok:
                return f"rival block signature invalid: {sig_reason}", ts

        rival = Block(
            chain_id=self._chain_id,
            height=block_data.get("height", -1),
            hash=block_data["hash"],
            parent_hash=block_data.get("parent_hash", ""),
            proposer=block_data.get("proposer", "unknown"),
            timestamp=ts,
            tx_count=block_data.get("tx_count", 0),
            state_root=block_data.get("state_root"),
            bridge_state_root=block_data.get("bridge_state_root"),
            signature=block_data.get("signature", ""),
        )
        try:
            self._validate_proposer_schedule(session, block_data, rival)
        except ValueError as exc:
            return str(exc), ts
        return None, ts

    def _blocks_provably_empty(self, session: Session, blocks: list[Block]) -> bool:
        """True when every block in the segment demonstrably moved no state.

        Removing a block without touching the delta journal is only safe if
        its transactions changed nothing — a block is provably empty when it
        carries no transactions and its recorded state root equals its
        parent's. Non-empty journaled segments take the undo path in
        ``state.block_deltas.revert_losing_segment`` instead.
        """
        by_hash = {b.hash: b for b in blocks}
        for block in sorted(blocks, key=lambda b: b.height):
            if (block.tx_count or 0) > 0:
                return False
            parent = by_hash.get(block.parent_hash)
            if parent is None:
                parent = session.exec(
                    select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == block.parent_hash)
                ).first()
            if parent is not None and block.state_root and parent.state_root:
                if str(block.state_root).lower() != str(parent.state_root).lower():
                    return False
        return True

    def _resolve_fork(
        self, session: Session, block_data: dict[str, Any], transactions: list[dict[str, Any]] | None, our_head: Block
    ) -> ImportResult:
        """Resolve a same-height hash conflict with a deterministic fork-choice rule.

        The push path can only decide a *tip race*: the rival shares our head's
        parent and our head has no descendants. Then the winner is the lower
        ``(round, hash)``. Anything deeper — different parents, or our block
        already extended — is a branch-weight question that needs the rival's
        full segment; it stays diverged for the pull resolver
        (``_resolve_fork_with_peer``).

        The rival is fully validated (timestamp sanity + proposer schedule;
        the signature was already checked in ``import_block``) BEFORE our head
        is staged for deletion, and the delete+append share one transaction:
        if ``_append_block`` rejects on the state root, its rollback restores
        our row. A rival therefore cannot shorten our chain by merely
        *claiming* the better key.
        """
        fork_height = block_data.get("height", -1)
        our_height = our_head.height
        fork_chain_id = block_data.get("chain_id", "")
        fork_hash = block_data.get("hash", "")
        metrics_registry.increment("sync_forks_detected_total")
        logger.warning(
            "Fork detected at height %s (our height: %s, fork hash: %s..., our hash: %s...)",
            fork_height,
            our_height,
            fork_hash[:16],
            our_head.hash[:16],
            extra={
                "fork_height": fork_height,
                "our_height": our_height,
                "fork_hash": fork_hash,
                "our_hash": our_head.hash,
                "fork_chain_id": fork_chain_id,
                "our_chain_id": self._chain_id,
            },
        )
        if fork_chain_id and fork_chain_id != self._chain_id:
            return self._make_import_result(
                accepted=False,
                height=fork_height,
                block_hash=fork_hash,
                reason=f"Incompatible chain: block from chain '{fork_chain_id}' does not match our chain '{self._chain_id}' (heights: {fork_height} vs {our_height})",
            )

        ours = session.exec(select(Block).where(Block.chain_id == self._chain_id).where(Block.height == fork_height)).first()
        parent_hash = block_data.get("parent_hash", "")
        if ours is None or parent_hash != ours.parent_hash or fork_height != our_height:
            # Not a decidable tip race: either the parents differ (the rival's
            # round is not derivable without its parent timestamp) or our block
            # already has descendants, in which case a single rival header
            # cannot outweigh our whole segment. The pull resolver fetches the
            # rival's segment and decides on branch weight.
            metrics_registry.increment("sync_divergence_rejected_total")
            return self._make_import_result(
                accepted=False,
                height=fork_height,
                block_hash=fork_hash,
                reason=(
                    f"Divergent chain: we hold a different block at height {fork_height} "
                    f"(ours {ours.hash[:16] if ours else '?'}..., peer {fork_hash[:16]}...); "
                    "branch-weight resolution required via pull"
                ),
                diverged=True,
            )

        parent = session.exec(select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == parent_hash)).first()
        parent_ts = parent.timestamp if parent else None

        # Validate the rival BEFORE it is allowed to matter: a block that
        # fails timestamp sanity or the proposer schedule is rejected outright
        # and can never cost us our head.
        invalid, rival_ts = self._validate_rival_header(session, block_data, parent_ts)
        if invalid:
            metrics_registry.increment("sync_fork_invalid_rival_total")
            metrics_registry.increment("sync_blocks_rejected_total")
            logger.warning("Rival fork block at height %s rejected: %s", fork_height, invalid)
            return self._make_import_result(
                accepted=False, height=fork_height, block_hash=fork_hash, reason=f"Invalid rival fork block: {invalid}"
            )

        our_key = self._fork_choice_key(ours.timestamp, parent_ts, ours.hash)
        their_key = self._fork_choice_key(rival_ts, parent_ts, fork_hash)
        metrics_registry.increment("sync_fork_choice_compared_total")

        if their_key >= our_key:
            metrics_registry.increment("sync_fork_choice_local_wins_total")
            metrics_registry.increment("sync_divergence_rejected_total")
            logger.warning(
                "Fork resolved at height %s: local block wins (round %s hash %s... beats round %s hash %s...)",
                fork_height,
                our_key[0],
                ours.hash[:16],
                their_key[0],
                fork_hash[:16],
            )
            return self._make_import_result(
                accepted=False,
                height=fork_height,
                block_hash=fork_hash,
                reason=(
                    f"Fork resolved at height {fork_height}: our block wins deterministically "
                    f"(round {our_key[0]} vs {their_key[0]}) — peer must resync"
                ),
                diverged=True,
            )

        # Rival wins the tip race. Replacing our head removes a committed row:
        # provably-empty blocks are deleted outright, non-empty ones are
        # reverted through the per-block delta journal (verified against the
        # parent's recorded state root + the per-table digests + the
        # structural row check) — otherwise escalate to an operator resync.
        # SYNC_FORK_UNDO_ENABLED=false is the operator kill-switch.
        orphaned: list[dict[str, Any]] = []
        if not self._blocks_provably_empty(session, [ours]):
            reverted = (
                revert_losing_segment(session, self._chain_id, [ours], parent, self._blocks_provably_empty)
                if settings.sync_fork_undo_enabled
                else None
            )
            if reverted is None:
                metrics_registry.increment("sync_fork_reorg_unsafe_total")
                metrics_registry.increment("sync_divergence_rejected_total")
                logger.error(
                    "Rival block wins fork at height %s but our block there could not be reverted — "
                    "missing journal or state-root mismatch; operator resync required",
                    fork_height,
                )
                return self._make_import_result(
                    accepted=False,
                    height=fork_height,
                    block_hash=fork_hash,
                    reason=(
                        f"Rival fork wins at height {fork_height} but local block could not be undone; manual resync required"
                    ),
                    diverged=True,
                )
            orphaned = reverted
            metrics_registry.increment("sync_fork_reorg_undone_total")
        else:
            for tx in session.exec(
                select(ChainTransaction)
                .where(ChainTransaction.chain_id == self._chain_id)
                .where(ChainTransaction.block_height == ours.height)
            ).all():
                session.delete(tx)
            session.delete(ours)
        # The undos/deletes above are flushed so the unique (chain_id, height)
        # constraint admits the rival, but nothing is committed until
        # _append_block's own commit — its failure paths roll back, restoring
        # our head.
        session.flush()
        try:
            result = self._append_block(session, block_data, transactions)
        except Exception as exc:
            session.rollback()
            logger.exception("Rival fork block failed to append at height %s", fork_height)
            metrics_registry.increment("sync_fork_invalid_rival_total")
            return self._make_import_result(
                accepted=False,
                height=fork_height,
                block_hash=fork_hash,
                reason=f"Rival fork block failed validation: {exc}",
                diverged=True,
            )
        if not result.accepted:
            # _append_block already rolled the transaction back; our head is intact.
            result.diverged = True
            metrics_registry.increment("sync_fork_invalid_rival_total")
            return result
        metrics_registry.increment("sync_reorgs_total")
        metrics_registry.increment("sync_fork_choice_remote_wins_total")
        metrics_registry.observe("sync_reorg_depth", 1.0)
        logger.warning(
            "Tip reorg at height %s: rival wins (round %s vs our %s)",
            fork_height,
            their_key[0],
            our_key[0],
            extra={"removed_blocks": 1, "new_height": fork_height},
        )
        result.reorged = True
        result.reorg_depth = 1
        if orphaned:
            failed = requeue_orphaned_transactions(self._chain_id, orphaned)
            logger.warning(
                "Requeued %s of %s orphaned transactions into the mempool", len(orphaned) - len(failed), len(orphaned)
            )
            # The rival block is already committed, so winning-branch checks
            # are definitive — classify rejected orphans immediately.
            reconcile_orphaned_transactions(self._chain_id, failed, self._session_factory)
        return result

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
