"""
Practical Byzantine Fault Tolerance (PBFT) Consensus Implementation
Provides Byzantine fault tolerance for up to 1/3 faulty validators

# ════════════════════════════════════════════════════════════════
# v0.7.5: All 5 security review findings fixed (C4-C5, H4-H6).
# Guard now reads from settings.multi_validator_consensus_enabled
# instead of MULTI_VALIDATOR_CONSENSUS_ENABLED env var.
# Keep guard in place until B14 test suite passes.
# ════════════════════════════════════════════════════════════════
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging
from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..metrics import metrics_registry
from .multi_validator_poa import MultiValidatorPoA
from .pbft_certificate import strict_certificate_active, validate_commit_certificate
from .pbft_cross_view import cross_view_commit_lock_active
from .pbft_quorum import pbft_required_messages
from .pbft_view_change import (
    MAX_VC_BUCKETS,
    MAX_NV_BUCKETS,
    MAX_VC_BUCKETS_PER_SENDER,
    MAX_VC_SET_ENTRIES,
    NV_MESSAGE_TYPE,
    VC_MESSAGE_TYPE,
    new_view_digest,
    scheduled_proposer,
    select_forced_hash,
    vc_signed_message,
    nv_signed_message,
    view_change_active,
    view_change_digest,
    verify_new_view,
    verify_view_change,
    MAX_LOCK_PROOF_MSGS,
    proposal_body_bound,
    proposal_body_signed,
    verify_vc_lock_proof,
)

logger = get_logger(__name__)


class PBFTPhase(Enum):
    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    EXECUTE = "execute"


class PBFTMessageType(Enum):
    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    VIEW_CHANGE = "view_change"
    NEW_VIEW = "new_view"


@dataclass
class PBFTMessage:
    message_type: PBFTMessageType
    sender: str
    view_number: int
    sequence_number: int
    digest: str
    signature: str
    timestamp: float
    block_hash: str = ""
    # #2005 F3-C: pre-prepare extensions, populated only while
    # ``view_change_active(sequence)`` — ``block`` is the full signed
    # proposal payload (ruling 2A, Option R) and ``new_view`` the NEW_VIEW
    # proof for this view. Both stay None on every other message type, so
    # commit-certificate ``to_dict`` output is byte-identical.
    block: dict[str, Any] | None = None
    new_view: dict[str, Any] | None = None
    # Transient intake flag: the proposal body was persisted before any
    # PREPARE may be broadcast (design §5/§7 fail-closed rule). Not gossiped.
    _proposal_persisted: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "message_type": self.message_type.value,
            "sender": self.sender,
            "view_number": self.view_number,
            "sequence_number": self.sequence_number,
            "digest": self.digest,
            "signature": self.signature,
            "timestamp": self.timestamp,
            "block_hash": self.block_hash,
        }
        if self.block is not None:
            out["block"] = self.block
        if self.new_view is not None:
            out["new_view"] = self.new_view
        return out


@dataclass
class PBFTState:
    current_view: int
    current_sequence: int
    prepared_messages: dict[str, list[PBFTMessage]]
    committed_messages: dict[str, list[PBFTMessage]]
    pre_prepare_messages: dict[str, PBFTMessage]


def _int_key_seq(key: str) -> int:
    """Sequence half of a "{seq}:{view}" bucket key; -1 for malformed keys so
    they never match a bound (#1060 defensive layer)."""
    try:
        return int(key.split(":")[0])
    except (ValueError, AttributeError):
        return -1


class PBFTConsensus:
    """PBFT consensus implementation"""

    def __init__(
        self,
        consensus: MultiValidatorPoA,
        private_key: str = "",
        *,
        chain_id: str,
        local_validator: str = "",
        sync_manager: Any | None = None,
    ):
        if not settings.multi_validator_consensus_enabled:
            raise RuntimeError(
                "PBFTConsensus is not yet activated. "
                "Set multi_validator_consensus_enabled=true in config to enable (requires security review)."
            )
        self.consensus = consensus
        # #2005 r3: the cross-view evidence detector on the consensus object
        # needs this engine's verified NEW_VIEWs to attach the unlock proof.
        try:
            consensus._pbft_engine = self  # type: ignore[attr-defined]
        except AttributeError:
            pass  # duck-typed double without attribute assignment
        self._private_key = private_key
        self._chain_id = chain_id
        self._local_validator = local_validator
        self._sync_manager: Any | None = sync_manager
        self._gossip_backend: Any = None
        self._view_change_count = 0
        self._message_event = asyncio.Event()
        self._local_prepared: set[str] = set()
        self._local_committed: set[str] = set()
        # The (round, block hash) this node has prepared at each height: one
        # block per round, and rounds only ever move forward. See prepare_phase
        # for why the round has to be part of it.
        self._prepared_heights: dict[int, tuple[int, str]] = {}
        # #2005 F3-C: VIEW_CHANGE protocol state — (sequence, view) ->
        # {canonical sender: verified VIEW_CHANGE dict} and (sequence,
        # view) -> {"payload","kind","selected"} for verified NEW_VIEWs.
        # Bounded by MAX_VC_BUCKETS / MAX_NV_BUCKETS; re-gossipable so NOT
        # persisted (the durable floor/lock/prepared/proposal state lives on
        # ``consensus`` — see multi_validator_poa._pbft_view_change).
        self._vc_messages: dict[tuple[int, int], dict[str, dict[str, Any]]] = {}
        self._vc_last_resend: dict[tuple[int, int], float] = {}
        self._new_views: dict[tuple[int, int], dict[str, Any]] = {}
        # #1940 F3-B: this node's cross-view commit locks (sequence ->
        # committed block_hash), hydrated from the persisted ConsensusState
        # row. Consulted only while ``cross_view_commit_lock_active`` is
        # true; the authoritative copy lives on ``consensus`` and is
        # re-read on every vote so a lock armed post-init or restored by
        # ``load_state`` is always seen. ``_commit_locks`` mirrors it for
        # observability and duck-typed consensus doubles.
        self._commit_locks: dict[int, str] = {}
        _locks_loader = getattr(consensus, "pbft_commit_locks", None)
        if callable(_locks_loader):
            self._commit_locks = dict(_locks_loader())
        self.state = PBFTState(
            current_view=0, current_sequence=0, prepared_messages={}, committed_messages={}, pre_prepare_messages={}
        )
        self._on_execute: Any = None
        self._recalculate_fault_tolerance()

    def get_message_digest(self, block_hash: str, sequence: int, view: int) -> str:
        """Generate message digest for PBFT"""
        content = f"{block_hash}:{sequence}:{view}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def pre_prepare_phase(
        self,
        proposer: str,
        block_hash: str,
        sequence: int | None = None,
        view: int | None = None,
        block_payload: dict[str, Any] | None = None,
        new_view_payload: dict[str, Any] | None = None,
    ) -> bool:
        """Phase 1: Pre-prepare.

        ``sequence`` and ``view`` should be the block height and the proposer
        round. Both are derived from the block itself, so every node keys the
        round identically. The local-counter fallbacks below only apply to
        callers that do not know the height; they drift between nodes across
        restarts and should not be relied on.
        """
        # H4: recalculate fault tolerance in case validator set changed
        self._recalculate_fault_tolerance()

        sequence = self.state.current_sequence + 1 if sequence is None else sequence
        view = self.state.current_view if view is None else view
        # The round the caller derived from block timestamps is the view, and
        # adopting it here is the whole of the view change. What used to sit in
        # this spot was a local timer that bumped ``current_view`` on the
        # proposer alone, 30s after it announced a block: nothing read the
        # result, no other node was told, and the proposer that had actually
        # gone dark was never running a timer in the first place.
        self._adopt_round_as_view(view)
        # #2005 F3-C: while the VIEW_CHANGE gate is armed the pre-prepare
        # MUST carry the full signed block (ruling 2A / Option R) and, once
        # the protocol has engaged for this height, the NEW_VIEW proof.
        # VC floor/NEW_VIEW assembly and the fail-closed proposal-body
        # persist all happen here, BEFORE anything is broadcast.
        if view_change_active(sequence):
            prepared = await self._prepare_view_change_proposal(sequence, view, block_hash, block_payload)
            if prepared is None:
                return False
            block_payload, new_view_payload = prepared
        elif block_payload is not None or new_view_payload is not None:
            # Gate inactive: never emit the extensions — flag-off stays
            # byte-identical to the pre-#2005 wire format.
            block_payload = None
            new_view_payload = None
        digest = self.get_message_digest(block_hash, sequence, view)

        message = PBFTMessage(
            message_type=PBFTMessageType.PRE_PREPARE,
            sender=proposer,
            view_number=view,
            sequence_number=sequence,
            digest=digest,
            signature="",
            timestamp=time.time(),
            block_hash=block_hash,
            block=block_payload,
            new_view=new_view_payload,
        )
        # B6: sign the pre-prepare message with the sender's private key
        self._sign_message(message)

        # Store pre-prepare message
        key = f"{sequence}:{view}"
        self.state.pre_prepare_messages[key] = message

        # Broadcast to all validators
        await self._broadcast_message(message)

        self._message_event.set()  # noqa: unawaited-async - asyncio.Event.set is synchronous
        return True

    async def _ensure_synced(self) -> bool:
        """Ask SyncManager to catch up and wait until the gap is small."""
        if self._sync_manager is None or not settings.sync_manager_enabled:
            return True
        max_gap = getattr(settings, "sync_manager_max_proposal_gap", 2)
        timeout = getattr(settings, "sync_manager_proposal_sync_timeout", 30)
        status = self._sync_manager.get_sync_status(self._chain_id)
        if status.get("gap", 0) <= max_gap:
            return True
        logger.warning("PBFT sync gap %s exceeds %s on chain %s, forcing catch-up", status.get("gap"), max_gap, self._chain_id)
        await self._sync_manager.force_catch_up(self._chain_id)
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self._sync_manager.get_sync_status(self._chain_id)
            if status.get("gap", 0) <= max_gap:
                return True
            try:
                await asyncio.wait_for(asyncio.sleep(1), timeout=1.0)
            except asyncio.TimeoutError:
                pass
        logger.warning("PBFT timed out waiting for sync on chain %s", self._chain_id)
        return False

    def _locked_reproposal(self, sequence: int, fresh_hash: str) -> tuple[str, dict[str, Any]] | None:
        """The commit-locked ``(hash, body)`` this node must re-propose (#2157).

        Only while the view-change gate is armed at ``sequence``, a durable
        commit lock exists for a hash other than the fresh block's, the body
        is held, signed, bound to that hash, and this node is the body's own
        proposer (#2133 R4 requires body proposer == pre-prepare sender).
        """
        if not view_change_active(sequence):
            return None
        lock = self._vc_commit_lock(sequence)
        locked_hash = lock.get("block_hash") if isinstance(lock, dict) else None
        if not isinstance(locked_hash, str) or not locked_hash or locked_hash == fresh_hash:
            return None
        body = self._vc_proposal_get(sequence, locked_hash)
        if body is None or not proposal_body_bound(body, locked_hash, sequence):
            return None
        if canonical_address(str(body.get("proposer", ""))) != canonical_address(str(self._local_validator)):
            return None
        return locked_hash, body

    async def propose_and_wait(
        self,
        proposer: str,
        block_hash: str,
        timeout: float | None = None,
        sequence: int | None = None,
        view: int | None = None,
        block_payload: dict[str, Any] | None = None,
    ) -> bool:
        """Run the full PBFT proposal pipeline for the local proposer.

        Waits for a prepare quorum and then a commit quorum before returning.
        The caller writes the block only when this returns True.
        """
        started_at = time.time()
        if not await self._ensure_synced():
            logger.warning("PBFT propose_and_wait aborted: sync check failed")
            return False

        if not self._local_validator:
            self._local_validator = proposer
        # Capture the sequence/view before pre-prepare broadcasts trigger commits
        pre_prepare_sequence = self.state.current_sequence + 1 if sequence is None else sequence
        pre_prepare_view = self.state.current_view if view is None else view
        key = f"{pre_prepare_sequence}:{pre_prepare_view}"
        # #2157: a height with a persisted commit lock can only ever decide
        # the locked hash (a locked NEW_VIEW permits nothing else), so a fresh
        # block here is refused by every follower and the chain stalls. When
        # this node authored the locked body, re-propose it as-is in this view.
        locked = self._locked_reproposal(pre_prepare_sequence, block_hash)
        if locked is not None:
            block_hash, block_payload = locked
            logger.warning(
                "PBFT re-proposing commit-locked block %s at seq %s view %s instead of a fresh block",
                block_hash[:18],
                pre_prepare_sequence,
                pre_prepare_view,
            )
        await self.pre_prepare_phase(
            proposer,
            block_hash,
            pre_prepare_sequence,
            pre_prepare_view,
            block_payload=block_payload,
        )
        pre_prepare_msg = self.state.pre_prepare_messages.get(key)
        if not pre_prepare_msg:
            logger.warning("PBFT propose_and_wait aborted: missing pre-prepare for seq %s", pre_prepare_sequence)
            return False

        # Send our own prepare; it will trigger a local commit once a prepare quorum forms
        await self.prepare_phase(self._local_validator, pre_prepare_msg)

        # Wait for enough prepares (other validators respond via handle_incoming_message)
        deadline = time.time() + timeout if timeout else None
        if not await self._wait_for_quorum(
            key, self.state.prepared_messages, "prepare", deadline, started_at, pre_prepare_sequence, pre_prepare_view
        ):
            return False

        # Wait for enough commits
        if not await self._wait_for_quorum(
            key, self.state.committed_messages, "commit", deadline, started_at, pre_prepare_sequence, pre_prepare_view
        ):
            return False

        duration = time.time() - started_at
        logger.info(
            "PBFT round completed for key %s (proposer=%s, block_hash=%s, "
            "required=%s, prepares=%s, commits=%s, duration=%.3fs)",
            key,
            proposer,
            block_hash,
            self.required_messages,
            len(self.state.prepared_messages.get(key, [])),
            len(self.state.committed_messages.get(key, [])),
            duration,
        )
        # A re-proposed locked block is imported by the re-seal path (the
        # original block + this round's certificate), never sealed from the
        # caller's fresh block, whose hash is not the decided value.
        return locked is None

    async def _wait_for_quorum(
        self,
        key: str,
        messages: dict[str, list[PBFTMessage]],
        phase: str,
        deadline: float | None,
        started_at: float,
        sequence: int,
        view: int,
    ) -> bool:
        """Block until ``messages[key]`` reaches the required quorum or the deadline.

        ``phase`` is the log label ("prepare"/"commit"); ``sequence``/``view``
        feed the view-change resend.
        """
        while True:
            self._recalculate_fault_tolerance()
            if len(messages.get(key, [])) >= self.required_messages:
                return True
            if deadline and time.time() > deadline:
                duration = time.time() - started_at
                logger.warning(
                    "PBFT %s quorum timeout for key %s (required=%s, have=%s, duration=%.3fs)",
                    phase,
                    key,
                    self.required_messages,
                    len(messages.get(key, [])),
                    duration,
                )
                return False
            self._message_event.clear()
            try:
                await asyncio.wait_for(self._message_event.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass
            await self._resend_view_change_if_due(sequence, view)

    async def prepare_phase(self, validator: str, pre_prepare_msg: PBFTMessage) -> bool:
        """Phase 2: Prepare"""
        self._recalculate_fault_tolerance()
        # B6: verify the incoming pre-prepare message signature
        if not self._verify_message_signature(pre_prepare_msg):
            return False

        key = f"{pre_prepare_msg.sequence_number}:{pre_prepare_msg.view_number}"

        if key not in self.state.pre_prepare_messages:
            return False

        # Only the local validator sends one prepare per key
        local_decision = await self._local_prepare_decision(pre_prepare_msg, key, validator)
        if local_decision is not None:
            return local_decision

        # Create prepare message
        prepare_msg = PBFTMessage(
            message_type=PBFTMessageType.PREPARE,
            sender=validator,
            view_number=pre_prepare_msg.view_number,
            sequence_number=pre_prepare_msg.sequence_number,
            digest=pre_prepare_msg.digest,
            signature="",
            timestamp=time.time(),
            block_hash=pre_prepare_msg.block_hash,
        )
        # B6: sign the prepare message with the sender's private key
        self._sign_message(prepare_msg)

        # Store prepare message
        if key not in self.state.prepared_messages:
            self.state.prepared_messages[key] = []
        self.state.prepared_messages[key].append(prepare_msg)

        # Broadcast prepare message
        await self._broadcast_message(prepare_msg)

        self._message_event.set()  # noqa: unawaited-async - asyncio.Event.set is synchronous

        # Check if we have enough prepare messages and trigger commit
        if len(self.state.prepared_messages[key]) >= self.required_messages:
            if self._local_validator:
                await self._maybe_send_commit(key)
            return True
        return False

    async def _local_prepare_decision(self, pre_prepare_msg: PBFTMessage, key: str, validator: str) -> bool | None:
        """Local-validator prepare gate for ``prepare_phase``.

        Returns ``None`` when the caller should continue building the
        PREPARE message; a bool is ``prepare_phase``'s own return value for
        the early-exit paths (refusals, an already-sent prepare, or a
        duplicate that already reached quorum). Non-local senders skip the
        gate entirely.
        """
        if validator != self._local_validator:
            return None
        # v0.25.6: one block per height per round, and never a round this
        # node has already left behind. Preparing two blocks in the same
        # round would let both reach a quorum and fork the height; going
        # back to an earlier round would do the same in slow motion.
        #
        # v0.25.7: the rule used to be one block per height across *every*
        # round, which is safe and also dead. A round that fails leaves its
        # block hash pinned at that height, and the stand-in the next round
        # hands the slot to necessarily proposes a different hash, so every
        # validator refuses it. A proposer dying between its pre-prepare and
        # the commit quorum -- the exact fault the rotation exists to
        # survive -- therefore froze that height until the survivors were
        # restarted, because the pin lives only in memory. Being in round r
        # is itself the evidence, derived from the parent block's timestamp
        # and agreed by every node without a message, that no round below r
        # produced a block; superseding them is what lets the rotation
        # finish the height instead of only re-nominating for it.
        height = pre_prepare_msg.sequence_number
        view = pre_prepare_msg.view_number
        prepared = self._prepared_heights.get(height) or self._durable_prepared(height)
        if prepared is not None:
            prepared_view, prepared_hash = prepared
            if view < prepared_view:
                logger.warning(
                    "PBFT refusing height %s round %s: this node has already prepared round %s",
                    height,
                    view,
                    prepared_view,
                )
                return False
            if view == prepared_view and prepared_hash != pre_prepare_msg.block_hash:
                logger.warning(
                    "PBFT refusing a second block at height %s round %s (prepared %s, offered %s)",
                    height,
                    view,
                    prepared_hash,
                    pre_prepare_msg.block_hash,
                )
                return False
        if key in self._local_prepared:
            return len(self.state.prepared_messages.get(key, [])) >= self.required_messages
        # #2005 F3-C: while the VIEW_CHANGE gate is armed this node may
        # only prepare a block the verified NEW_VIEW for (height, view)
        # permits — and only after its proposal body is persisted
        # (Option R). Both checks are dormant while the gate is unset.
        if not await self._view_change_prepare_allows(height, view, pre_prepare_msg):
            return False
        # The durable prepared record persists BEFORE the prepare is
        # broadcast — a restart must not forget this vote (design §7).
        if view_change_active(height) and not self._vc_prepared_arm(height, view, pre_prepare_msg.block_hash):
            return False
        self._local_prepared.add(key)
        self._prepared_heights[height] = (view, pre_prepare_msg.block_hash)
        return None

    async def commit_phase(self, validator: str, prepare_msg: PBFTMessage) -> bool:
        """Phase 3: Commit"""
        self._recalculate_fault_tolerance()
        # B6: verify the incoming prepare message signature
        if not self._verify_message_signature(prepare_msg):
            return False

        key = f"{prepare_msg.sequence_number}:{prepare_msg.view_number}"

        if validator == self._local_validator:
            if key in self._local_committed:
                return len(self.state.committed_messages.get(key, [])) >= self.required_messages
            # #1940 F3-B: once the cross-view commit lock is armed for this
            # sequence, this node may not emit a commit for a different
            # block_hash in a later view — the first committed value is
            # final. Refusal happens BEFORE the message exists, so nothing
            # is stored or broadcast; prepare rotation is untouched.
            if not self._commit_lock_allows(prepare_msg.sequence_number, prepare_msg.block_hash, prepare_msg.view_number):
                return False
            # #2005 F3-C: the floor rule + NEW_VIEW permit gate the commit
            # exactly like the prepare — a node that raised its floor may
            # only commit the value the verified NEW_VIEW selected.
            if not self._view_change_commit_allows(
                prepare_msg.sequence_number, prepare_msg.view_number, prepare_msg.block_hash
            ):
                return False
            self._local_committed.add(key)

        # Create commit message
        commit_msg = PBFTMessage(
            message_type=PBFTMessageType.COMMIT,
            sender=validator,
            view_number=prepare_msg.view_number,
            sequence_number=prepare_msg.sequence_number,
            digest=prepare_msg.digest,
            signature="",
            timestamp=time.time(),
            block_hash=prepare_msg.block_hash,
        )
        # B6: sign the commit message with the sender's private key
        self._sign_message(commit_msg)

        # Store commit message
        if key not in self.state.committed_messages:
            self.state.committed_messages[key] = []
        self.state.committed_messages[key].append(commit_msg)

        # #2005 F3-C: persist this node's commit-lock — view, hash and the
        # OWN signed COMMIT a later VIEW_CHANGE must carry as proof —
        # BEFORE the commit is broadcast (design §3/§7, fail closed).
        if (
            validator == self._local_validator
            and view_change_active(commit_msg.sequence_number)
            and not self._vc_commit_lock_arm(
                commit_msg.sequence_number,
                commit_msg.view_number,
                commit_msg.block_hash,
                commit_msg.to_dict(),
                self._lock_proof_msgs(key, commit_msg.block_hash),
            )
        ):
            self.state.committed_messages[key].remove(commit_msg)
            self._local_committed.discard(key)
            return False

        # Broadcast commit message
        await self._broadcast_message(commit_msg)

        self._message_event.set()  # noqa: unawaited-async - asyncio.Event.set is synchronous

        # Check if we have enough commit messages
        if len(self.state.committed_messages[key]) >= self.required_messages:
            return await self.execute_phase(key)

        return False

    def _locked_commit_hash(self, sequence: int) -> str | None:
        """The persisted cross-view commit lock for ``sequence``, if any.

        Reads through to ``consensus`` so a lock armed by another
        PBFTConsensus sharing the same MultiValidatorPoA — or restored by
        ``load_state`` after a restart — is always seen; the in-memory
        ``_commit_locks`` mirror is the fallback for duck-typed doubles.
        """
        getter = getattr(self.consensus, "pbft_commit_lock_get", None)
        if callable(getter):
            locked = getter(sequence)
            if isinstance(locked, str):
                self._commit_locks[sequence] = locked
                return locked
            return None
        return self._commit_locks.get(sequence)

    def _new_view_supersedes_commit_lock(self, sequence: int, view: int | None, block_hash: str) -> bool:
        """F3-A/F3-B/VC precedence (#2005 review).

        While the VIEW_CHANGE gate is armed a VERIFIED NEW_VIEW for exactly
        ``(sequence, view)`` is authoritative for what may be voted: its
        selection is derived from a quorum of lock-proof-carrying VIEW_CHANGEs
        (Q1), so a hash it selects is safe even when this node's own F3-B
        pin names an older hash — refusing would strand the height behind a
        lock the quorum already superseded. Never applies without a stored
        NEW_VIEW (floor never raised -> pre-protocol, F3-B governs unchanged).
        """
        if view is None or not view_change_active(sequence):
            return False
        if self._vc_floor(sequence) is None or (sequence, view) not in self._new_views:
            return False
        return self._view_change_permit(sequence, view, block_hash)

    def _commit_lock_allows(self, sequence: int, block_hash: str, view: int | None = None) -> bool:
        """Whether this node may emit a local COMMIT for ``block_hash``.

        Dormant while ``cross_view_commit_lock_active(sequence)`` is False —
        the pre-#1940-F3-B rotation behavior then applies byte-for-byte.
        Armed: the first committed ``block_hash`` per sequence is locked;
        same-hash commits in later views stay legal (they cannot fork the
        value), a different hash is refused BEFORE broadcast (log + metric).
        Arming persists ``(sequence, hash)`` through ``consensus`` first and
        fails closed — a persistence failure means no broadcast, matching
        the #1268 vote-journal precedent.
        """
        if not cross_view_commit_lock_active(sequence):
            return True
        locked = self._locked_commit_hash(sequence)
        if locked is None:
            if self.consensus.pbft_commit_lock_arm(sequence, block_hash):
                self._commit_locks[sequence] = block_hash
                metrics_registry.increment("pbft_cross_view_commit_lock_armed_total")
                return True
            metrics_registry.increment("pbft_cross_view_commit_lock_persist_failed_total")
            logger.error(
                "PBFT cross-view commit lock for seq %s could not be persisted; refusing to broadcast commit for %s",
                sequence,
                block_hash,
            )
            return False
        if locked == block_hash:
            return True
        if self._new_view_supersedes_commit_lock(sequence, view, block_hash):
            metrics_registry.increment("pbft_cross_view_commit_lock_superseded_total")
            return True
        metrics_registry.increment("pbft_cross_view_commit_refused_total")
        logger.warning(
            "PBFT refusing cross-view commit at seq %s: locked to %s, offered %s",
            sequence,
            locked,
            block_hash,
        )
        return False

    def _quorum_block_hash(self, key: str) -> str | None:
        """The ``block_hash`` whose commits reached quorum for bucket ``key``.

        The quorum digest is the local pre-prepare's, and the digest binds
        ``(block_hash, sequence, view)``, so the pre-prepare's hash IS the
        quorum's hash. ``None`` when there is no local pre-prepare or the
        digest has not reached ``required_messages``.
        """
        pp = self.state.pre_prepare_messages.get(key)
        if pp is None:
            return None
        commits = self.state.committed_messages.get(key, [])
        if self._digest_count(commits, pp.digest) < self.required_messages:
            return None
        return pp.block_hash

    def _execute_allowed_by_commit_lock(self, sequence: int, key: str, view: int | None = None) -> bool:
        """Whether a commit quorum for ``key`` may trigger local execution.

        Dormant while the gate is inactive or this node holds no lock for
        ``sequence``. Armed with a lock: a quorum for a DIFFERENT hash means
        more than f validators double-committed — the lock makes that
        impossible for honest voters, so if it still arrives (Byzantine
        quorum) the node stalls safely instead of forking the height.
        """
        if not cross_view_commit_lock_active(sequence):
            return True
        locked = self._locked_commit_hash(sequence)
        if locked is None:
            return True
        winner = self._quorum_block_hash(key)
        if winner is None or winner == locked:
            return True
        if self._new_view_supersedes_commit_lock(sequence, view, winner):
            return True
        metrics_registry.increment("pbft_cross_view_execute_refused_total")
        logger.warning(
            "PBFT refusing execution at seq %s: commit lock is %s but quorum is for %s",
            sequence,
            locked,
            winner,
        )
        return False

    async def execute_phase(self, key: str) -> bool:
        """Phase 4: Execute"""
        # Extract sequence and view from key
        sequence, view = map(int, key.split(":"))

        # #1940 F3-B: a commit quorum for a hash this node did not lock at
        # this sequence must not trigger local execution.
        if not self._execute_allowed_by_commit_lock(sequence, key, view):
            return False

        # Update state
        self.state.current_sequence = sequence

        # Clean up old messages
        self._cleanup_messages(sequence)

        # Notify the block production path that consensus is complete
        if self._on_execute:
            try:
                pp = self.state.pre_prepare_messages.get(key)
                if pp:
                    await self._on_execute(pp.block_hash, self.state.committed_messages.get(key, []))
            except Exception:
                logger.exception("PBFT on_execute callback failed for key %s", key)

        # #2005 F3-C Option R: a commit quorum's decided value must stay
        # recoverable — every committer persisted the pre-prepare's full
        # signed block, so any honest holder can re-publish the ORIGINAL
        # block as-is plus the commit certificate when the proposer's own
        # seal path is the only publisher and it dies after quorum
        # (dead-after-quorum re-seal, design §5/§7 test 6). Dormant unless
        # the view-change gate is armed at this sequence.
        await self._maybe_reseal_committed_block(key, sequence, view)

        return True

    async def _maybe_reseal_committed_block(self, key: str, sequence: int, view: int) -> None:
        """Publish ``block + commit certificate`` for a decided height (#2005).

        The re-seal carries the ORIGINAL header, proposer signature and
        derived round unchanged — a locked block cannot be re-proposed under
        a new header (design §5), so this is a re-publish of the persisted
        pre-prepare body, never a new proposal. ``block_metadata`` is
        reconstructed from the commit certificate this node already holds,
        which is exactly what strict-era importers verify. The proposer
        itself skips this: it seals through the normal broadcast path.
        """
        if not view_change_active(sequence):
            return
        pp = self.state.pre_prepare_messages.get(key)
        if pp is None or not pp.block_hash:
            return
        if canonical_address(str(pp.sender)) == canonical_address(str(self._local_validator)):
            return
        body_get = self._vc_proposal_get(sequence, pp.block_hash)
        if not isinstance(body_get, dict):
            metrics_registry.increment("pbft_view_change_reseal_missing_body_total")
            return
        certificate = self.get_certificate(pp.block_hash, view=view)
        if not certificate:
            return
        # #2156: ``block_metadata`` is a JSON STRING on the wire and in the DB
        # (the proposer's gossip body carries ``block.block_metadata``). Parse
        # the proposer's string so its stamps (rejected_txs, state version)
        # survive the re-seal, and publish a string back — a dict here crashed
        # every non-PBFT importer's ``json.loads``.
        prior_metadata = body_get.get("block_metadata")
        if isinstance(prior_metadata, str) and prior_metadata:
            try:
                prior_metadata = json.loads(prior_metadata)
            except (ValueError, RecursionError):
                prior_metadata = None
        block_metadata = dict(prior_metadata) if isinstance(prior_metadata, dict) else {}
        block_metadata["pbft_certificate"] = certificate
        payload = {
            "chain_id": self._chain_id,
            "height": sequence,
            "hash": pp.block_hash,
            "parent_hash": body_get.get("parent_hash"),
            "proposer": body_get.get("proposer"),
            "timestamp": body_get.get("timestamp"),
            "tx_count": body_get.get("tx_count"),
            "state_root": body_get.get("state_root"),
            "bridge_state_root": body_get.get("bridge_state_root"),
            "aux_state_root": body_get.get("aux_state_root"),
            "signature": body_get.get("signature"),
            "block_metadata": json.dumps(block_metadata),
            "transactions": body_get.get("transactions") or [],
        }
        if self._gossip_backend is None:
            return
        try:
            await self._gossip_backend.publish(f"blocks.{self._chain_id}", payload)
            metrics_registry.increment("pbft_view_change_reseal_published_total")
            logger.info(
                "PBFT view-change re-seal published for %s height %s (original proposer %s)",
                pp.block_hash[:18],
                sequence,
                pp.sender,
            )
        except Exception:
            logger.exception("PBFT view-change re-seal publish failed for %s:%s", sequence, view)

    def get_certificate(self, block_hash: str, view: int | None = None) -> list[dict[str, Any]]:
        """Return the commit certificate for a completed PBFT round.

        Searches across all views and sequences for commit messages matching
        the requested block hash, so a certificate is still retrievable after
        a view change during the proposal round.

        #1940 F3: once ``pbft_certificate_strict_height`` is armed at a
        candidate group's sequence — the group sequence IS the block height
        being committed — the certificate must be ONE complete coherent
        ``(sequence, view)`` group that passes the shared strict verifier,
        never a union across buckets. ``view`` then selects only that view's
        group; an incomplete requested view yields ``[]``. With no
        strict-era candidate the legacy union body runs unchanged.
        """
        if self._has_strict_certificate_candidate(block_hash):
            return self._strict_commit_certificate(block_hash, view)
        certificate = []
        for messages in self.state.committed_messages.values():
            for m in messages:
                if m.block_hash == block_hash:
                    certificate.append(m.to_dict())
        # De-duplicate by sender to keep certificates compact.
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for msg in certificate:
            sender = msg.get("sender", "")
            if sender and sender in seen:
                continue
            seen.add(sender)
            deduped.append(msg)
        return deduped

    def _committed_candidates(self, block_hash: str, view: int | None = None) -> list[PBFTMessage]:
        """Commit messages for ``block_hash`` (optionally one view) across all buckets."""
        return [
            m
            for messages in self.state.committed_messages.values()
            for m in messages
            if m.block_hash == block_hash and (view is None or m.view_number == view)
        ]

    def _has_strict_certificate_candidate(self, block_hash: str) -> bool:
        """Whether any commit for ``block_hash`` sits at a strict-era sequence.

        The gate is inferred per candidate group: a group's
        ``sequence_number`` is the block height it commits (the producer
        call passes ``sequence=next_height``), so
        ``strict_certificate_active`` is evaluated on it directly.
        """
        return any(strict_certificate_active(m.sequence_number) for m in self._committed_candidates(block_hash))

    def _strict_commit_certificate(self, block_hash: str, view: int | None) -> list[dict[str, Any]]:
        """Best complete coherent commit group for ``block_hash`` (#1940 F3).

        Candidates are grouped by their SIGNED ``(sequence_number,
        view_number)``; each group is verified independently by the shared
        strict contract and the highest valid view wins (sequence breaks the
        tie deterministically). No valid complete group -> ``[]``.
        """
        groups: dict[tuple[int, int], list[PBFTMessage]] = {}
        for m in self._committed_candidates(block_hash, view):
            groups.setdefault((m.sequence_number, m.view_number), []).append(m)
        validators = self.consensus.get_consensus_participants()
        best_key: tuple[int, int] | None = None
        best_certificate: list[dict[str, Any]] = []
        for (sequence, view_number), messages in groups.items():
            if not strict_certificate_active(sequence):
                continue
            certificate = [m.to_dict() for m in messages]
            ok, _reason = validate_commit_certificate(
                certificate, block_hash, validators, height=sequence, view=view_number, chain_id=self._chain_id
            )
            if not ok:
                continue
            if best_key is None or (view_number, sequence) > best_key:
                best_key = (view_number, sequence)
                best_certificate = certificate
        return best_certificate

    def set_on_execute(self, callback: Any) -> None:
        """Set the callback executed when a commit quorum is reached.

        The callback receives the block hash and the list of commit messages.
        """
        self._on_execute = callback

    def _pre_prepare_digest(self, key: str) -> str | None:
        """The digest the local pre-prepare carries for a bucket key — the only
        digest this node may prepare/commit toward (#1059)."""
        pp = self.state.pre_prepare_messages.get(key)
        return pp.digest if pp is not None else None

    @staticmethod
    def _digest_count(messages: list, digest: str | None) -> int:
        """Count messages carrying one digest — a quorum never mixes digests."""
        return sum(1 for m in messages if m.digest == digest)

    async def _maybe_send_commit(self, key: str) -> bool:
        """Send a local commit message if we have a prepare quorum and have not yet committed."""
        self._recalculate_fault_tolerance()
        prepared = self.state.prepared_messages.get(key, [])
        pp_digest = self._pre_prepare_digest(key)
        if pp_digest is None:
            return False  # no local pre-prepare to bind to
        if self._digest_count(prepared, pp_digest) < self.required_messages:
            return False
        if key in self._local_committed:
            return True

        # Use any prepare message to derive the commit fields
        base = prepared[0]
        return await self.commit_phase(self._local_validator, base)

    async def _broadcast_message(self, message: PBFTMessage) -> None:
        """Broadcast message once to the shared gossip topic."""
        await self._send_to_validator(message)

    async def _send_to_validator(self, message: PBFTMessage) -> None:
        """Send message to the shared gossip backend; subscribers deliver to each validator."""
        if self._gossip_backend is None:
            return  # no-op when no gossip backend is set (for testing)
        topic = f"pbft.{message.message_type.value}.{self._chain_id}"
        msg_data: dict[str, Any] = {
            "message_type": message.message_type.value,
            "sender": message.sender,
            "view_number": message.view_number,
            "sequence_number": message.sequence_number,
            "digest": message.digest,
            "signature": message.signature,
            "timestamp": message.timestamp,
            "block_hash": message.block_hash,
        }
        # #2005 F3-C: pre-prepare extensions ride only when present — every
        # other message type keeps the pre-#2005 wire shape byte-identical.
        if message.block is not None:
            msg_data["block"] = message.block
        if message.new_view is not None:
            msg_data["new_view"] = message.new_view
        await self._gossip_backend.publish(topic, msg_data)

    def sync_to_head(self, head_height: int) -> bool:
        """#2145: align the local sequence with the sealed chain head.

        ``current_sequence`` is the base of the intake window
        (``current_sequence + pbft_max_sequence_ahead``) and starts at 0, but
        the proposer keys every round by block height. Armed on a chain that
        already has blocks, every real-height vote was therefore past the
        window and silently dropped until a first local ``execute_phase`` that
        could never happen. Monotonic: only ever raises the sequence, so a
        stale or reorged-low head cannot reopen an already-executed height.
        The prepared/committed buckets are not carried across a restart, so
        only entries below the new base are pruned. ``current_view`` is left
        alone: it is the proposer round (re-derived from block timestamps and
        adopted per pre-prepare), not a height-like counter.
        """
        try:
            height = int(head_height)
        except (TypeError, ValueError):
            return False
        if height <= self.state.current_sequence:
            return False
        self.state.current_sequence = height
        self._cleanup_messages(height)
        return True

    def _cleanup_messages(self, sequence: int) -> None:
        """Clean up old messages to prevent memory leaks"""
        old_keys = [key for key in self.state.prepared_messages.keys() if _int_key_seq(key) < sequence]

        for key in old_keys:
            self.state.prepared_messages.pop(key, None)
            self.state.committed_messages.pop(key, None)
            self.state.pre_prepare_messages.pop(key, None)

        for height in [h for h in self._prepared_heights if h < sequence]:
            self._prepared_heights.pop(height, None)

        # #2005 F3-C: VC/NEW_VIEW buckets are re-gossipable state — prune
        # them with the message buckets so a long-running node does not
        # accumulate per-height protocol state forever.
        for vc_key in [k for k in self._vc_messages if _int_key_seq(f"{k[0]}:{k[1]}") < sequence]:
            self._vc_messages.pop(vc_key, None)
        for nv_key in [k for k in self._new_views if _int_key_seq(f"{k[0]}:{k[1]}") < sequence]:
            self._new_views.pop(nv_key, None)

    def _adopt_round_as_view(self, view: int) -> None:
        """Move to the round the network is in, keeping the messages for it.

        ``handle_view_change`` also discards every uncommitted message, which is
        what abandoning a round means and the opposite of what adopting one
        does: the pre-prepare that announces the new round arrives interleaved
        with the prepares its peers have already broadcast for it, so clearing
        on arrival throws away votes for the very round being adopted and the
        quorum never forms.
        """
        if view <= self.state.current_view:
            return
        self.state.current_view = view
        self._view_change_count += 1

    def handle_view_change(self, new_view: int) -> bool:
        """Handle view change when proposer fails (H5: safe view change)."""
        if self._sync_manager is not None and settings.sync_manager_enabled:
            create_task_with_logging(
                self._sync_manager.force_catch_up(self._chain_id), name=f"pbft_view_change_sync_{self._chain_id}"
            )
        self.state.current_view = new_view
        self._view_change_count += 1
        # H5: Preserve prepared certificates for committed sequences
        committed_seq = self.state.current_sequence
        # Only clear messages for sequences > current_sequence (uncommitted)
        keys_to_clear = [key for key in list(self.state.prepared_messages.keys()) if _int_key_seq(key) > committed_seq]
        for key in keys_to_clear:
            self.state.prepared_messages.pop(key, None)
            self.state.pre_prepare_messages.pop(key, None)
        # Don't clear committed_messages — they're done
        # Clear uncommitted pre_prepare messages
        pp_to_clear = [key for key in list(self.state.pre_prepare_messages.keys()) if _int_key_seq(key) > committed_seq]
        for key in pp_to_clear:
            self.state.pre_prepare_messages.pop(key, None)
        return True

    # ------------------------------------------------------------------
    # B6: PBFT message signatures (C4)
    # ------------------------------------------------------------------

    def _sign_message(self, message: PBFTMessage) -> None:
        """Sign a PBFT message in place with the sender's private key.

        Only signs when ``self._private_key`` is non-empty. The signed
        payload is the canonical message dict plus ``chain_id`` (#2102) —
        matching the chain-bound preimage ``_verify_message_signature()``
        tries first.
        """
        if not self._private_key:
            return
        from aitbc.crypto.consensus_signing import sign_consensus_message

        from .pbft_vote_signature import pbft_vote_preimage

        msg_data = pbft_vote_preimage(
            {
                "message_type": message.message_type.value,
                "sender": message.sender,
                "view_number": message.view_number,
                "sequence_number": message.sequence_number,
                "digest": message.digest,
            },
            self._chain_id,
        )
        message.signature = sign_consensus_message(msg_data, self._private_key)

    def _verify_message_signature(self, message: PBFTMessage) -> bool:
        """Verify a PBFT message signature (B6/C4).

        Rejects unsigned messages unless ``pbft_require_signatures`` is
        explicitly disabled in config (testing only). Signed messages are
        verified cryptographically regardless of whether this node has its
        own signing key — verification only needs the signer's address.
        """
        if not message.signature:
            return not settings.pbft_require_signatures
        from .pbft_vote_signature import verify_pbft_vote_signature

        # #2102: chain-bound preimage first, legacy preimage fallback —
        # pre-change signatures stay valid, cross-chain replay does not.
        return verify_pbft_vote_signature(
            {
                "message_type": message.message_type.value,
                "sender": message.sender,
                "view_number": message.view_number,
                "sequence_number": message.sequence_number,
                "digest": message.digest,
            },
            message.signature,
            message.sender,
            self._chain_id,
        )

    # ------------------------------------------------------------------
    # B7: Gossip network transport (C5)
    # ------------------------------------------------------------------

    def set_gossip_backend(self, backend: Any) -> None:
        """Set the gossip backend used for broadcasting PBFT messages."""
        self._gossip_backend = backend

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

    # ------------------------------------------------------------------
    # #2005 F3-C: VIEW_CHANGE / NEW_VIEW protocol (dormant)
    #
    # Everything below is gated by ``view_change_active(sequence)`` — while
    # ``pbft_view_change_height`` is unset the methods are never reached and
    # the engine is byte-identical to the pre-#2005 rotation behavior.
    # ------------------------------------------------------------------

    # -- persistence wrappers (duck-typed consensus doubles stay safe) --

    def _vc_floor(self, sequence: int) -> int | None:
        fn = getattr(self.consensus, "pbft_vc_floor", None)
        return fn(sequence) if callable(fn) else None

    def _vc_floor_raise(self, sequence: int, view: int) -> bool:
        fn = getattr(self.consensus, "pbft_vc_floor_raise", None)
        return bool(fn(sequence, view)) if callable(fn) else False

    def _vc_commit_lock(self, sequence: int) -> dict[str, Any] | None:
        fn = getattr(self.consensus, "pbft_vc_commit_lock", None)
        return fn(sequence) if callable(fn) else None

    def _durable_prepared(self, sequence: int) -> tuple[int, str] | None:
        """This node's persisted prepared ``(view, hash)`` for an armed height.

        #2005 r3: the durable record used to be write-only, so a restart lost
        ``_prepared_heights`` and the node could prepare a second block in the
        same view (the restart-amnesia hole the design claims to close). Read
        back through the persisted record and mirror it into memory.
        """
        if not view_change_active(sequence):
            return None
        records = getattr(self.consensus, "pbft_vc_records", None)
        rec = records().get(sequence) if callable(records) else None
        prepared = rec.get("prepared") if isinstance(rec, dict) else None
        if not isinstance(prepared, dict):
            return None
        view, block_hash = prepared.get("view"), prepared.get("block_hash")
        if not isinstance(view, int) or isinstance(view, bool) or not isinstance(block_hash, str) or not block_hash:
            return None
        self._prepared_heights[sequence] = (view, block_hash)
        return view, block_hash

    def _vc_commit_lock_arm(
        self, sequence: int, view: int, block_hash: str, commit: dict[str, Any], proof: list[dict[str, Any]]
    ) -> bool:
        fn = getattr(self.consensus, "pbft_vc_commit_lock_arm", None)
        return bool(fn(sequence, view, block_hash, commit, proof)) if callable(fn) else False

    def _lock_proof_msgs(self, key: str, block_hash: str) -> list[dict[str, Any]]:
        """The PREPARE quorum certificate backing a commit-lock (#2005 Q1).

        One signed PREPARE per distinct sender for ``block_hash`` at the
        locked ``key`` (``seq:view``), capped. Returns ``[]`` when fewer than
        ``required_messages`` distinct voters are held — the caller then
        refuses to arm (a lock nobody can verify would only get its VIEW_CHANGE
        dropped).
        """
        proof: dict[str, dict[str, Any]] = {}
        for msg in self.state.prepared_messages.get(key, []):
            if msg.block_hash != block_hash or not msg.signature:
                continue
            proof.setdefault(canonical_address(str(msg.sender)), msg.to_dict())
            if len(proof) >= MAX_LOCK_PROOF_MSGS:
                break
        if len(proof) < self.required_messages:
            return []
        return list(proof.values())

    def _vc_prepared_arm(self, sequence: int, view: int, block_hash: str) -> bool:
        fn = getattr(self.consensus, "pbft_vc_prepared_arm", None)
        return bool(fn(sequence, view, block_hash)) if callable(fn) else False

    def _vc_expected_proposer(self, sequence: int, view: int) -> str | None:
        """Scheduled NEW_VIEW sender for ``(sequence, view)`` (#2133 R1).

        Derived from the shared VC member set — the exact computation the
        on-chain ``view_change_justified`` runs — so the engine can never accept
        a NEW_VIEW from a proposer the chain would not excuse under
        ``is_active``/role skew. Falls back to the engine schedule only when the
        consensus object exposes no shared set (legacy/test doubles).
        """
        members = self._vc_participants(sequence)
        if callable(getattr(self.consensus, "pbft_vc_validator_set", None)) and members:
            return scheduled_proposer(members, sequence, view)
        try:
            return self.consensus.select_proposer(sequence, view)
        except TypeError:
            return self.consensus.select_proposer(sequence)

    def _vc_proposal_store(self, sequence: int, block_hash: str, payload: dict[str, Any], sender: str) -> bool:
        # #2133 R4: the body's self-declared proposer must be the authenticated
        # pre-prepare sender (itself checked against the schedule at intake).
        if canonical_address(str(payload.get("proposer", ""))) != canonical_address(sender):
            metrics_registry.increment("pbft_view_change_proposal_unsigned_total")
            logger.warning("PBFT refusing proposal body for seq %s: proposer is not the pre-prepare sender", sequence)
            return False
        if not proposal_body_signed(payload):
            metrics_registry.increment("pbft_view_change_proposal_unsigned_total")
            logger.warning("PBFT refusing proposal body for seq %s: missing/invalid proposer block signature", sequence)
            return False
        fn = getattr(self.consensus, "pbft_vc_proposal_store", None)
        return bool(fn(sequence, block_hash, payload)) if callable(fn) else False

    def _vc_proposal_get(self, sequence: int, block_hash: str) -> dict[str, Any] | None:
        fn = getattr(self.consensus, "pbft_vc_proposal_get", None)
        if not callable(fn):
            return None
        result = fn(sequence, block_hash)
        return result if isinstance(result, dict) else None

    def view_change_unlock_justification(self, sequence: int, view: int) -> dict[str, Any] | None:
        """The ``unlock_justification`` for cross-view evidence at ``(h, v')``.

        ``{"kind": "view_change", "new_view": <the verified NEW_VIEW>}`` — the
        exact shape ``equivocation_policy.view_change_justified`` verifies —
        or ``None`` when this node holds no verified NEW_VIEW for the slot
        (or the gate is dormant). Producer for #2005: without it the proof
        existed only in tests.
        """
        if not view_change_active(sequence):
            return None
        entry = self._new_views.get((sequence, view))
        payload = entry.get("payload") if entry is not None else None
        if not isinstance(payload, dict):
            return None
        return {"kind": "view_change", "new_view": dict(payload)}

    def _vc_participants(self, sequence: int | None = None) -> list[str]:
        """VC member set; with ``sequence`` the shared chain-state derivation
        (#2133 item 1), else the legacy participant view."""
        fn = getattr(self.consensus, "pbft_vc_validator_set", None)
        if sequence is not None and callable(fn):
            return sorted(fn(sequence))
        return list(self.consensus.get_consensus_participants())

    def _vc_quorum(self, sequence: int) -> int:
        """VC/NEW_VIEW quorum for ``sequence`` over the shared member set."""
        members = self._vc_participants(sequence)
        return pbft_required_messages(len(members)) if members else self.required_messages

    # -- sending VIEW_CHANGE --

    def _commit_certificate_known(self, sequence: int) -> bool:
        """Whether a commit quorum for ``sequence`` is already visible locally.

        Design §3(a): a voter sends VC(h, v') only when no commit certificate
        for h is known — a decided height never view-changes.
        """
        for key, commits in self.state.committed_messages.items():
            if _int_key_seq(key) != sequence:
                continue
            pp = self.state.pre_prepare_messages.get(key)
            if pp is None:
                continue
            if self._digest_count(commits, pp.digest) >= self.required_messages:
                return True
        return False

    async def _send_view_change(self, sequence: int, view: int) -> bool:
        """Persist the floor, then broadcast VIEW_CHANGE(h, view).

        Order is load-bearing (design §7): the floor record is written
        BEFORE the message may leave — a persistence failure means no VC.
        The VC's ``lock`` carries this node's persisted commit-lock plus its
        own signed COMMIT as proof.
        """
        if not self._local_validator or not self._private_key:
            return False
        if not self._vc_floor_raise(sequence, view):
            metrics_registry.increment("pbft_view_change_persist_failed_total")
            logger.error("PBFT view-change floor for seq %s view %s could not be persisted; no VC sent", sequence, view)
            return False
        lock = None
        lock_view, lock_hash = -1, ""
        lock_rec = self._vc_commit_lock(sequence)
        if isinstance(lock_rec, dict):
            lv = lock_rec.get("view")
            lh = lock_rec.get("block_hash")
            proof = lock_rec.get("proof")
            if (
                isinstance(lv, int)
                and not isinstance(lv, bool)
                and 0 <= lv < view
                and isinstance(lh, str)
                and lh
                and isinstance(proof, list)
            ):
                lock_view, lock_hash = lv, lh
                lock = {"view": lv, "block_hash": lh, "kind": "prepare", "msgs": proof}
        vc = {
            "message_type": VC_MESSAGE_TYPE,
            "sender": self._local_validator,
            "sequence_number": sequence,
            "view_number": view,
            "timestamp": time.time(),
            "lock": lock,
        }
        vc["digest"] = view_change_digest(self._chain_id, sequence, view, lock_view, lock_hash)
        from aitbc.crypto.consensus_signing import sign_consensus_message

        vc["signature"] = sign_consensus_message(vc_signed_message(vc), self._private_key)
        # Record our own VC so a locally-assembled NEW_VIEW can count it.
        bucket = self._vc_messages.setdefault((sequence, view), {})
        bucket.setdefault(canonical_address(self._local_validator), vc)
        if self._gossip_backend is not None:
            await self._gossip_backend.publish(f"pbft.{VC_MESSAGE_TYPE}.{self._chain_id}", vc)
        await self._maybe_build_new_view(sequence, view)
        return True

    VC_RESEND_INTERVAL_SECONDS = 2.0

    async def _resend_view_change_if_due(self, sequence: int, view: int) -> None:
        """Periodic re-send (#2005 review): gossip is lossy, and a VIEW_CHANGE
        or NEW_VIEW published once can be missed by exactly the peers that
        need it. While the gate is armed and no NEW_VIEW is stored for the
        slot, re-publish this node's own VC; the proposer also re-publishes
        the NEW_VIEW it built. Rate-limited, never creates a message — it only
        repeats ones already built, signed and persisted.
        """
        if not view_change_active(sequence) or self._gossip_backend is None:
            return
        now = time.monotonic()
        if now - self._vc_last_resend.get((sequence, view), 0.0) < self.VC_RESEND_INTERVAL_SECONDS:
            return
        entry = self._new_views.get((sequence, view))
        if entry is not None:
            payload = entry.get("payload")
            if isinstance(payload, dict) and canonical_address(str(payload.get("sender", ""))) == canonical_address(
                str(self._local_validator)
            ):
                self._vc_last_resend[(sequence, view)] = now
                await self._gossip_backend.publish(f"pbft.{NV_MESSAGE_TYPE}.{self._chain_id}", payload)
            return
        own = self._vc_messages.get((sequence, view), {}).get(canonical_address(str(self._local_validator)))
        if own is None:
            return
        if len(self._vc_last_resend) >= MAX_VC_BUCKETS:
            self._vc_last_resend.clear()
        self._vc_last_resend[(sequence, view)] = now
        metrics_registry.increment("pbft_view_change_resent_total")
        await self._gossip_backend.publish(f"pbft.{VC_MESSAGE_TYPE}.{self._chain_id}", own)

    async def _ensure_view_change_sent(self, sequence: int, view: int) -> bool:
        """Raise the floor to ``view`` when the round has reached it.

        True when the floor already covers ``view``, a commit certificate
        for the height is known (no view change needed), or the VC was
        persisted+broadcast. False on persistence/signing failure — callers
        must then refuse the vote (fail closed).
        """
        floor = self._vc_floor(sequence)
        if floor is not None and view <= floor:
            return True
        if self._commit_certificate_known(sequence):
            return True
        return await self._send_view_change(sequence, view)

    # -- receiving VIEW_CHANGE --

    def _vc_in_window(self, seq: int, view: int) -> bool:
        """Same sequence/view window the PREPARE/COMMIT intake applies (#1060).

        VIEW_CHANGE / NEW_VIEW used to skip it, so one validator could fill the
        bucket table with signed junk (seq, view) pairs and starve the honest
        VC for the real stalled height (#2005 r2 finding 3).
        """
        if seq < self.state.current_sequence:
            return False
        max_seq = self.state.current_sequence + getattr(settings, "pbft_max_sequence_ahead", 512)
        max_view = self.state.current_view + getattr(settings, "pbft_max_view_ahead", 64)
        return seq <= max_seq and view <= max_view

    def _vc_make_room(self, table: dict[tuple[int, int], Any], key: tuple[int, int], cap: int) -> bool:
        """Admit ``key`` into a bounded (seq, view) table, evicting the FARTHEST slot.

        Entries below the local height are dead and go first; if the table is
        still full the farthest-ahead slot is dropped only when the newcomer is
        nearer, so the live stalled (h, v') pair always displaces junk.
        """
        for stale in [k for k in table if k[0] < self.state.current_sequence]:
            table.pop(stale, None)
        if len(table) < cap:
            return True
        farthest = max(table)
        if key < farthest:
            table.pop(farthest, None)
            return True
        return False

    def _vc_sender_slot(self, sender: str, key: tuple[int, int]) -> bool:
        """Per-sender bucket budget for VIEW_CHANGEs (#2133 / reviewer B's R1).

        A sender holding ``MAX_VC_BUCKETS_PER_SENDER`` buckets may add another only
        by displacing its OWN farthest one, and only for a nearer key — so no single
        Byzantine validator can fill the shared table (from either side of the live
        pair) and starve honest VCs. Stale seqs are pruned first.
        """
        for stale in [k for k in self._vc_messages if k[0] < self.state.current_sequence]:
            self._vc_messages.pop(stale, None)
        own = [k for k, b in self._vc_messages.items() if sender in b]
        if len(own) < MAX_VC_BUCKETS_PER_SENDER:
            return True
        farthest = max(own)
        if key >= farthest:
            return False
        bucket = self._vc_messages[farthest]
        bucket.pop(sender, None)
        if not bucket:
            del self._vc_messages[farthest]
        return True

    def _vc_store(self, sender: str, data: dict[str, Any], key: tuple[int, int]) -> bool:
        """Bound + store one verified VC; False when dropped."""
        bucket = self._vc_messages.get(key)
        if bucket is not None and sender in bucket:
            return False  # one VC per (sender, height, view) — first wins
        if not self._vc_sender_slot(sender, key):
            metrics_registry.increment("pbft_view_change_flood_dropped_total")
            return False
        bucket = self._vc_messages.get(key)
        if bucket is None:
            if not self._vc_make_room(self._vc_messages, key, MAX_VC_BUCKETS):
                metrics_registry.increment("pbft_view_change_flood_dropped_total")
                return False
            bucket = self._vc_messages[key] = {}
        if sender in bucket:
            return False  # one VC per (sender, height, view) — first wins
        if len(bucket) >= MAX_VC_SET_ENTRIES:
            metrics_registry.increment("pbft_view_change_flood_dropped_total")
            return False
        bucket[sender] = data
        return True

    async def _handle_view_change_payload(self, data: dict[str, Any]) -> None:
        """Intake one gossip VIEW_CHANGE: verify, bound, store."""
        seq = data.get("sequence_number")
        view = data.get("view_number")
        if (
            not isinstance(seq, int)
            or isinstance(seq, bool)
            or not isinstance(view, int)
            or isinstance(view, bool)
            or seq < 0
            or view < 0
            or not view_change_active(seq)
            or not self._vc_in_window(seq, view)
        ):
            return
        ok, reason = verify_view_change(data, self._chain_id)
        if not ok:
            logger.debug("Dropping invalid VIEW_CHANGE for %s:%s: %s", seq, view, reason)
            return
        participants = {canonical_address(a) for a in self._vc_participants(seq)}
        ok, reason = verify_vc_lock_proof(data, participants, self._vc_quorum(seq), chain_id=self._chain_id)
        if not ok:
            logger.debug("Dropping VIEW_CHANGE with bad lock for %s:%s: %s", seq, view, reason)
            return
        sender = canonical_address(str(data.get("sender", "")))
        # Membership gate BEFORE storing: with an empty participant view the
        # deployment is permissive (same policy as prepare/commit votes).
        if participants and sender not in participants:
            logger.warning(
                "Dropping VIEW_CHANGE for height %s view %s from %s: not a consensus participant",
                seq,
                view,
                data.get("sender"),
            )
            return
        if not self._vc_store(sender, data, (seq, view)):
            return
        self._message_event.set()  # noqa: unawaited-async - asyncio.Event.set is synchronous
        await self._maybe_build_new_view(seq, view)

    async def _maybe_build_new_view(self, sequence: int, view: int) -> None:
        """Q2 (#2005): the scheduled proposer builds NEW_VIEW the moment the
        (h, v') VC bucket reaches quorum — not only when it is about to
        pre-prepare. A NEW_VIEW built lazily at pre-prepare time sees
        whatever VCs happen to have arrived by then, so a late VC could be
        missed and the sub-quorum case never published. Never builds below
        quorum (``_build_new_view`` re-checks) and is idempotent per slot.
        """
        if (sequence, view) in self._new_views:
            return
        if len(self._vc_messages.get((sequence, view), {})) < self._vc_quorum(sequence):
            return
        await self._build_new_view(sequence, view)

    # -- NEW_VIEW: build, receive, verify --

    async def _build_new_view(self, sequence: int, view: int) -> dict[str, Any] | None:
        """Assemble and broadcast NEW_VIEW(h, view) as the scheduled proposer.

        Requires a local VC quorum (>= ``required_messages`` distinct
        verified senders) and ownership of the ``(h, view)`` proposer slot.
        Selection is recomputed from the VC locks — never asserted.
        """
        if not self._local_validator or not self._private_key:
            return None
        existing = self._new_views.get((sequence, view))
        if existing is not None:
            payload = existing.get("payload")
            return payload if isinstance(payload, dict) else None
        expected = self._vc_expected_proposer(sequence, view)
        if canonical_address(str(expected or "")) != canonical_address(self._local_validator):
            return None
        bucket = self._vc_messages.get((sequence, view), {})
        # Dedup by canonical sender — the same rule analyze_vc_set applies.
        by_sender = {canonical_address(str(vc.get("sender", ""))): vc for vc in bucket.values()}
        if len(by_sender) < self._vc_quorum(sequence):
            return None
        vc_set = list(by_sender.values())[:MAX_VC_SET_ENTRIES]
        kind, selected = select_forced_hash({canonical_address(str(vc.get("sender", ""))): vc for vc in vc_set})
        if kind == "conflict":
            logger.error("PBFT NEW_VIEW for %s:%s has conflicting lock reports; refusing to build", sequence, view)
            return None
        chosen = selected if kind == "locked" else None
        nv = {
            "message_type": NV_MESSAGE_TYPE,
            "sender": self._local_validator,
            "sequence_number": sequence,
            "view_number": view,
            "timestamp": time.time(),
            "vc_set": vc_set,
            "chosen_hash": chosen,
        }
        nv["digest"] = new_view_digest(self._chain_id, sequence, view, chosen, [str(vc.get("digest", "")) for vc in vc_set])
        from aitbc.crypto.consensus_signing import sign_consensus_message

        nv["signature"] = sign_consensus_message(nv_signed_message(nv), self._private_key)
        if self._gossip_backend is not None:
            await self._gossip_backend.publish(f"pbft.{NV_MESSAGE_TYPE}.{self._chain_id}", nv)
        self._new_views[(sequence, view)] = {"payload": nv, "kind": kind, "selected": selected}
        return nv

    async def _handle_new_view_payload(self, data: dict[str, Any]) -> None:
        """Intake one gossip NEW_VIEW: full verification, then store."""
        seq = data.get("sequence_number")
        view = data.get("view_number")
        if (
            not isinstance(seq, int)
            or isinstance(seq, bool)
            or not isinstance(view, int)
            or isinstance(view, bool)
            or seq < 0
            or view < 0
            or not view_change_active(seq)
            or not self._vc_in_window(seq, view)
        ):
            return
        if (seq, view) in self._new_views:
            return  # cheap dedup BEFORE any signature verification (ECDSA DoS)
        try:
            expected = self._vc_expected_proposer(seq, view)
        except Exception:  # noqa: BLE001
            expected = None
        if not isinstance(expected, str) or not expected:
            # Fail closed: an unknown schedule must not turn the proposer
            # check off (expected_sender=None skips it) — drop the NEW_VIEW.
            logger.warning("Dropping NEW_VIEW for %s:%s: proposer schedule unavailable", seq, view)
            return
        # Cheap sender pre-filter BEFORE the ~n ECDSA verifications in verify_new_view.
        if canonical_address(str(data.get("sender", ""))) != canonical_address(expected):
            logger.debug("Dropping NEW_VIEW for %s:%s: sender is not the scheduled proposer", seq, view)
            return
        ok, reason, kind, selected = verify_new_view(
            data,
            self._vc_participants(seq),
            chain_id=self._chain_id,
            sequence=seq,
            view=view,
            expected_sender=expected,
        )
        if not ok:
            logger.debug("Dropping invalid NEW_VIEW for %s:%s: %s", seq, view, reason)
            return
        key = (seq, view)
        if key in self._new_views:
            return  # first valid NEW_VIEW wins — a second is proposer equivocation
        if not self._vc_make_room(self._new_views, key, MAX_NV_BUCKETS):
            metrics_registry.increment("pbft_view_change_flood_dropped_total")
            return
        self._new_views[key] = {"payload": data, "kind": kind, "selected": selected}
        await self._retry_view_change_votes(seq, view)

    async def _retry_view_change_votes(self, sequence: int, view: int) -> None:
        """Re-drive prepare/commit for (sequence, view) once its NEW_VIEW verifies."""
        if not self._local_validator:
            return
        key = f"{sequence}:{view}"
        pp = self.state.pre_prepare_messages.get(key)
        if pp is not None and key not in self._local_prepared:
            await self.prepare_phase(self._local_validator, pp)
        await self._maybe_send_commit(key)

    # -- vote gates --

    async def _prepare_view_change_proposal(
        self, sequence: int, view: int, block_hash: str, block_payload: dict[str, Any] | None
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None] | None:
        """Proposer-side gate run inside ``pre_prepare_phase``.

        Returns ``(block_payload, new_view_payload)`` to attach, or None
        when the proposal must not be broadcast (payload missing/oversized
        or persistence failed — fail closed, design §5/§7). While the gate
        is armed a pre-prepare without a block body can never be recovered,
        so it is refused outright.
        """
        if not isinstance(block_payload, dict):
            logger.error(
                "PBFT view-change gate armed at seq %s but no proposal payload supplied; refusing pre-prepare",
                sequence,
            )
            return None
        if not proposal_body_bound(block_payload, block_hash, sequence):
            logger.error("PBFT proposal body for seq %s is not bound to hash %s; refusing pre-prepare", sequence, block_hash)
            return None
        if not await self._ensure_view_change_sent(sequence, view):
            return None
        entry = self._new_views.get((sequence, view))
        new_view_payload = entry["payload"] if entry is not None else None
        if new_view_payload is None:
            new_view_payload = await self._build_new_view(sequence, view)
        if not self._vc_proposal_store(sequence, block_hash, block_payload, self._local_validator or ""):
            metrics_registry.increment("pbft_view_change_persist_failed_total")
            logger.error("PBFT proposal body for seq %s could not be persisted; refusing pre-prepare", sequence)
            return None
        return block_payload, new_view_payload

    async def _view_change_prepare_allows(self, sequence: int, view: int, pp_msg: PBFTMessage) -> bool:
        """Whether this node may broadcast a PREPARE for ``pp_msg``.

        Dormant while the gate is unset. Armed: raises the floor to the
        vote's view (sending VIEW_CHANGE first), requires the proposal body
        to be persisted (Option R), then applies the floor + NEW_VIEW
        permit rule.
        """
        if not view_change_active(sequence):
            return True
        if not await self._ensure_view_change_sent(sequence, view):
            return False
        if isinstance(pp_msg.block, dict) and proposal_body_bound(pp_msg.block, pp_msg.block_hash, sequence):
            if not pp_msg._proposal_persisted:
                pp_msg._proposal_persisted = self._vc_proposal_store(sequence, pp_msg.block_hash, pp_msg.block, pp_msg.sender)
        if not pp_msg._proposal_persisted:
            metrics_registry.increment("pbft_view_change_proposal_missing_total")
            logger.warning(
                "PBFT refusing prepare at seq %s view %s: proposal body not persisted",
                sequence,
                view,
            )
            return False
        return self._view_change_permit(sequence, view, pp_msg.block_hash)

    def _view_change_permit(self, sequence: int, view: int, block_hash: str) -> bool:
        """The floor + NEW_VIEW permit rule (design §3).

        ``floor`` is the highest view this node sent a VIEW_CHANGE for.
        Never raised -> pre-protocol free vote. Otherwise the vote's view
        must be >= floor AND a verified NEW_VIEW for exactly that view must
        permit the hash (free selection permits any; locked selection only
        the forced hash).
        """
        floor = self._vc_floor(sequence)
        if floor is None:
            return True
        if view < floor:
            metrics_registry.increment("pbft_view_change_floor_refused_total")
            logger.warning("PBFT refusing vote at seq %s view %s: floor is %s", sequence, view, floor)
            return False
        entry = self._new_views.get((sequence, view))
        if entry is None:
            return False
        if entry.get("kind") == "free":
            return True
        if entry.get("kind") == "locked":
            return entry.get("selected") == block_hash
        return False

    def _view_change_commit_allows(self, sequence: int, view: int, block_hash: str) -> bool:
        """Commit-side permit: same floor/NV rule plus the held body (Option R)."""
        if not view_change_active(sequence):
            return True
        if not self._view_change_permit(sequence, view, block_hash):
            return False
        if self._vc_proposal_get(sequence, block_hash) is None:
            metrics_registry.increment("pbft_view_change_proposal_missing_total")
            logger.warning(
                "PBFT refusing commit at seq %s view %s: proposal body for %s not held",
                sequence,
                view,
                block_hash,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # B10: View change fixes (H4 + H6)
    # ------------------------------------------------------------------

    def _is_scheduled_proposer(self, sender: str, height: int, view: int) -> bool:
        """Whether ``sender`` owns the (height, round) slot in the round-robin.

        Without this a follower prepares any signed proposal from any
        validator, which is what makes the rotation advisory rather than
        enforced. Unknown schedules (no active validator set) stay permissive
        so single-proposer deployments are unaffected.
        """
        if not getattr(settings, "consensus_enforce_proposer_schedule", True):
            return True
        try:
            expected = self.consensus.select_proposer(height, view)
        except TypeError:
            expected = self.consensus.select_proposer(height)
        return expected is None or expected == sender

    def _recalculate_fault_tolerance(self) -> None:
        """H4: dynamically recalculate fault tolerance from the current validator set."""
        participants = self.consensus.get_consensus_participants()
        active_count = len(participants)
        # True BFT quorum (#1061): shared formula with /consensus/status —
        # MULTI_VALIDATOR_MIN_ATTESTATIONS clamps crash-tolerance attestation
        # only, it must never shrink the Byzantine quorum.
        self.fault_tolerance = max(1, (active_count - 1) // 3)
        self.required_messages = pbft_required_messages(active_count)
