"""Byzantine-equivalence detection and slashing for ``MultiValidatorPoA``
(#1860 pure-move split).

Holds the prepare/commit vote stores' equivocation scanners, the dormant
cross-view COMMIT double-sign evidence path (#1940 F3-A / #2005 excuse
rules), the byzantine-threshold deactivation gate (#2158 quorum floor),
operator reactivation, and the attestation-equivocation recorder. The
facade ``MultiValidatorPoA`` inherits this mixin on top of ``_StateMixin``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from . import multi_validator_poa as _mvpoa
from .multi_validator_poa import _StateMixin, _cross_view_message_shape, ValidatorRole

if TYPE_CHECKING:
    import logging

    logger: logging.Logger
else:
    logger = _mvpoa.logger


class _EquivocationMixin(_StateMixin):
    """Vote-equivocation detection, evidence, and slashing (#1860 split)."""

    @staticmethod
    def _vote_record_fields(message: Any) -> dict[str, Any]:
        """Signed-field subset of a PBFTMessage for equivocation evidence (#1263).

        Exactly the fields ``PBFTConsensus._sign_message``/``_verify_message_signature``
        cover plus ``block_hash`` — everything on-chain verification needs to
        rebuild the signed preimage and recover the signer.
        """
        if message is None:
            return {}
        message_type = getattr(message, "message_type", None)
        return {
            "message_type": getattr(message_type, "value", message_type),
            "sender": getattr(message, "sender", ""),
            "view_number": getattr(message, "view_number", None),
            "sequence_number": getattr(message, "sequence_number", None),
            "digest": getattr(message, "digest", ""),
            "block_hash": getattr(message, "block_hash", ""),
            "signature": getattr(message, "signature", ""),
        }

    @staticmethod
    def _vote_sequence(record: dict[str, Any]) -> int | None:
        """Strict-int sequence a recorded vote carries, else None (unknown)."""
        seq = record.get("sequence_number")
        return seq if isinstance(seq, int) and not isinstance(seq, bool) else None

    @classmethod
    def _same_vote_slot(cls, a: dict[str, Any], b: dict[str, Any]) -> bool:
        """#2147: two votes occupy one slot only at the same ``(sequence, view)``.

        The round (view) is timestamp-derived and repeats across heights, so
        honest votes at different sequences share a view; keying on the view
        alone flagged them as equivocation and deactivated every validator.
        A vote whose sequence is unknown (legacy ``message=None`` records)
        cannot be exonerated, so it keeps the pre-#2147 view-only behaviour
        against anything in the same round.
        """
        seq_a, seq_b = cls._vote_sequence(a), cls._vote_sequence(b)
        return seq_a is None or seq_b is None or seq_a == seq_b

    def _record_phase_vote(
        self,
        store: dict[str, list[dict[str, Any]]],
        validator: str,
        block_hash: str,
        round: int,
        message: Any = None,
    ) -> bool:
        """Record a prepare/commit vote; a same-round conflicting digest is
        Byzantine evidence and triggers detection immediately."""
        if validator not in self.validators:
            return False

        if validator not in store:
            store[validator] = []

        record = {"block_hash": block_hash, "round": round, "timestamp": time.time(), **self._vote_record_fields(message)}

        # Check for conflicting messages (Byzantine detection)
        for msg in store[validator]:
            if msg["round"] == round and msg["block_hash"] != block_hash and self._same_vote_slot(msg, record):
                # B4: conflicting message detected — reject and trigger slashing (C2 + C6)
                store[validator].append(record)
                self.detect_byzantine_behavior(validator)
                return False

        store[validator].append(record)

        # #1940 F3-A: a commit vote on an armed sequence can complete a
        # cross-view equivocation pair — run detection. The cross-view scan
        # inside ``detect_byzantine_behavior`` is gated per-record by
        # ``cross_view_commit_lock_active`` and commit-store only, so this is
        # a no-op while the gate is unset; ``apply_slashing`` dedup keeps
        # re-observation free. Prepare votes never trigger it — cross-view
        # prepare rotation is the current liveness mechanism.
        if store is self.commit_messages:
            from .pbft_cross_view import cross_view_commit_lock_active

            if cross_view_commit_lock_active(record.get("sequence_number")):
                self.detect_byzantine_behavior(validator)

        return True

    def record_prepare(self, validator: str, block_hash: str, round: int, *, message: Any = None) -> bool:
        """Record a prepare message from a validator"""
        return self._record_phase_vote(self.prepare_messages, validator, block_hash, round, message=message)

    def record_commit(self, validator: str, block_hash: str, round: int, *, message: Any = None) -> bool:
        """Record a commit message from a validator (#1235).

        Symmetric to ``record_prepare``: the canonical PBFT slashable
        offense is committing two different digests at the same round —
        before this the COMMIT branch deduped silently and left zero
        slashing evidence.
        """
        return self._record_phase_vote(self.commit_messages, validator, block_hash, round, message=message)

    def detect_byzantine_behavior(self, validator: str) -> bool:
        """Detect if a validator exhibited Byzantine behavior and apply slashing (B4 / C2).

        Scans both the prepare and commit vote stores (#1235) — equivocation
        in either phase is the same slashable offense.

        #1206: every conflicting round is evaluated, not just the first —
        ``rounds`` is insertion-ordered, so returning early re-found the
        oldest recorded equivocation on every call and never reached newer
        offenses (previously masked because ``apply_slashing`` re-appended
        the same event and inflated the slash count). The dedup guard in
        ``apply_slashing`` now makes re-scanning safe: an already-recorded
        offense returns False without double-charging.
        """
        detected = False
        for store in (self.prepare_messages, self.commit_messages):
            messages = store.get(validator)
            if not messages or len(messages) < 2:
                continue

            # Check for conflicting messages in the same (sequence, round) slot (#2147)
            for round_num, sequence, block_hashes in self._conflicting_vote_slots(messages):
                detected = True
                event = self._vote_equivocation_event(validator, store, messages, round_num, block_hashes, sequence)
                if event is None or validator not in self.validators:
                    continue
                self._apply_equivocation_slash(validator, event)

        # #1940 F3-A: dormant cross-view COMMIT equivocation scan — runs after
        # the same-round scan above, commit store only, gated per record by
        # ``cross_view_commit_lock_active(sequence_number)``. Unset gate =
        # byte-identical pre-F3-A behavior.
        if self._detect_cross_view_commit_equivocations(validator):
            detected = True

        return detected

    @classmethod
    def _conflicting_vote_slots(cls, messages: list[dict[str, Any]]) -> list[tuple[int, int | None, set[str]]]:
        """#2147: ``(round, sequence, hashes)`` for every slot with 2+ block hashes.

        Slots are ``(sequence, round)``. A record with an unknown sequence
        joins every slot of its round (it cannot be exonerated); when a
        round has no known sequence at all the unknown records form one slot.
        """
        by_round: dict[int, list[dict[str, Any]]] = {}
        for msg in messages:
            by_round.setdefault(msg["round"], []).append(msg)
        found: list[tuple[int, int | None, set[str]]] = []
        for round_num, records in by_round.items():
            known = sorted({seq for r in records if (seq := cls._vote_sequence(r)) is not None})
            slots: list[int | None] = list(known) if known else [None]
            for sequence in slots:
                hashes = {r["block_hash"] for r in records if cls._vote_sequence(r) in (None, sequence)}
                if len(hashes) > 1:
                    found.append((round_num, sequence, hashes))
        return found

    def _detect_cross_view_commit_equivocations(self, validator: str) -> bool:
        """Slash a validator that COMMIT two different block hashes at the
        same sequence across different PBFT views (#1940 F3-A).

        Only fully signed commit records qualify (``message=`` capture —
        ``message_type == "commit"``, strict-int ``sequence_number`` /
        ``view_number``, non-empty ``block_hash``/``digest``/``signature``,
        and ``sender`` canonical-matching the store key): anything less could
        never satisfy the on-chain evidence gate, so it produces no event at
        all. Within one armed ``sequence_number`` a conflict needs BOTH a
        different ``view_number`` AND a different ``block_hash`` — the same
        hash re-committed in a later view is legal rotation, and same-view
        hash conflicts remain the existing ``vote_equivocation`` path.
        One canonical pair per ``(validator, sequence)`` is evidenced (the
        lexicographically smallest conflicting record pair under
        ``(view_number, block_hash.lower(), signature)``, so observation
        order cannot change the evidence); the ``apply_slashing`` dedup key —
        extended for this kind to cover sequence + view pair — keeps
        re-observation from double-charging.
        """
        messages = self.commit_messages.get(validator)
        if not messages or len(messages) < 2 or validator not in self.validators:
            return False

        by_sequence: dict[int, list[dict[str, Any]]] = {}
        for msg in messages:
            if self._cross_view_record_eligible(msg, validator):
                # eligibility guarantees a strict-int sequence_number
                by_sequence.setdefault(msg["sequence_number"], []).append(msg)

        detected = False
        for sequence in sorted(by_sequence):
            seq_msgs = by_sequence[sequence]
            views = {m["view_number"] for m in seq_msgs}
            hashes = {str(m["block_hash"]).lower() for m in seq_msgs}
            if len(views) < 2 or len(hashes) < 2:
                continue  # single view or single hash across views — not equivocation

            # Canonical conflicting pair: the smallest key over all
            # unordered record pairs with different view AND different hash
            # — observation order cannot change the evidence. Computed in
            # O(k log k) (#2128): the O(k^2) pair enumeration ran on every
            # armed commit receipt, so k commits at one sequence cost O(k^3).
            best_pair = self._canonical_cross_view_pair(seq_msgs)
            if best_pair is None:
                continue
            msg_a = {k: best_pair[0].get(k) for k in self._VOTE_EVIDENCE_FIELDS}
            msg_b = {k: best_pair[1].get(k) for k in self._VOTE_EVIDENCE_FIELDS}
            justification = self._cross_view_unlock_justification(sequence, msg_a, msg_b)
            event = self._slashing_manager.cross_view_vote_equivocation_event(
                validator, sequence, "commit", msg_a, msg_b, unlock_justification=justification
            )
            if justification is not None and self._cross_view_pair_justified(event, justification, sequence):
                # #2005 r3: the later commit followed a verified NEW_VIEW that
                # permits it — protocol-sanctioned, not a double-sign. The same
                # proof rides the evidence so peers and the chain apply path
                # excuse it identically.
                # #1940 F3: excusing the canonical pair must not hide another
                # conflicting pair whose later vote is NOT sanctioned.
                event = self._first_unjustified_cross_view_event(validator, sequence, seq_msgs)
                if event is None:
                    continue
            self._apply_equivocation_slash(validator, event)
            detected = True
        return detected

    @staticmethod
    def _cross_view_later_candidates(seq_msgs: list[dict[str, Any]]):
        """Yield ``(earlier, later)`` conflicting record pairs, one per distinct
        later ``(view, hash)``, in deterministic ``(view, hash)`` order (#1940 F3).

        ``earlier`` is the first record in ``_cross_view_message_order`` with a
        lower view and a different hash — found from a running prefix in
        O(1), so the whole scan is O(k log k). A NEW_VIEW excuses a pair by its
        LATER vote only, so one candidate per later ``(view, hash)`` covers
        every pair the excuse can distinguish."""
        from .slashing import _cross_view_message_order

        ordered = sorted(seq_msgs, key=_cross_view_message_order)
        first: dict[str, Any] | None = None
        first_diff: dict[str, Any] | None = None
        i = 0
        while i < len(ordered):
            view = ordered[i]["view_number"]
            j = i
            while j < len(ordered) and ordered[j]["view_number"] == view:
                j += 1
            group = ordered[i:j]
            seen: set[str] = set()
            for rec in group:
                h = str(rec["block_hash"]).lower()
                if h in seen or first is None:
                    continue
                seen.add(h)
                earlier = first if str(first["block_hash"]).lower() != h else first_diff
                if earlier is not None:
                    yield earlier, rec
            for rec in group:
                if first is None:
                    first = rec
                elif first_diff is None and str(rec["block_hash"]).lower() != str(first["block_hash"]).lower():
                    first_diff = rec
            i = j

    def _first_unjustified_cross_view_event(self, validator: str, sequence: int, seq_msgs: list[dict[str, Any]]) -> Any:
        """The event for the first conflicting pair whose later vote no verified
        NEW_VIEW permits, or None when every conflicting pair is excused.

        At most two NEW_VIEW verifications per view: a free NEW_VIEW permits
        every hash, a locked one exactly one, so two distinct hashes that both
        verify prove the whole view is sanctioned."""
        sanctioned: dict[int, int] = {}
        for earlier, later in self._cross_view_later_candidates(seq_msgs):
            view = later["view_number"]
            if sanctioned.get(view, 0) >= 2:
                continue
            msg_a = {k: earlier.get(k) for k in self._VOTE_EVIDENCE_FIELDS}
            msg_b = {k: later.get(k) for k in self._VOTE_EVIDENCE_FIELDS}
            justification = self._cross_view_unlock_justification(sequence, msg_a, msg_b)
            event = self._slashing_manager.cross_view_vote_equivocation_event(
                validator, sequence, "commit", msg_a, msg_b, unlock_justification=justification
            )
            if justification is not None and self._cross_view_pair_justified(event, justification, sequence):
                sanctioned[view] = sanctioned.get(view, 0) + 1
                continue
            return event
        return None

    def _cross_view_unlock_justification(
        self, sequence: int, msg_a: dict[str, Any], msg_b: dict[str, Any]
    ) -> dict[str, Any] | None:
        """The engine's verified NEW_VIEW for the pair's higher view, or None."""
        engine = getattr(self, "_pbft_engine", None)
        producer = getattr(engine, "view_change_unlock_justification", None)
        if not callable(producer):
            return None
        views = [v for v in (msg_a.get("view_number"), msg_b.get("view_number")) if isinstance(v, int)]
        if not views:
            return None
        result = producer(sequence, max(views))
        return result if isinstance(result, dict) else None

    def _cross_view_pair_justified(self, event: Any, justification: dict[str, Any], sequence: int) -> bool:
        """Verify the proof exactly as the apply path does (same function, same set)."""
        import json

        from .equivocation_policy import VcApplyContext, view_change_justified

        try:
            payload = json.loads(event.evidence)
        except (TypeError, ValueError):
            return False
        ctx = VcApplyContext(
            chain_id=self.chain_id,
            sequence=sequence,
            validator_set=self.pbft_vc_validator_set(sequence),
        )
        return view_change_justified(payload, justification, ctx)

    def _cross_view_record_eligible(self, msg: dict[str, Any], validator: str) -> bool:
        """Fully-signed COMMIT record bound to ``validator`` on an armed
        sequence — the store-key sender must canonical-match and the
        sequence must be at/above the dormant cross-view commit-lock gate."""
        from .pbft_cross_view import cross_view_commit_lock_active

        return (
            _cross_view_message_shape(msg)
            and canonical_address(str(msg.get("sender", ""))) == canonical_address(validator)
            and cross_view_commit_lock_active(msg.get("sequence_number"))
        )

    @staticmethod
    def _canonical_cross_view_pair(seq_msgs: list[dict[str, Any]]):
        """The canonical conflicting ``(lo, hi)`` record pair for one armed
        sequence — byte-identical to ``min`` over all conflicting pairs under
        ``_cross_view_pair_key`` (#2128), computed in O(k log k).

        Records are sorted by ``_cross_view_message_order`` —
        ``(view_number, block_hash.lower(), signature)`` — which is exactly
        the pair-key ordering restricted to a single side of the pair.
        ``lo`` is the first sorted record that has ANY conflicting partner:
        the pair key leads with ``(lo.view, lo.hash)``, so the global min's
        first element is the smallest ``(view, hash, signature)`` record that
        can pair at all. Every partner of ``lo`` must sort after it (a
        partner sorting before ``lo`` would itself have a partner and would
        have been chosen instead). ``hi`` is then the first sorted record
        after ``lo`` with a different ``view_number`` AND a different
        ``block_hash`` — the minimum ``(view, hash, signature)`` partner,
        which is exactly what the pair key's trailing fields select.

        Partner existence for a record ``(v, h)`` is decided in O(1) from
        per-view hash-set counts: a conflicting partner needs a record with
        view ``!= v`` and hash ``!= h``. ``bad_total(h)`` counts views whose
        hash-set is not exactly ``{h}`` (each supplies a record with hash
        ``!= h``); view ``v`` itself is subtracted via ``v_bad`` when its own
        hash-set contains something other than ``h`` — that view does not
        count as a "different view".
        """
        from .slashing import _cross_view_message_order

        ordered = sorted(seq_msgs, key=_cross_view_message_order)
        if len(ordered) < 2:
            return None

        hashes_by_view: dict[int, set[str]] = {}
        for msg in ordered:
            hashes_by_view.setdefault(msg["view_number"], set()).add(str(msg["block_hash"]).lower())
        total_views = len(hashes_by_view)
        sig_counts: dict[frozenset, int] = {}
        for view_hashes in hashes_by_view.values():
            key = frozenset(view_hashes)
            sig_counts[key] = sig_counts.get(key, 0) + 1

        def _has_partner(msg: dict[str, Any]) -> bool:
            h = str(msg["block_hash"]).lower()
            bad_total = total_views - sig_counts.get(frozenset({h}), 0)
            v_bad = 1 if hashes_by_view[msg["view_number"]] - {h} else 0
            return bad_total - v_bad > 0

        lo = next((msg for msg in ordered if _has_partner(msg)), None)
        if lo is None:
            return None
        lo_view = lo["view_number"]
        lo_hash = str(lo["block_hash"]).lower()
        seen_lo = False
        for msg in ordered:
            if msg is lo:
                seen_lo = True
                continue
            if not seen_lo:
                continue
            if msg["view_number"] != lo_view and str(msg["block_hash"]).lower() != lo_hash:
                return lo, msg
        return None  # unreachable: _has_partner(lo) guarantees a partner after lo

    @staticmethod
    def _cross_view_conflicting_pairs(seq_msgs: list[dict[str, Any]]):
        """Yield canonically-ordered ``(lo, hi)`` record pairs that conflict:
        different ``view_number`` AND different ``block_hash``.

        Retained as the brute-force reference for tests pinning
        ``_canonical_cross_view_pair`` exact-equivalence (#2128); production
        detection no longer enumerates pairs."""
        from .slashing import _cross_view_message_order

        for i in range(len(seq_msgs)):
            for j in range(i + 1, len(seq_msgs)):
                ra, rb = seq_msgs[i], seq_msgs[j]
                if ra["view_number"] != rb["view_number"] and str(ra["block_hash"]).lower() != str(rb["block_hash"]).lower():
                    yield tuple(sorted((ra, rb), key=_cross_view_message_order))

    @staticmethod
    def _cross_view_pair_key(pair: tuple[dict[str, Any], dict[str, Any]]) -> tuple:
        """Deterministic ordering key for a conflicting record pair."""
        lo, hi = pair
        return (
            lo["view_number"],
            str(lo["block_hash"]).lower(),
            hi["view_number"],
            str(hi["block_hash"]).lower(),
            str(lo.get("signature", "")),
            str(hi.get("signature", "")),
        )

    def _apply_equivocation_slash(self, validator: str, event: Any) -> None:
        """Levy an equivocation event and run the shared byzantine-threshold
        deactivation/advisory block (#1940 F3-A review).

        Every slashable equivocation — same-round ``vote_equivocation`` and
        armed cross-view COMMIT evidence alike — feeds the same counter and
        the same threshold gate, so a cross-view double-sign cannot bypass
        deactivation by arriving through the newer path. The caller-side
        dormant gating is unchanged: this only runs when an event was
        actually produced.
        """
        self._slashing_manager.apply_slashing(self.validators[validator], event)
        # Deactivate validator once byzantine threshold is reached.
        # #1198: with chain slashing armed this write is
        # advisory-only — selection reads on-chain
        # validator_deactivation markers instead, so a
        # node-local flip here would reintroduce exactly the
        # divergence the row exists to remove.
        if (
            self._slashing_manager.get_validator_slash_count(validator, event.condition)
            >= settings.consensus_byzantine_threshold
        ):
            if self._chain_slashing_armed():
                logger.warning(
                    "Byzantine threshold reached for %s — advisory only "
                    "(CONSENSUS_CHAIN_SLASHING_ENABLED): submit a "
                    "VALIDATOR_DEACTIVATE tx to deactivate on-chain",
                    validator,
                )
            elif self._deactivation_floor_refuses(validator):
                # #2158: the event is recorded and the stake slashed above;
                # only the membership flip is withheld, so a wrongful-slash
                # bug cannot take the active set below quorum (drill-1: all
                # four validators deactivated, permanent halt).
                from ..metrics import metrics_registry

                health = self.quorum_health()
                episode_key = canonical_address(validator)
                if self._floor_refusals_seen.get(episode_key) == health["active"]:
                    return  # same episode (#2165): already counted and logged
                self._floor_refusals_seen[episode_key] = health["active"]
                metrics_registry.increment("consensus_deactivation_floor_refused_total")
                logger.critical(
                    "Byzantine threshold reached for %s but deactivation REFUSED: it would leave %s active of %s "
                    "configured, below the quorum of %s. Operator review required (#2158)",
                    validator,
                    health["active"] - 1,
                    health["configured"],
                    health["required"],
                )
            else:
                self.validators[validator].is_active = False
                # Persist the deactivation — a restart must not clear
                # a byzantine verdict and reset the slash history.
                self.save_state()

    def quorum_health(self) -> dict[str, Any]:
        """Active vs configured validators and the PBFT quorum of the configured set (#2158).

        ``configured`` counts proposer/validator-role entries regardless of
        ``is_active`` (a deactivated validator keeps its role, so it is still
        part of the configured set). ``required`` is the quorum of that
        configured set, never of the shrinking active set.
        """
        from ..metrics import metrics_registry
        from .pbft_quorum import pbft_required_messages

        configured = sum(1 for v in self.validators.values() if v.role in (ValidatorRole.PROPOSER, ValidatorRole.VALIDATOR))
        active = len(self.get_consensus_participants())
        required = pbft_required_messages(configured) if configured else 0
        below = configured > 0 and active < required
        metrics_registry.set_gauge("consensus_active_below_quorum", 1.0 if below else 0.0)
        return {"configured": configured, "active": active, "required": required, "below_quorum": below}

    def _deactivation_floor_refuses(self, validator: str) -> bool:
        """Whether deactivating ``validator`` would leave fewer active than the configured quorum."""
        target = canonical_address(validator)
        if target not in {canonical_address(a) for a in self.get_consensus_participants()}:
            return False  # already out of the active set: nothing changes
        health = self.quorum_health()
        return bool(health["active"] - 1 < health["required"])

    def reactivation_refusal(self) -> str | None:
        """Why a confirmed reactivation would be refused right now, or None (#2165)."""
        if self._chain_slashing_armed():
            return "chain slashing is armed: deactivation is an on-chain marker, not local state"
        return None

    @staticmethod
    def _in_configured_validator_set(address: str) -> bool:
        import json

        raw = getattr(settings, "validator_set", "")
        if not raw:
            return False
        try:
            members = json.loads(raw)
        except ValueError:
            return False
        return any(
            canonical_address(str(m.get("address", ""))) == canonical_address(address) for m in members if isinstance(m, dict)
        )

    def reactivate_validator(self, address: str, reason: str) -> bool:
        """Operator re-activation of a locally deactivated validator (#2158).

        Legacy (node-local) regime only: with chain slashing armed the
        canonical state is the on-chain marker and a local flip would diverge.
        Requires a non-empty reason, writes an audit log line and persists.
        Returns False when the validator is unknown or already active.

        #2165: a validator removed through ``remove_validator`` or an env diff was also
        demoted to STANDBY, which ``get_consensus_participants`` excludes, so flipping
        ``is_active`` alone would leave it inert. When it is still in the configured
        ``VALIDATOR_SET`` its VALIDATOR role is restored; otherwise the role is left
        alone and the audit line says so.
        """
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reactivation requires a non-empty reason")
        refusal = self.reactivation_refusal()
        if refusal:
            raise ValueError(refusal)
        key = next((k for k in self.validators if canonical_address(k) == canonical_address(address)), None)
        if key is None or self.validators[key].is_active:
            return False
        validator = self.validators[key]
        validator.is_active = True
        role_note = ""
        if validator.role not in (ValidatorRole.PROPOSER, ValidatorRole.VALIDATOR):
            if self._in_configured_validator_set(key):
                validator.role = ValidatorRole.VALIDATOR
                role_note = "; role restored to validator"
            else:
                role_note = "; role stays standby (not in the configured validator set)"
        logger.warning("AUDIT validator %s re-activated by operator (#2158); reason: %s%s", key, reason.strip(), role_note)
        from ..metrics import metrics_registry

        metrics_registry.increment("consensus_validator_reactivated_total")
        self.save_state()
        return True

    _VOTE_EVIDENCE_FIELDS = ("message_type", "sender", "view_number", "sequence_number", "digest", "block_hash", "signature")

    def _vote_equivocation_event(
        self,
        validator: str,
        store: dict[str, list[dict[str, Any]]],
        messages: list[dict[str, Any]],
        round_num: int,
        block_hashes: set[str],
        sequence: int | None = None,
    ):
        """Build the slashing event for one conflicting round (#1263).

        When both conflicting votes retained their signed PBFTMessage fields
        (``message=`` was passed to ``record_prepare``/``record_commit``) the
        event carries a ``vote_equivocation`` payload on-chain verification
        can check; otherwise it falls back to the legacy free-text
        ``detect_double_sign`` record — advisory-only, never gate-satisfying.
        """
        phase = "prepare" if store is self.prepare_messages else "commit"
        by_hash: dict[str, dict[str, Any]] = {}
        for msg in messages:
            if (
                msg.get("round") == round_num
                and msg.get("block_hash") in block_hashes
                and self._vote_sequence(msg) in (None, sequence)
            ):
                by_hash.setdefault(msg["block_hash"], msg)
        signed = [{k: m.get(k) for k in self._VOTE_EVIDENCE_FIELDS} for m in list(by_hash.values())[:2]]
        if (
            len(signed) == 2
            and all(all(m.get(k) is not None for k in self._VOTE_EVIDENCE_FIELDS) for m in signed)
            and all(m.get("signature") and m.get("digest") for m in signed)
        ):
            return self._slashing_manager.vote_equivocation_event(validator, round_num, phase, signed[0], signed[1])
        hashes_list = sorted(block_hashes, key=str.lower)
        return self._slashing_manager.detect_double_sign(validator, hashes_list[0], hashes_list[1], round_num)

    def get_slashing_history(self):
        """Get slashing history (delegates to SlashingManager)"""
        return self._slashing_manager.get_slashing_history()

    def record_attestation_equivocation(
        self,
        validator_address: str,
        height: int,
        round_number: int | None,
        block_hash_a: str,
        block_hash_b: str,
        proposer: str = "",
        attestations: list[dict] | None = None,
        justification: str | None = None,
        unlock_justification: dict | None = None,
        persist: bool = True,
    ):
        """Record attestation equivocation on this chain's SlashingManager and persist (#1198/#1263).

        Routes attestation-layer double-sign evidence into the same per-chain
        manager that backs ``draft_deactivation_txs``, ``evidence_bundle``,
        ``ConsensusState.slashing_events_json``, and ``/slashing-history``.
        ``attestations`` carries the two signed attestation records when both
        signatures are retained — the material on-chain verification needs.

        ``persist=False`` (#1278 fix) records in memory only; the caller owns
        the later ``save_state()``. The proposer-side recorder runs while the
        proposal's DB session holds the sqlite write lock, so a synchronous
        save on its own connection would block the event loop for the busy
        timeout.
        """
        event = self._slashing_manager.record_attestation_equivocation(
            validator_address=validator_address,
            height=height,
            round_number=round_number,
            block_hash_a=block_hash_a,
            block_hash_b=block_hash_b,
            proposer=proposer,
            attestations=attestations,
            justification=justification,
            unlock_justification=unlock_justification,
            accused_stake=self._accused_stake(validator_address),
        )
        if persist:
            self.save_state()
        return event

    def _accused_stake(self, validator_address: str) -> Any:
        """Stake of the accused validator, or None when it is not in the set (#2130)."""
        from aitbc.crypto.signature_recovery import canonical_address

        target = canonical_address(validator_address)
        for addr, validator in (getattr(self, "validators", None) or {}).items():
            if addr == validator_address or canonical_address(addr) == target:
                return validator.stake
        return None
