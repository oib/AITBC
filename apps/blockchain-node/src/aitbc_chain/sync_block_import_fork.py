"""Fork-choice, rival validation and reorg helpers for ``BlockImportMixin`` (#1860).

Split out of ``aitbc_chain.sync_block_import`` (#1860): the methods are
byte-identical moves onto a mixin that ``BlockImportMixin`` inherits, so
every ``self._…`` call resolves exactly as before. Import
``aitbc_chain.sync_block_import`` first (it wires these mixins in); this
module is not meant to be imported directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlmodel import Session, select

from .base_models import Block
from .base_models import Transaction as ChainTransaction
from .config import settings
from .consensus.multi_validator_poa import proposer_round
from .logger import get_logger
from .metrics import metrics_registry
from .state import state_root_utils
from .state.block_deltas import reconcile_orphaned_transactions, requeue_orphaned_transactions, revert_losing_segment
from .sync_base import SyncBase
from .sync_validator import ImportResult


logger = get_logger("aitbc_chain.sync_block_import")


class ForkResolutionMixin(SyncBase):
    """Same-height fork resolution: rival header checks, fork choice, safe reorg and divergence reporting."""

    if TYPE_CHECKING:
        # Provided by ``BlockImportMixin`` itself (sync_block_import.py).
        def _make_import_result(self, **kwargs: Any) -> ImportResult: ...

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

        ours_or_error = self._fork_tip_race_check(session, block_data, our_head, fork_height, fork_hash)
        if isinstance(ours_or_error, ImportResult):
            return ours_or_error
        ours = ours_or_error

        parent_hash = block_data.get("parent_hash", "")
        parent = session.exec(select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == parent_hash)).first()
        parent_ts = parent.timestamp if parent else None

        judgment = self._judge_rival_fork(session, block_data, ours, parent_ts, fork_height, fork_hash)
        if isinstance(judgment, ImportResult):
            return judgment
        our_key, their_key = judgment

        # Rival wins the tip race. Replacing our head removes a committed row:
        # provably-empty blocks are deleted outright, non-empty ones are
        # reverted through the per-block delta journal (verified against the
        # parent's recorded state root + the per-table digests + the
        # structural row check) — otherwise escalate to an operator resync.
        # SYNC_FORK_UNDO_ENABLED=false is the operator kill-switch.
        orphaned, undo_error = self._revert_local_head_for_rival(session, ours, parent, fork_height, fork_hash)
        if undo_error is not None:
            return undo_error
        # The undos/deletes above are flushed so the unique (chain_id, height)
        # constraint admits the rival, but nothing is committed until
        # _append_block's own commit — its failure paths roll back, restoring
        # our head.
        session.flush()
        try:
            result = self._append_block(session, block_data, transactions)
        except Exception as exc:  # noqa: BLE001 - must-run rollback + rival-fork metrics boundary
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
        return self._finalize_rival_reorg(result, orphaned, fork_height, their_key, our_key)

    def _fork_tip_race_check(
        self,
        session: Session,
        block_data: dict[str, Any],
        our_head: Block,
        fork_height: int,
        fork_hash: str,
    ) -> Block | ImportResult:
        """Confirm the fork is a decidable tip race: we hold a block at the
        rival's height whose parent matches the rival's parent, and our head
        sits at that same height (no descendants yet). Returns the ``ours``
        Block on success, or an ImportResult rejection when the race is not
        decidable here — anything deeper is a branch-weight question for the
        pull resolver."""
        ours = session.exec(select(Block).where(Block.chain_id == self._chain_id).where(Block.height == fork_height)).first()
        parent_hash = block_data.get("parent_hash", "")
        if ours is None or parent_hash != ours.parent_hash or fork_height != our_head.height:
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
        return ours

    def _judge_rival_fork(
        self,
        session: Session,
        block_data: dict[str, Any],
        ours: Block,
        parent_ts: Any,
        fork_height: int,
        fork_hash: str,
    ) -> ImportResult | tuple[tuple[int, str], tuple[int, str]]:
        """Validate the rival header, then compare deterministic fork-choice
        keys. Returns an ImportResult rejection (invalid rival or local
        wins), or ``(our_key, their_key)`` when the rival wins the tip race."""
        # Validate the rival BEFORE it is allowed to matter: a block that
        # fails timestamp sanity or the proposer schedule is rejected outright
        # and can never cost us our head.
        invalid, rival_ts = self._validate_rival_header(session, block_data, parent_ts)
        if invalid:
            metrics_registry.increment("sync_fork_invalid_rival_total")
            metrics_registry.increment("sync_blocks_rejected_total")
            logger.warning("Rival fork block at height %s rejected: %s", fork_height, invalid)
            return self._make_import_result(
                accepted=False,
                height=fork_height,
                block_hash=fork_hash,
                reason=f"Invalid rival fork block: {invalid}",
            )

        our_key = self._fork_choice_key(ours.timestamp, parent_ts, ours.hash)
        their_key = self._fork_choice_key(rival_ts, parent_ts, fork_hash)
        metrics_registry.increment("sync_fork_choice_compared_total")

        if their_key < our_key:
            return our_key, their_key
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

    def _revert_local_head_for_rival(
        self,
        session: Session,
        ours: Block,
        parent: Block | None,
        fork_height: int,
        fork_hash: str,
    ) -> tuple[list[dict[str, Any]], ImportResult | None]:
        """Undo our head block so the winning rival can take its height.
        Returns ``(orphaned_txs, error_result)`` — exactly one is meaningful."""
        if self._blocks_provably_empty(session, [ours]):
            for tx in session.exec(
                select(ChainTransaction)
                .where(ChainTransaction.chain_id == self._chain_id)
                .where(ChainTransaction.block_height == ours.height)
            ).all():
                session.delete(tx)
            session.delete(ours)
            return [], None
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
            return [], self._make_import_result(
                accepted=False,
                height=fork_height,
                block_hash=fork_hash,
                reason=(
                    f"Rival fork wins at height {fork_height} but local block could not be undone; manual resync required"
                ),
                diverged=True,
            )
        metrics_registry.increment("sync_fork_reorg_undone_total")
        return reverted, None

    def _finalize_rival_reorg(
        self,
        result: ImportResult,
        orphaned: list[dict[str, Any]],
        fork_height: int,
        their_key: tuple[int, str],
        our_key: tuple[int, str],
    ) -> ImportResult:
        """Record the completed tip reorg and requeue orphaned transactions
        into the mempool."""
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
