"""PBFT prepare/commit/execute pipeline, split out of ``pbft.py``.

Pure code motion: the methods below are the ``PBFTConsensus`` phases —
pre-prepare, prepare, commit, execute, re-seal, quorum waits, commit locks
and commit-certificate production — unchanged, now living on
``_PhasesMixin`` so ``pbft.py`` stays a facade. Dormant-gate behavior is
preserved exactly: ``view_change_active`` / ``cross_view_commit_lock_active``
/ ``strict_certificate_active`` still resolve False while their heights are
unset, and every gate reads ``settings`` at call time as before.

Import ``aitbc_chain.consensus.pbft`` (it wires these mixins into
``PBFTConsensus``); this module is not meant to be imported directly.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..metrics import metrics_registry
from .pbft import (
    BODY_FETCH_WAIT_SECONDS,
    MAX_BODY_WANTED,
    PBFTMessage,
    PBFTMessageType,
    _PbftBaseMixin,
    logger,
)
from . import pbft_trace
from .pbft_certificate import strict_certificate_active, validate_commit_certificate
from .pbft_cross_view import cross_view_commit_lock_active
from .pbft_view_change import (
    PB_MESSAGE_TYPE,
    PF_MESSAGE_TYPE,
    cross_author_reproposal_active,
    proposal_body_bound,
    proposal_body_signed,
    select_forced_hash,
    view_change_active,
)


class _PhasesMixin(_PbftBaseMixin):
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

    def _forced_locked_hash(self, sequence: int, view: int) -> str | None:
        """The hash a locked NEW_VIEW forces at ``(sequence, view)`` (#2171).

        From the verified NEW_VIEW when held, else recomputed from the local
        VIEW_CHANGE bucket once it reaches quorum (the scheduled proposer builds
        its NEW_VIEW from that same set). ``None`` for a free selection or when
        no quorum is visible yet.
        """
        entry = self._new_views.get((sequence, view))
        if entry is not None:
            selected = entry.get("selected")
            return selected if entry.get("kind") == "locked" and isinstance(selected, str) and selected else None
        bucket = self._vc_messages.get((sequence, view), {})
        by_sender = {canonical_address(str(vc.get("sender", ""))): vc for vc in bucket.values()}
        if len(by_sender) < self._vc_quorum(sequence):
            return None
        kind, selected = select_forced_hash(by_sender)
        return selected if kind == "locked" and selected else None

    def _locked_reproposal(self, sequence: int, fresh_hash: str, view: int | None = None) -> tuple[str, dict[str, Any]] | None:
        """The commit-locked ``(hash, body)`` this node must re-propose (#2157).

        Only while the view-change gate is armed at ``sequence``, a durable
        commit lock exists for a hash other than the fresh block's, the body
        is held, signed, bound to that hash, and this node is the body's own
        proposer (#2133 R4 requires body proposer == pre-prepare sender).

        #2171: with ``pbft_locked_cross_author_height`` armed the hash comes
        from the locked NEW_VIEW selection and the author check is dropped —
        the narrow R4 exemption in ``_vc_proposal_store`` lets followers
        accept the author-signed body from the scheduled proposer.
        """
        if not view_change_active(sequence):
            return None
        forced = None
        if view is not None and cross_author_reproposal_active(sequence):
            forced = self._forced_locked_hash(sequence, view)
        locked_hash: Any
        if forced:
            locked_hash = forced
        else:
            lock = self._vc_commit_lock(sequence)
            locked_hash = lock.get("block_hash") if isinstance(lock, dict) else None
        if not isinstance(locked_hash, str) or not locked_hash or locked_hash == fresh_hash:
            return None
        body = self._vc_proposal_get(sequence, locked_hash)
        if body is None or not proposal_body_bound(body, locked_hash, sequence):
            return None
        if not forced and canonical_address(str(body.get("proposer", ""))) != canonical_address(str(self._local_validator)):
            return None
        return locked_hash, body

    async def _ensure_locked_body(self, sequence: int, view: int) -> None:
        """Fetch the locked body the NEW_VIEW forces when this node lacks it (#2171)."""
        if not cross_author_reproposal_active(sequence) or self._gossip_backend is None:
            return
        locked_hash = self._forced_locked_hash(sequence, view)
        if not locked_hash or self._vc_proposal_get(sequence, locked_hash) is not None:
            return
        if len(self._body_wanted) >= MAX_BODY_WANTED:
            self._body_wanted.clear()
        self._body_wanted[(sequence, locked_hash)] = view
        request = {
            "message_type": PF_MESSAGE_TYPE,
            "sender": self._local_validator,
            "sequence_number": sequence,
            "view_number": view,
            "block_hash": locked_hash,
        }
        deadline = time.time() + BODY_FETCH_WAIT_SECONDS
        try:
            while time.time() < deadline:
                await self._gossip_backend.publish(f"pbft.{PF_MESSAGE_TYPE}.{self._chain_id}", request)
                metrics_registry.increment("pbft_locked_body_fetch_requested_total")
                for _ in range(4):
                    if self._vc_proposal_get(sequence, locked_hash) is not None:
                        return
                    await asyncio.sleep(0.25)
        finally:
            self._body_wanted.pop((sequence, locked_hash), None)

    async def _handle_proposal_fetch(self, data: dict[str, Any]) -> None:
        """Answer a locked-body request from the proposal store (#2171)."""
        seq, block_hash = data.get("sequence_number"), data.get("block_hash")
        if not isinstance(seq, int) or isinstance(seq, bool) or not isinstance(block_hash, str):
            return
        if not cross_author_reproposal_active(seq) or self._gossip_backend is None:
            return
        view = data.get("view_number")
        lock = self._vc_commit_lock(seq)
        local_lock = lock.get("block_hash") if isinstance(lock, dict) else None
        forced = self._forced_locked_hash(seq, view) if isinstance(view, int) and not isinstance(view, bool) else None
        if block_hash not in (forced, local_lock):
            return  # only ever serve the hash a lock or locked NEW_VIEW forces
        body = self._vc_proposal_get(seq, block_hash)
        if body is None or not proposal_body_bound(body, block_hash, seq):
            return
        now = time.time()
        if now - self._fetch_answered.get((seq, block_hash), 0.0) < 2.0:
            return
        if len(self._fetch_answered) >= MAX_BODY_WANTED:
            for stale in [k for k, t in self._fetch_answered.items() if now - t > 10.0]:
                self._fetch_answered.pop(stale, None)
            if len(self._fetch_answered) >= MAX_BODY_WANTED:
                return  # table full of live entries: drop, never reset the limiter
        self._fetch_answered[(seq, block_hash)] = now
        response = {
            "message_type": PB_MESSAGE_TYPE,
            "sender": self._local_validator,
            "sequence_number": seq,
            "block_hash": block_hash,
            "block": body,
        }
        await self._gossip_backend.publish(f"pbft.{PB_MESSAGE_TYPE}.{self._chain_id}", response)
        metrics_registry.increment("pbft_locked_body_fetch_answered_total")

    def _handle_proposal_body(self, data: dict[str, Any]) -> None:
        """Store a fetched locked body: only when requested, bound and author-signed (#2171)."""
        seq, block_hash, body = data.get("sequence_number"), data.get("block_hash"), data.get("block")
        if not isinstance(seq, int) or isinstance(seq, bool) or not isinstance(block_hash, str):
            return
        if (seq, block_hash) not in self._body_wanted:
            return  # unsolicited
        if (
            not proposal_body_bound(body, block_hash, seq)
            or not proposal_body_signed(body)
            or not self._body_hash_recomputes(body, block_hash)
        ):
            metrics_registry.increment("pbft_locked_body_fetch_refused_total")
            return
        fn = getattr(self.consensus, "pbft_vc_proposal_store", None)
        if callable(fn) and fn(seq, block_hash, body):
            metrics_registry.increment("pbft_locked_body_fetch_stored_total")

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
        t_body = time.time()
        await self._ensure_locked_body(pre_prepare_sequence, pre_prepare_view)
        pbft_trace.trace(
            "propose.locked_body", hr=key, dur=f"{time.time() - t_body:.3f}", since_start=f"{time.time() - started_at:.3f}"
        )
        locked = self._locked_reproposal(pre_prepare_sequence, block_hash, pre_prepare_view)
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
        pbft_trace.trace("propose.pre_prepare_out", hr=key, since_start=f"{time.time() - started_at:.3f}")
        pre_prepare_msg = self.state.pre_prepare_messages.get(key)
        if not pre_prepare_msg:
            logger.warning("PBFT propose_and_wait aborted: missing pre-prepare for seq %s", pre_prepare_sequence)
            return False

        # Send our own prepare; it will trigger a local commit once a prepare quorum forms
        await self.prepare_phase(self._local_validator, pre_prepare_msg)
        pbft_trace.trace("propose.own_prepare", hr=key, since_start=f"{time.time() - started_at:.3f}")

        # Wait for enough prepares (other validators respond via handle_incoming_message)
        deadline = time.time() + timeout if timeout else None
        if not await self._wait_for_quorum(
            key, self.state.prepared_messages, "prepare", deadline, started_at, pre_prepare_sequence, pre_prepare_view
        ):
            return False
        pbft_trace.trace("propose.prepare_quorum", hr=key, since_start=f"{time.time() - started_at:.3f}")

        # Wait for enough commits
        if not await self._wait_for_quorum(
            key, self.state.committed_messages, "commit", deadline, started_at, pre_prepare_sequence, pre_prepare_view
        ):
            return False

        pbft_trace.trace("propose.commit_quorum", hr=key, since_start=f"{time.time() - started_at:.3f}")
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
                    "PBFT %s quorum timeout for key %s (required=%s, have=%s, duration=%.3fs) %s",
                    phase,
                    key,
                    self.required_messages,
                    len(messages.get(key, [])),
                    duration,
                    pbft_trace.describe_quorum_gap(list(self.consensus.get_consensus_participants()), messages.get(key, [])),
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
                pbft_trace.trace(
                    "refuse.prepare", hr=f"{height}:{view}", reason="already_prepared_later_round", prepared_view=prepared_view
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
                pbft_trace.trace("refuse.prepare", hr=f"{height}:{view}", reason="second_block_same_round")
                return False
        if key in self._local_prepared:
            return len(self.state.prepared_messages.get(key, [])) >= self.required_messages
        # #2005 F3-C: while the VIEW_CHANGE gate is armed this node may
        # only prepare a block the verified NEW_VIEW for (height, view)
        # permits — and only after its proposal body is persisted
        # (Option R). Both checks are dormant while the gate is unset.
        if not await self._view_change_prepare_allows(height, view, pre_prepare_msg):
            pbft_trace.trace("refuse.prepare", hr=f"{height}:{view}", reason="view_change_not_allowed")
            return False
        # The durable prepared record persists BEFORE the prepare is
        # broadcast — a restart must not forget this vote (design §7).
        if view_change_active(height) and not self._vc_prepared_arm(height, view, pre_prepare_msg.block_hash):
            pbft_trace.trace("refuse.prepare", hr=f"{height}:{view}", reason="vc_prepared_arm_failed")
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
            except Exception:  # noqa: BLE001
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
        except Exception:  # noqa: BLE001
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
