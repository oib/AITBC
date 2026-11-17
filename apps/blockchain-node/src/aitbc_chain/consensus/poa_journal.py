"""Vote-journal suppression, abandon publication, and orphan recovery for ``PoAProposer`` (poa split).

Import ``aitbc_chain.consensus.poa`` first (it wires these
mixins into ``PoAProposer``); this module is not meant to be imported
directly."""

from __future__ import annotations

from typing import Any

from . import abandon
from . import poa as _poa
from .poa import _PoaBaseMixin, _send_abandon
from .vote_journal import get_vote_journal

from ..config import settings
from ..metrics import metrics_registry
from ..models import Block
from aitbc.crypto.signature_recovery import canonical_address
from sqlalchemy import text
from sqlmodel import select


class _JournalMixin(_PoaBaseMixin):
    def _own_addresses(self) -> set[str]:
        """Canonical addresses of every validator key this node holds."""
        return {canonical_address(a) for a in self._validator_keys}

    def _attach_unlock_justification(self, next_height: int, metadata_dict: dict[str, Any]) -> None:
        """#1281: move a pending valve justification onto block_metadata."""
        unlock_just = self._unlock_justifications.pop(next_height, None)
        if unlock_just is not None:
            metadata_dict["unlock_justification"] = unlock_just

    async def _publish_abandon(self, block: Block, block_hash: str, round_number: int | None = None) -> None:
        """#1301 L2: tell voters this proposer will never seal ``block_hash``.

        Best-effort and flag-gated; the proposer's own journal entry stays
        (self-lock), so it cannot reseal the abandoned hash itself.

        #1962: ``round_number`` is the proposer round the dropped proposal
        was collected in; it is signed into the statement so voters populate
        the same-round rival guard directly instead of only from local
        evidence. ``None`` keeps the legacy round-less shape.
        """
        if not abandon.abandon_enabled():
            return
        proposer = str(block.proposer)
        if abandon.liveness_enabled():
            # #1985: owe the abandon BEFORE the first publish, durably: a failed or lost first
            # send, or a restart before the height is decided, must not forget it.
            self._abandon_ledger.record(block.height, block_hash, round_number, proposer, 0.0)
        sent = await _send_abandon(
            self._config.chain_id,
            self._validator_keys,
            self._logger,
            block.height,
            block_hash,
            proposer,
            round_number,
        )
        if sent and abandon.liveness_enabled():
            self._abandon_ledger.mark_sent(block.height, block_hash, _poa.time.time())

    async def _abandon_liveness_tick(self, tip_height: int) -> None:
        """#1985: once-per-start orphan recovery, then paced re-announce. Inert unless the liveness flag is armed."""
        if not abandon.liveness_enabled():
            return
        if not self._abandon_orphans_done:
            self._abandon_orphans_done = True
            self._recover_orphaned_proposals(tip_height)
        every = float(getattr(settings, "vote_journal_abandon_reannounce_seconds", 30.0))
        for height, block_hash, owed_round, proposer in self._abandon_ledger.due(tip_height, every, _poa.time.time()):
            if await _send_abandon(
                self._config.chain_id, self._validator_keys, self._logger, height, block_hash, proposer, owed_round
            ):
                self._abandon_ledger.mark_sent(height, block_hash, _poa.time.time())
                metrics_registry.increment("vote_journal_abandon_reannounced_total")

    async def _abandon_tick_from_loop(self) -> None:
        """#1985: run the tick every loop iteration, not only in this validator's own proposal slots.

        Reads the tip in its own short session (no gossip inside an open proposal session). Never
        raises: the re-announce is best-effort and must not disturb the proposer loop.
        """
        if not abandon.liveness_enabled():
            return
        try:
            with self._session_factory() as session:
                head = session.exec(
                    select(Block).where(Block.chain_id == self._config.chain_id).order_by(text("height DESC")).limit(1)
                ).first()
                tip = head.height if head is not None else -1
            await self._abandon_liveness_tick(tip)
        except Exception as exc:  # noqa: BLE001 - best effort; the valve remains the backstop
            self._logger.warning("Abandon re-announce tick failed: %s", exc)

    def _recover_orphaned_proposals(self, tip_height: int) -> None:
        """#1985: proposals this validator journaled above the tip that died with a previous process.

        Nothing is in flight at the first tick after a start, so the block can
        never be sealed: owe an abandon for it and void the own proposal vote
        (the same retract a failed gate performs), or the restarted proposer
        stays pinned to a hash it can no longer produce.
        """
        journal = get_vote_journal(self._config.chain_id)
        for address in self._validator_keys:
            for rec in journal.proposals_above(address, tip_height):
                self._abandon_ledger.record(rec.height, rec.block_hash, rec.round, address, 0.0)
                journal.retract(rec.height, address, rec.block_hash)
                metrics_registry.increment("vote_journal_orphan_proposal_retracted_total")
                self._logger.warning(
                    "[PROPOSE] Orphaned journal proposal %s at height %s (above tip %s): abandoning and retracting",
                    rec.block_hash[:18],
                    rec.height,
                    tip_height,
                )
