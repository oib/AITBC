"""PBFT gossip-message intake, split out of ``pbft.py``.

Pure code motion: the methods below are the ``PBFTConsensus`` inbound path —
``handle_incoming_message`` and the per-type vote handlers — unchanged, now
living on ``_IntakeMixin``. Signature verification, membership checks,
sequence/view window bounds and the commit-quorum execute trigger behave
byte-identically to the pre-split ``pbft.py``.

Import ``aitbc_chain.consensus.pbft`` (it wires these mixins into
``PBFTConsensus``); this module is not meant to be imported directly.
"""

from __future__ import annotations

import time
from typing import Any

from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from .pbft import PBFTMessage, PBFTMessageType, _PbftBaseMixin, logger
from .pbft_view_change import NV_MESSAGE_TYPE, VC_MESSAGE_TYPE, proposal_body_bound, view_change_active


class _IntakeMixin(_PbftBaseMixin):
    async def handle_incoming_message(self, message_data: dict[str, Any]) -> None:
        """Handle an incoming gossip message (B7/C5).

        Reconstructs a :class:`PBFTMessage` from the dict, verifies its
        signature, and routes it to the appropriate phase handler based
        on ``message_type``. When enough prepare or commit messages are
        collected, it triggers the next PBFT phase for the local validator.
        """
        self._recalculate_fault_tolerance()
        # #2005 F3-C: VIEW_CHANGE and NEW_VIEW are dict payloads with their
        # own schemas (lock / vc_set / chosen_hash) — they are NOT
        # PBFTMessage votes and never enter the phase buckets. Routed before
        # reconstruction; dormant while the gate is unset.
        if await self._route_view_change_message(message_data):
            return
        message = self._pbft_message_from_dict(message_data)
        if message is None:
            return  # malformed message — drop

        # B6: verify the signature before processing
        if not self._verify_message_signature(message):
            return

        # Intake bounds (#1060): sequence/view must coerce to non-negative ints
        # within a window of the local position — a poisoned key used to crash
        # _cleanup_messages/handle_view_change and a far-future one lingered.
        if not self._message_intake_ok(message):
            return

        # The signed digest must recompute from the (unsigned) block_hash +
        # bounded fields — otherwise block_hash rides unsigned and a swapped
        # hash still verifies (#1059).
        if message.digest != self.get_message_digest(message.block_hash, message.sequence_number, message.view_number):
            return

        # Membership gate: a prepare or commit only carries weight when its
        # sender is in the active consensus set. A valid signature from an
        # address outside the set is still not a vote — without this check any
        # key could inject a quorum and drive commit quorum to execute_phase.
        # An empty participant view stays permissive so single-proposer or
        # not-yet-configured deployments are unaffected (same policy as
        # _is_scheduled_proposer).
        if not self._consensus_membership_ok(message):
            return

        key = f"{message.sequence_number}:{message.view_number}"

        # Route to the appropriate phase handler
        if message.message_type == PBFTMessageType.PRE_PREPARE:
            await self._handle_pre_prepare_vote(message, key)
        elif message.message_type == PBFTMessageType.PREPARE:
            await self._handle_prepare_vote(message, key)
        elif message.message_type == PBFTMessageType.COMMIT:
            await self._handle_commit_vote(message, key)

    async def _route_view_change_message(self, message_data: Any) -> bool:
        """Dispatch a VIEW_CHANGE/NEW_VIEW dict payload; True when handled."""
        if not isinstance(message_data, dict):
            return False
        mtype = message_data.get("message_type")
        if mtype == VC_MESSAGE_TYPE:
            await self._handle_view_change_payload(message_data)
            return True
        if mtype == NV_MESSAGE_TYPE:
            await self._handle_new_view_payload(message_data)
            return True
        return False

    @staticmethod
    def _pbft_message_from_dict(message_data: dict[str, Any]) -> PBFTMessage | None:
        """Reconstruct a PBFTMessage; None on a malformed payload."""
        try:
            return PBFTMessage(
                message_type=PBFTMessageType(message_data["message_type"]),
                sender=message_data["sender"],
                view_number=message_data["view_number"],
                sequence_number=message_data["sequence_number"],
                digest=message_data["digest"],
                signature=message_data.get("signature", ""),
                timestamp=message_data.get("timestamp", time.time()),
                block_hash=message_data.get("block_hash", ""),
                block=message_data.get("block"),
                new_view=message_data.get("new_view"),
            )
        except (KeyError, ValueError):
            return None

    def _message_intake_ok(self, message: PBFTMessage) -> bool:
        """Coerce/bound sequence+view in place; False drops the message."""
        try:
            seq = int(message.sequence_number)
            view = int(message.view_number)
        except (TypeError, ValueError):
            return False  # non-integer sequence/view — drop
        if seq < 0 or view < 0:
            return False
        max_seq = self.state.current_sequence + getattr(settings, "pbft_max_sequence_ahead", 512)
        max_view = self.state.current_view + getattr(settings, "pbft_max_view_ahead", 64)
        if seq > max_seq or view > max_view:
            return False  # far-future sequence/view — drop
        message.sequence_number = seq
        message.view_number = view
        return True

    def _consensus_membership_ok(self, message: PBFTMessage) -> bool:
        """False drops a PREPARE/COMMIT whose sender is outside the consensus set."""
        if message.message_type not in (PBFTMessageType.PREPARE, PBFTMessageType.COMMIT):
            return True
        participants = {canonical_address(a) for a in self.consensus.get_consensus_participants()}
        if participants and canonical_address(message.sender) not in participants:
            logger.warning(
                "PBFT dropping %s for height %s round %s from %s: sender is not a consensus participant",
                message.message_type.value,
                message.sequence_number,
                message.view_number,
                message.sender,
            )
            return False
        return True

    async def _handle_pre_prepare_vote(self, message: PBFTMessage, key: str) -> None:
        if not self._is_scheduled_proposer(message.sender, message.sequence_number, message.view_number):
            logger.warning(
                "PBFT dropping pre-prepare for height %s round %s from %s: not the scheduled proposer",
                message.sequence_number,
                message.view_number,
                message.sender,
            )
            return
        # Follow the rotation the proposer's round implies. Every node
        # derives the same round from the same on-chain timestamps, so a
        # pre-prepare carrying a higher one is the view change arriving.
        self._adopt_round_as_view(message.view_number)
        # #2005 F3-C: while the gate is armed, an extended pre-prepare
        # carries the NEW_VIEW proof and the full proposal body. The NV
        # is verified and stored FIRST so the vote gate below can see
        # it; the body is persisted BEFORE any PREPARE may be broadcast
        # (Option R, fail closed); then the floor rises to this view.
        if view_change_active(message.sequence_number):
            if isinstance(message.new_view, dict):
                await self._handle_new_view_payload(message.new_view)
            if isinstance(message.block, dict) and proposal_body_bound(
                message.block, message.block_hash, message.sequence_number
            ):
                message._proposal_persisted = self._vc_proposal_store(
                    message.sequence_number, message.block_hash, message.block, message.sender
                )
            await self._ensure_view_change_sent(message.sequence_number, message.view_number)
        self.state.pre_prepare_messages[key] = message
        self._message_event.set()  # noqa: unawaited-async - asyncio.Event.set is synchronous
        # As a validator, respond with a prepare for this pre-prepare
        if self._local_validator and message.sender != self._local_validator and key not in self._local_prepared:
            await self.prepare_phase(self._local_validator, message)

    async def _handle_prepare_vote(self, message: PBFTMessage, key: str) -> None:
        # Feed the slashing detector BEFORE the silent duplicate drop:
        # a same-sender prepare for a different block at the same round is
        # a double-sign — it used to vanish into the dedup branch (#1062).
        if settings.consensus_slashing_enabled:
            self.consensus.record_prepare(message.sender, message.block_hash, message.view_number, message=message)
        if key not in self.state.prepared_messages:
            self.state.prepared_messages[key] = []
        if any(m.sender == message.sender for m in self.state.prepared_messages[key]):
            return  # ignore duplicate prepare from same sender
        self.state.prepared_messages[key].append(message)
        self._message_event.set()  # noqa: unawaited-async - asyncio.Event.set is synchronous
        if self._local_validator:
            await self._maybe_send_commit(key)

    async def _handle_commit_vote(self, message: PBFTMessage, key: str) -> None:
        # Feed the slashing detector BEFORE the silent duplicate drop —
        # symmetric to the PREPARE branch (#1235): a same-sender commit
        # for a different digest at the same round is a double-sign.
        if settings.consensus_slashing_enabled:
            self.consensus.record_commit(message.sender, message.block_hash, message.view_number, message=message)
        if key not in self.state.committed_messages:
            self.state.committed_messages[key] = []
        if any(m.sender == message.sender for m in self.state.committed_messages[key]):
            return  # ignore duplicate commit from same sender
        self.state.committed_messages[key].append(message)
        self._message_event.set()  # noqa: unawaited-async - asyncio.Event.set is synchronous
        pp_digest = self._pre_prepare_digest(key)
        if (
            pp_digest is not None
            and self._digest_count(self.state.committed_messages[key], pp_digest) >= self.required_messages
        ):
            await self.execute_phase(key)
