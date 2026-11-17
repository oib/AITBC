"""PBFT VIEW_CHANGE / NEW_VIEW engine runtime, split out of ``pbft.py``.

Pure code motion: the methods below are the dormant #2005 F3-C protocol
runtime on ``PBFTConsensus`` — VC/NEW_VIEW send, receive, store, verify and
the prepare/commit vote gates — unchanged, now living on ``_VcEngineMixin``.
Every method stays gated by ``view_change_active(sequence)``: while
``pbft_view_change_height`` is unset the engine is byte-identical to the
pre-#2005 rotation behavior. Flood caps (``MAX_VC_BUCKETS``,
``MAX_NV_BUCKETS``, ``MAX_VC_SET_ENTRIES``, ``MAX_LOCK_PROOF_MSGS``,
``MAX_VC_BUCKETS_PER_SENDER``) and signature/digest verification order are
preserved exactly; nothing here arms the protocol.

Import ``aitbc_chain.consensus.pbft`` (it wires these mixins into
``PBFTConsensus``); this module is not meant to be imported directly.
"""

from __future__ import annotations

import time
from typing import Any

from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..metrics import metrics_registry
from .pbft import PBFTMessage, _PbftBaseMixin, _int_key_seq, logger
from .block_hash import compute_block_hash
from .pbft_quorum import pbft_required_messages
from .pbft_view_change import (
    MAX_LOCK_PROOF_MSGS,
    MAX_NV_BUCKETS,
    MAX_VC_BUCKETS,
    MAX_VC_BUCKETS_PER_SENDER,
    MAX_VC_SET_ENTRIES,
    NV_MESSAGE_TYPE,
    VC_MESSAGE_TYPE,
    cross_author_reproposal_active,
    new_view_digest,
    nv_signed_message,
    proposal_body_bound,
    proposal_body_signed,
    scheduled_proposer,
    select_forced_hash,
    vc_signed_message,
    verify_new_view,
    verify_vc_lock_proof,
    verify_view_change,
    view_change_active,
    view_change_digest,
)


class _VcEngineMixin(_PbftBaseMixin):
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

    def _body_hash_recomputes(self, body: Any, block_hash: str) -> bool:
        """Whether the body's own fields reproduce ``block_hash`` (#2171 rework).

        The proposer's header signature covers the hash label and roots, not
        the transaction list, so a bound + signed body can still carry a
        substituted tx set. Recompute the canonical block hash over the body;
        fail closed on anything malformed.
        """
        if not isinstance(body, dict):
            return False
        txs = body.get("transactions")
        if not isinstance(txs, list):
            return False
        tx_hashes: list[str] = []
        for tx in txs:
            tx_hash = tx.get("tx_hash") if isinstance(tx, dict) else None
            if not isinstance(tx_hash, str) or not tx_hash:
                return False
            tx_hashes.append(tx_hash)
        height, parent, proposer, timestamp = (body.get(k) for k in ("height", "parent_hash", "proposer", "timestamp"))
        if (
            body.get("chain_id") != self._chain_id
            or not isinstance(height, int)
            or not isinstance(parent, str)
            or not isinstance(proposer, str)
            or not isinstance(timestamp, str)
        ):
            return False
        try:
            computed = compute_block_hash(
                self._chain_id,
                height,
                parent,
                timestamp,
                tx_hashes,
                proposer,
                body.get("state_root"),
                body.get("bridge_state_root"),
                body.get("aux_state_root"),
            )
        except (TypeError, ValueError):
            return False
        return computed.lower() == block_hash.lower()

    def _cross_author_exempt(self, sequence: int, view: int | None, block_hash: str, sender: str) -> bool:
        """#2171: R4 exemption for a locked re-proposal by the scheduled proposer.

        Only under a verified locked NEW_VIEW at ``(sequence, view)`` whose
        selected hash is exactly ``block_hash`` and whose sender is the
        pre-prepare sender; the body's author signature is still checked by
        the caller.
        """
        if view is None or not cross_author_reproposal_active(sequence):
            return False
        entry = self._new_views.get((sequence, view))
        if entry is None or entry.get("kind") != "locked" or entry.get("selected") != block_hash:
            return False
        expected = self._vc_expected_proposer(sequence, view)
        return canonical_address(str(expected or "")) == canonical_address(sender)

    def _vc_proposal_store(
        self, sequence: int, block_hash: str, payload: dict[str, Any], sender: str, view: int | None = None
    ) -> bool:
        # #2133 R4: the body's self-declared proposer must be the authenticated
        # pre-prepare sender (itself checked against the schedule at intake).
        # #2171: except a locked re-proposal by the scheduled proposer.
        if canonical_address(str(payload.get("proposer", ""))) != canonical_address(sender) and not (
            self._cross_author_exempt(sequence, view, block_hash, sender) and self._body_hash_recomputes(payload, block_hash)
        ):
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
        if not self._vc_proposal_store(sequence, block_hash, block_payload, self._local_validator or "", view):
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
                pp_msg._proposal_persisted = self._vc_proposal_store(
                    sequence, pp_msg.block_hash, pp_msg.block, pp_msg.sender, view
                )
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
