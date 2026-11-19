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
import json as json
import time as time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging
from aitbc.crypto.signature_recovery import canonical_address as canonical_address

from ..config import settings
from ..metrics import metrics_registry as metrics_registry
from .multi_validator_poa import MultiValidatorPoA
from .pbft_certificate import (
    strict_certificate_active as strict_certificate_active,
    validate_commit_certificate as validate_commit_certificate,
)
from .pbft_cross_view import cross_view_commit_lock_active as cross_view_commit_lock_active
from .pbft_quorum import pbft_required_messages
from .pbft_view_change import (
    MAX_VC_BUCKETS as MAX_VC_BUCKETS,
    MAX_NV_BUCKETS as MAX_NV_BUCKETS,
    MAX_VC_BUCKETS_PER_SENDER as MAX_VC_BUCKETS_PER_SENDER,
    MAX_VC_SET_ENTRIES as MAX_VC_SET_ENTRIES,
    NV_MESSAGE_TYPE as NV_MESSAGE_TYPE,
    VC_MESSAGE_TYPE as VC_MESSAGE_TYPE,
    new_view_digest as new_view_digest,
    scheduled_proposer as scheduled_proposer,
    select_forced_hash as select_forced_hash,
    vc_signed_message as vc_signed_message,
    nv_signed_message as nv_signed_message,
    view_change_active as view_change_active,
    view_change_digest as view_change_digest,
    verify_new_view as verify_new_view,
    verify_view_change as verify_view_change,
    MAX_LOCK_PROOF_MSGS as MAX_LOCK_PROOF_MSGS,
    proposal_body_bound as proposal_body_bound,
    proposal_body_signed as proposal_body_signed,
    verify_vc_lock_proof as verify_vc_lock_proof,
)

logger = get_logger(__name__)

MAX_BODY_WANTED = 64  # #2171 bound on the fetch bookkeeping tables
BODY_FETCH_WAIT_SECONDS = 5.0  # #2171 how long a proposer waits for a locked body


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


class _PbftBaseMixin:
    """Shared PBFT engine state: init, signing, gossip transport, view sync.

    Base of the ``PBFTConsensus`` mixin decomposition (``pbft_phases`` / ``pbft_intake`` / ``pbft_vc_engine``);
    not instantiated directly.
    """

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
        # #2281: (sequence, view) -> (block_hash, block_payload) this node has
        # already broadcast a pre-prepare for. A same-view retry MUST reuse the
        # emitted hash — the caller rebuilds a fresh block on every retry (new
        # timestamp -> new hash), and a second hash in one view is equivocation:
        # followers refuse it (second_block_same_round) and split prepare
        # quorums end in commit.digest_mismatch freezes. In-memory only: a
        # proposer restart mid-view keeps the pre-existing liveness hole,
        # never a safety one (followers' durable prepared record still
        # refuses the second hash).
        self._emitted_preprepare: dict[tuple[int, int], tuple[str, dict[str, Any] | None]] = {}
        # #2171: locked bodies this node asked for (accepted only when solicited)
        # and the last time it answered a request for one (rate limit).
        self._body_wanted: dict[tuple[int, str], int] = {}
        self._fetch_answered: dict[tuple[int, str], float] = {}
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

    def sync_view(self, round_number: int) -> bool:
        """#2157: seed the view window from the clock-derived proposer round.

        ``current_view`` is the base of the view intake window
        (``current_view + pbft_max_view_ahead``) and restarts at 0, while the
        network's round is derived from block timestamps and keeps climbing
        while a height is stuck. Once the round passed the window every
        pre-prepare and VIEW_CHANGE was dropped silently, so a restarted node
        could never rejoin a stalled height. Monotonic like ``sync_to_head``.
        """
        if isinstance(round_number, bool) or not isinstance(round_number, int) or round_number <= self.state.current_view:
            return False
        self._adopt_round_as_view(round_number)
        return True

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

    # ------------------------------------------------------------------
    # Cross-mixin surface (type declarations only — never called)
    #
    # The concrete implementations live in the sibling mixins
    # (``pbft_phases`` / ``pbft_intake`` / ``pbft_vc_engine``) and the PBFT
    # phases, intake and VIEW_CHANGE runtime call each other through
    # ``self``. Declaring the signatures here keeps ``self.<m>`` fully typed
    # for mypy without touching the moved method bodies; ``PBFTConsensus``
    # always resolves the real override first in its MRO, so these stubs
    # are unreachable at runtime.
    # ------------------------------------------------------------------

    async def prepare_phase(self, validator: str, pre_prepare_msg: PBFTMessage) -> bool:
        raise NotImplementedError

    async def _maybe_send_commit(self, key: str) -> bool:
        raise NotImplementedError

    async def execute_phase(self, key: str) -> bool:
        raise NotImplementedError

    async def _handle_view_change_payload(self, data: dict[str, Any]) -> None:
        raise NotImplementedError

    async def _handle_new_view_payload(self, data: dict[str, Any]) -> None:
        raise NotImplementedError

    async def _ensure_view_change_sent(self, sequence: int, view: int) -> bool:
        raise NotImplementedError

    async def _resend_view_change_if_due(self, sequence: int, view: int) -> None:
        raise NotImplementedError

    async def _prepare_view_change_proposal(
        self, sequence: int, view: int, block_hash: str, block_payload: dict[str, Any] | None
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None] | None:
        raise NotImplementedError

    async def _view_change_prepare_allows(self, sequence: int, view: int, pp_msg: PBFTMessage) -> bool:
        raise NotImplementedError

    def _vc_floor(self, sequence: int) -> int | None:
        raise NotImplementedError

    def _vc_commit_lock(self, sequence: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def _durable_prepared(self, sequence: int) -> tuple[int, str] | None:
        raise NotImplementedError

    def _vc_commit_lock_arm(
        self, sequence: int, view: int, block_hash: str, commit: dict[str, Any], proof: list[dict[str, Any]]
    ) -> bool:
        raise NotImplementedError

    def _lock_proof_msgs(self, key: str, block_hash: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _vc_prepared_arm(self, sequence: int, view: int, block_hash: str) -> bool:
        raise NotImplementedError

    def _vc_proposal_store(
        self, sequence: int, block_hash: str, payload: dict[str, Any], sender: str, view: int | None = None
    ) -> bool:
        raise NotImplementedError

    def _vc_quorum(self, sequence: int) -> int:
        raise NotImplementedError

    def _body_hash_recomputes(self, body: Any, block_hash: str) -> bool:
        raise NotImplementedError

    async def _handle_proposal_fetch(self, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def _handle_proposal_body(self, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def _vc_proposal_get(self, sequence: int, block_hash: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def _view_change_permit(self, sequence: int, view: int, block_hash: str) -> bool:
        raise NotImplementedError

    def _view_change_commit_allows(self, sequence: int, view: int, block_hash: str) -> bool:
        raise NotImplementedError


from .pbft_intake import _IntakeMixin
from .pbft_phases import _PhasesMixin
from .pbft_vc_engine import _VcEngineMixin


class PBFTConsensus(_PhasesMixin, _IntakeMixin, _VcEngineMixin):
    """PBFT consensus implementation"""
