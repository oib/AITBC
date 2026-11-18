"""Release the chain.db write lock across the PBFT/attestation wait (#2193 F2).

Import ``aitbc_chain.consensus.poa`` first (it wires this mixin into
``PoAProposer``); this module is not meant to be imported directly.

The proposal session applies the drained txs (flush = SQLite write lock) and then
waits for the mesh. With ``proposer_release_write_lock_during_gates`` the proposer
rolls back before the wait, and after the gates pass re-applies the *same inputs* on
a fresh transaction. The block is committed only if the re-assembled block hash is
byte-identical to the one the mesh voted on, so this is a local scheduling change —
the sealed block is unchanged and no consensus rule or height gate is involved.
Anything that does not reproduce exactly aborts the round (never commits a
different block): the vote stays recorded, so the next round re-proposes the same
hash through the same-hash-retry pin.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, select

from . import poa as _poa
from .poa import _PoaBaseMixin
from ..config import settings
from ..metrics import metrics_registry
from ..models import Block
from ..state.block_deltas import BlockDeltaJournal

VERDICT_OK = "ok"
VERDICT_SEALED = "sealed"
VERDICT_ABORT = "abort"


@dataclass
class GateReleasePlan:
    """Pre-apply copies of everything the apply path mutates.

    ``existing_tx_map`` and ``account_map`` are written by the apply loop (it marks
    applied txs as present and registers created accounts); a re-apply on the mutated
    maps would skip every tx as already sealed.
    """

    pending_txs: list[Any]
    account_map: dict[str, Any]
    existing_tx_map: dict[str, int]


class _GateReleaseMixin(_PoaBaseMixin):
    def _gate_release_plan(
        self, pending_txs: list[Any], account_map: dict[str, Any], existing_tx_map: dict[str, int]
    ) -> GateReleasePlan | None:
        """Snapshot the apply inputs, or None when the flag is off (the default)."""
        if not settings.proposer_release_write_lock_during_gates:
            return None
        return GateReleasePlan(list(pending_txs), dict(account_map), dict(existing_tx_map))

    async def _run_gates_released(
        self,
        session: Session | None,
        block: Block,
        block_hash: str,
        proposer: str,
        round_number: int,
        next_height: int,
        metadata_dict: dict[str, Any],
        *,
        transactions: list[dict[str, Any]],
        release_plan: GateReleasePlan | None,
        parent_hash: str,
        timestamp: datetime,
        processed_txs: list[Any],
        rejected_txs: list[tuple[Any, str]],
    ) -> str:
        """Run the journaled gates; with a plan, free the write lock for the wait and re-apply after.

        Returns ``ok`` / ``sealed`` / ``abort`` (re-apply) or ``gates_failed``. With no plan
        (flag off) this is exactly ``_run_journaled_gates`` plus ``ok``.
        """
        self._gate_release_begin(session, release_plan)
        if not await self._run_journaled_gates(
            session, block, block_hash, proposer, round_number, next_height, metadata_dict, transactions=transactions
        ):
            return "gates_failed"
        return self._gate_release_finish(
            session,
            release_plan,
            next_height=next_height,
            parent_hash=parent_hash,
            timestamp=timestamp,
            proposer=proposer,
            block_hash=block_hash,
            processed_txs=processed_txs,
            rejected_txs=rejected_txs,
        )

    def _gate_release_begin(self, session: Session | None, plan: GateReleasePlan | None) -> None:
        """Free the write lock before the gates wait. The signed block lives in memory only."""
        if plan is None or session is None:
            return
        session.rollback()
        metrics_registry.increment("proposer_gate_lock_released_total")

    def _gate_release_finish(
        self,
        session: Session | None,
        plan: GateReleasePlan | None,
        *,
        next_height: int,
        parent_hash: str,
        timestamp: datetime,
        proposer: str,
        block_hash: str,
        processed_txs: list[Any],
        rejected_txs: list[tuple[Any, str]],
    ) -> str:
        """Re-apply after the gates passed; return ``ok`` / ``sealed`` / ``abort``.

        ``ok``     — session carries the re-applied state, commit the original block.
        ``sealed`` — the import path already sealed this exact block while we waited.
        ``abort``  — head moved or the re-apply did not reproduce the block; session is clean.
        """
        if plan is None or session is None:
            return VERDICT_OK
        head = session.exec(
            select(Block).where(Block.chain_id == self._config.chain_id).order_by(text("height DESC")).limit(1)
        ).first()
        if head is not None and head.height == next_height and head.hash == block_hash:
            metrics_registry.increment("proposer_gate_already_sealed_total")
            session.rollback()
            return VERDICT_SEALED
        if head is None or head.height != next_height - 1 or head.hash != parent_hash:
            metrics_registry.increment("proposer_gate_head_moved_total")
            self._logger.warning(
                "[PROPOSE] head moved during the gates wait (now %s/%s, expected parent %s at %s); aborting the round",
                head.height if head is not None else None,
                head.hash if head is not None else None,
                parent_hash,
                next_height - 1,
            )
            session.rollback()
            return VERDICT_ABORT
        if self._gate_reapply_matches(
            session, plan, next_height, parent_hash, timestamp, proposer, block_hash, processed_txs, rejected_txs
        ):
            return VERDICT_OK
        metrics_registry.increment("proposer_gate_reapply_mismatch_total")
        session.rollback()
        return VERDICT_ABORT

    def _gate_reapply_matches(
        self,
        session: Session,
        plan: GateReleasePlan,
        next_height: int,
        parent_hash: str,
        timestamp: datetime,
        proposer: str,
        block_hash: str,
        processed_txs: list[Any],
        rejected_txs: list[tuple[Any, str]],
    ) -> bool:
        """Re-run apply + assemble on a fresh transaction; True only on an identical result."""
        # The StateTransition singleton remembers the hashes it applied this block; a re-apply
        # without a reset is rejected as a replay.
        _poa.get_state_transition().reset_processed_cache()
        # The rollback marked the first journal incomplete — the commit needs a fresh capture.
        BlockDeltaJournal.attach(session, self._config.chain_id, next_height)
        rejected: list[tuple[Any, str]] = []
        processed, _changed, ok = self._process_proposal_txs(
            session,
            list(plan.pending_txs),
            dict(plan.account_map),
            dict(plan.existing_tx_map),
            next_height,
            timestamp,
            rejected,
        )
        if not ok:
            self._logger.warning("[PROPOSE] re-apply after the gates wait failed; aborting the round")
            return False
        self._persist_rejected_txs(session, rejected, next_height, timestamp, commit=False)
        _block, new_hash = self._assemble_proposal_block(session, next_height, parent_hash, timestamp, processed, proposer)
        same_txs = [t.tx_hash for t in processed] == [t.tx_hash for t in processed_txs]
        same_rejects = [t.tx_hash for t, _ in rejected] == [t.tx_hash for t, _ in rejected_txs]
        if new_hash != block_hash or not same_txs or not same_rejects:
            self._logger.error(
                "[PROPOSE] re-apply after the gates wait is not byte-identical (hash %s vs voted %s, txs_equal=%s, rejects_equal=%s); aborting the round",
                new_hash,
                block_hash,
                same_txs,
                same_rejects,
            )
            return False
        return True
