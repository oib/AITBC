"""Persisted consensus state and chain-visible validator state for
``MultiValidatorPoA`` (#1860 pure-move split).

Holds ``__init__`` (so every attribute the mixins touch is declared on the
root of the MRO), validator-set mutation, the on-chain deactivation-marker
reads, ``save_state``/``load_state`` and the slashing-history parsers, and
the PBFT commit-lock / VIEW_CHANGE record accessors. ``MultiValidatorPoA``
in ``multi_validator_poa.py`` inherits this mixin; every name remains
importable from the facade module.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..models import Block
from . import multi_validator_poa as _mvpoa
from .multi_validator_poa import Validator, ValidatorRole, _is_strict_int

if TYPE_CHECKING:
    import logging

    logger: logging.Logger
else:
    logger = _mvpoa.logger


class _StateMixin:
    """Validator state, persistence, and chain-visible reads (#1860 split)."""

    def __init__(
        self,
        chain_id: str,
        load_state: bool = True,
        *,
        chain_state_session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
    ):
        if not settings.multi_validator_consensus_enabled:
            raise RuntimeError(
                "MultiValidatorPoA is not yet activated. "
                "Set multi_validator_consensus_enabled=true in config to enable (requires security review)."
            )
        self.chain_id = chain_id
        self.validators: dict[str, Validator] = {}
        self.current_proposer_index = 0
        self.round_robin_enabled = True
        self.consensus_timeout = 30  # seconds

        # Network partition tracking
        self.network_partitioned = False
        self.last_partition_healed = 0.0
        self.partitioned_validators: set[str] = set()

        # Byzantine fault tolerance tracking
        self.prepare_messages: dict[str, list[dict[str, Any]]] = {}  # validator -> list of prepare messages
        self.commit_messages: dict[str, list[dict[str, Any]]] = {}  # validator -> list of commit messages (#1235)
        self.consensus_attempts: int = 0
        # #2165: validators whose deactivation the floor already refused, mapped to the
        # active count at that moment; a repeat verdict at the same active count is the
        # same episode and must not re-fire the CRITICAL log / counter.
        self._floor_refusals_seen: dict[str, int] = {}

        # B3: block signature verification toggle
        self._require_block_signatures: bool = getattr(settings, "bridge_block_signature_required", True)

        # B4: slashing manager (imported here to avoid circular import at module load)
        from .slashing import SlashingManager

        self._slashing_manager = SlashingManager(chain_id=self.chain_id)

        # B5: validator-set epoch rotation was removed (#848) — it was never
        # invoked, and the strategies in rotation.py demoted validators beyond
        # the top slots to STANDBY, so wiring it would have dropped part of the
        # live set. Proposer selection stays per-height/round round-robin in
        # select_proposer. _current_epoch remains as a persisted snapshot field
        # (always 0 — no epoch transitions exist).
        self._current_epoch = 0

        # B11: PBFT view/sequence tracking (persisted)
        self._pbft_view: int = 0
        self._pbft_sequence: int = 0

        # #1940 F3-B: this node's cross-view PBFT commit locks —
        # sequence_number -> committed block_hash, persisted on
        # ConsensusState.pbft_commit_locks_json so a restart cannot forget a
        # vote. Only armed while ``cross_view_commit_lock_active`` is true;
        # empty/dormant otherwise and pruned below the newest armed height.
        self._pbft_commit_locks: dict[int, str] = {}

        # #2005 F3-C: per-height VIEW_CHANGE protocol state — floor (highest
        # view this node sent a VC for), prepared (view, hash), commit_lock
        # (view, hash, own signed COMMIT) and persisted proposal bodies.
        # Persisted on ConsensusState.pbft_view_change_json; dormant while
        # ``view_change_active`` is false and pruned below the current
        # sequence exactly like the F3-B commit locks.
        self._pbft_view_change: dict[int, dict[str, Any]] = {}
        self._pbft_vc_corrupt = False

        # #1940 F4: optional session factory for chain-state reads
        # (_current_head_height / _chain_deactivated_addresses). The
        # attestation post-state probe injects one bound to its scratch
        # session so speculative schedule/deactivation checks can never open
        # a production session_scope. None keeps the production default.
        self._chain_state_session_factory = chain_state_session_factory

        if load_state:
            self.load_state()

    def add_validator(self, address: str, stake: Decimal | float | str = Decimal("1000")) -> bool:
        """Add a new validator to the consensus"""
        if address in self.validators:
            return False

        # Coercion boundary: callers pass whatever they have, this normalises once so that
        # nothing downstream ever sees a float stake.
        self.validators[address] = Validator(
            address=address,
            stake=Decimal(str(stake)),
            reputation=1.0,
            role=ValidatorRole.STANDBY,
            last_proposed=0,
            is_active=True,
        )
        return True

    def get_consensus_participants(self) -> list[str]:
        """Get list of active consensus participants"""
        deactivated = self._chain_deactivated_addresses(self._current_head_height())
        return [
            v.address
            for v in self.validators.values()
            if v.is_active
            and v.role in [ValidatorRole.PROPOSER, ValidatorRole.VALIDATOR]
            and canonical_address(v.address) not in deactivated
        ]

    def pbft_vc_validator_set(self, sequence: int) -> frozenset[str]:
        """Canonical VC member set at ``sequence`` (#2133 item 1).

        Same derivation as the on-chain apply (``vc_active_set``): all
        configured validators minus chain deactivation markers at or below
        ``sequence - 1`` — NOT the local ``is_active``/role view, which is
        off-chain state the apply path cannot see.
        """
        from .pbft_view_change import vc_active_set

        marked = self._chain_deactivated_addresses(sequence - 1)
        return vc_active_set(self.validators, [(a, None) for a in marked], sequence)

    # ─── #1198: consensus-visible slashing state ─────────────────

    def _chain_slashing_armed(self) -> bool:
        """Whether slash-driven deactivation reads chain state (default off)."""
        return bool(getattr(settings, "consensus_chain_slashing_enabled", False))

    def _chain_state_session(self) -> AbstractContextManager[Session]:
        """Session scope for chain-state reads (#1940 F4).

        An injected factory (the attestation probe's scratch session) wins;
        otherwise the production ``session_scope`` — query text and defaults
        are identical either way.
        """
        if self._chain_state_session_factory is not None:
            return self._chain_state_session_factory()
        from ..database import session_scope

        return session_scope(self.chain_id)

    def _current_head_height(self) -> int | None:
        """Local chain tip height, or None when unreadable (treated as "no
        markers yet" — the same view pre-#1198 nodes always had)."""
        from sqlmodel import func, select

        try:
            with self._chain_state_session() as session:
                return session.exec(select(func.max(Block.height)).where(Block.chain_id == self.chain_id)).one()
        except (SQLAlchemyError, OSError, RuntimeError) as e:
            # #1940 F4: injected scratch-session reads verify snapshot state —
            # a failure must refuse, not degrade to "no markers". The
            # production session_scope path keeps the legacy fallback.
            if self._chain_state_session_factory is not None:
                raise
            logger.warning("Failed to read chain head for %s: %s", self.chain_id, e)
            return None

    def _chain_deactivated_addresses(self, upto_height: int | None) -> frozenset[str]:
        """Validator addresses carrying an on-chain deactivation marker (#1198).

        Markers with ``block_height <= upto_height`` apply; ``None`` means all
        markers regardless of height (migration reporting). Returns empty when
        the flag is off — callers then get byte-identical legacy behavior —
        and on read failure (logged; availability over silent correctness,
        the divergence report surfaces the gap).
        """
        if not self._chain_slashing_armed():
            return frozenset()
        from sqlmodel import select

        from ..base_models import ValidatorDeactivation

        try:
            with self._chain_state_session() as session:
                rows = session.exec(
                    select(ValidatorDeactivation.validator_address, ValidatorDeactivation.block_height).where(
                        ValidatorDeactivation.chain_id == self.chain_id
                    )
                ).all()
            # The table holds at most one row per validator — filter heights
            # in Python rather than fighting SQLModel's Optional-column typing.
            return frozenset(
                canonical_address(addr)
                for addr, height in rows
                if upto_height is None or height is None or height <= upto_height
            )
        except (SQLAlchemyError, OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            # #1940 F4: injected scratch-session reads verify snapshot state —
            # a failure must refuse, not degrade to "no markers". The
            # production session_scope path keeps the legacy fallback.
            if self._chain_state_session_factory is not None:
                raise
            logger.error("Failed to read validator_deactivation for %s: %s", self.chain_id, e)
            return frozenset()

    def chain_slashing_divergence_report(self) -> list[dict[str, Any]]:
        """Validators locally deactivated vs on-chain markers (#1198 migration).

        One entry per ``is_active=False`` validator: ``on_chain_marker`` says
        whether canonical chain state independently excludes it. Run at
        flag-arming time; entries with ``on_chain_marker=False`` are the
        locally-deactivated validators that need a drafted
        ``VALIDATOR_DEACTIVATE`` or an explicit operator re-activation
        decision — canonical state wins for selection either way.
        """
        deactivated = self._chain_deactivated_addresses(None)
        return [
            {
                "address": addr,
                "canonical_address": canonical_address(addr),
                "on_chain_marker": canonical_address(addr) in deactivated,
            }
            for addr, v in self.validators.items()
            if not v.is_active
        ]

    def _report_slashing_divergence(self) -> None:
        """Log + count locally-deactivated validators lacking on-chain markers.

        Runs once per ``load_state`` while ``CONSENSUS_CHAIN_SLASHING_ENABLED``
        is armed: canonical chain state wins for selection immediately, so a
        locally-deactivated validator without a marker re-enters the active
        set — this report is the operator's list of who needs a drafted
        ``VALIDATOR_DEACTIVATE`` (or an explicit re-activation decision)
        before/just after arming.
        """
        from ..metrics import metrics_registry

        try:
            report = self.chain_slashing_divergence_report()
        except (SQLAlchemyError, OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.warning("Slashing divergence report failed for %s: %s", self.chain_id, e)
            return
        for entry in report:
            metrics_registry.increment("consensus_slashing_divergence_total")
            logger.warning(
                "Slashing divergence #%s: validator %s is locally deactivated but has %s on-chain marker",
                self.chain_id,
                entry["address"],
                "an" if entry["on_chain_marker"] else "NO",
            )

    # ─── B11: State Persistence ───────────────────────────────────

    def save_state(self) -> bool:
        """Persist consensus state to DB (survives node restart).

        Saves validator set, PBFT view/sequence, epoch, and slashing
        history to the ConsensusState table. Called at init, after every
        validator-set mutation (removal, byzantine deactivation, epoch
        rotation), and on graceful shutdown.
        """
        import json

        from datetime import UTC, datetime

        from ..base_models import ConsensusState
        from ..database import session_scope

        validator_set = {
            addr: {
                "stake": str(v.stake),
                "reputation": v.reputation,
                "role": v.role.value,
                "last_proposed": v.last_proposed,
                "is_active": v.is_active,
            }
            for addr, v in self.validators.items()
        }
        # V23-48: `slash_amount` here held the *rate*, and the amount actually deducted was
        # never written down at all. Both are recorded now, plus the stake they were computed
        # from, so a penalty can be audited after the fact. Money goes out as a decimal
        # string; json.dumps cannot serialise a Decimal and float() would undo the point.
        # #1263: the record shape lives in slashing.slashing_event_record — the
        # VALIDATOR_DEACTIVATE v2 evidence payload must be byte-identical.
        from .slashing import slashing_event_record

        self._slashing_manager.bound_for_persist()  # #2131 (no-op while the limit is 0)
        slashing_events: list[dict[str, Any]] = [
            slashing_event_record(e) for e in self._slashing_manager.get_slashing_history()
        ]
        if self._slashing_manager.pruned_summary:
            slashing_events.append({"_pruned_summary": self._slashing_manager.pruned_summary})
        # #1940 F3-B: str(seq) -> block_hash, keys in ascending int order so
        # the persisted bytes are deterministic regardless of insertion order.
        commit_locks_json = json.dumps({str(seq): self._pbft_commit_locks[seq] for seq in sorted(self._pbft_commit_locks)})
        # #2005 F3-C: str(seq) -> VC record, keys in ascending int order so
        # the persisted bytes are deterministic regardless of insertion order.
        view_change_json = json.dumps(
            {str(seq): self._pbft_view_change[seq] for seq in sorted(self._pbft_view_change)},
            sort_keys=True,
        )
        try:
            with session_scope(self.chain_id) as session:
                existing = session.query(ConsensusState).filter_by(chain_id=self.chain_id).first()
                if existing:
                    existing.current_view = self._pbft_view
                    existing.current_sequence = self._pbft_sequence
                    existing.current_epoch = self._current_epoch
                    existing.validator_set_json = json.dumps(validator_set)
                    existing.slashing_events_json = json.dumps(slashing_events)
                    existing.pbft_commit_locks_json = commit_locks_json
                    existing.pbft_view_change_json = view_change_json
                    existing.updated_at = datetime.now(UTC)
                else:
                    session.add(
                        ConsensusState(
                            chain_id=self.chain_id,
                            current_view=self._pbft_view,
                            current_sequence=self._pbft_sequence,
                            current_epoch=self._current_epoch,
                            validator_set_json=json.dumps(validator_set),
                            slashing_events_json=json.dumps(slashing_events),
                            pbft_commit_locks_json=commit_locks_json,
                            pbft_view_change_json=view_change_json,
                        )
                    )
                # session_scope closes without committing — without this the
                # write above was silently rolled back on every call and
                # consensus_state stayed empty fleet-wide.
                session.commit()
            return True
        except (SQLAlchemyError, ArithmeticError, OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error("Failed to save consensus state for %s: %s", self.chain_id, e)
            return False

    @staticmethod
    def _split_pruned_summary(records: list[Any]) -> tuple[list[Any], dict[str, dict]]:
        """Separate the #2131 ``_pruned_summary`` marker record from the event records."""
        summary: dict[str, dict] = {}
        events: list[Any] = []
        for rec in records:
            if isinstance(rec, dict) and "_pruned_summary" in rec:
                summary = dict(rec["_pruned_summary"])
            else:
                events.append(rec)
        return events, summary

    @staticmethod
    def _parse_slashing_events(records: list[dict[str, Any]]) -> list[Any]:
        """Rebuild SlashingEvents from persisted JSON, tolerating the pre-V23-48 shape.

        Records written before V23-48 carry `slash_amount` holding the *rate*, and no
        `slashed_amount` at all -- the deducted quantity was never stored, so for those events
        it is genuinely unknown and stays None. `calculate_total_slashed` skips them rather
        than guessing, which means a total computed over old history is a lower bound and says
        so by omission. Re-deriving it is impossible: the stake at the time is not recorded.
        """
        from .slashing import SlashingCondition, SlashingEvent

        def _decimal_or_none(value: Any) -> Decimal | None:
            return None if value is None else Decimal(str(value))

        events = []
        for record in records:
            try:
                evidence, round_number, hash_a, hash_b = _StateMixin._canonical_evidence_fields(record)
                events.append(
                    SlashingEvent(
                        validator_address=record["validator_address"],
                        condition=SlashingCondition(record["condition"]),
                        evidence=evidence,
                        block_height=record.get("block_height", 0),
                        timestamp=record.get("timestamp", 0.0),
                        # legacy key first, since it is what old rows have
                        slash_rate=float(record.get("slash_rate", record.get("slash_amount", 0.0))),
                        stake_before=_decimal_or_none(record.get("stake_before")),
                        slashed_amount=_decimal_or_none(record.get("slashed_amount")),
                        round_number=round_number,
                        hash_a=hash_a,
                        hash_b=hash_b,
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning("Skipping unreadable slashing record %s: %s", record, e)
        return events

    @staticmethod
    def _canonical_evidence_fields(record: dict[str, Any]) -> tuple[str, int | None, str, str]:
        """Canonical equivocation fields for a persisted slashing record (#1206).

        New records carry ``round_number``/``hash_a``/``hash_b`` directly. Legacy
        ``attestation_equivocation`` records only have them inside the evidence
        JSON — and possibly in observation order — so they are extracted and
        re-serialized canonically (sorted hash pair) here, making pre-#1206
        rows hash-identical to freshly recorded ones.
        """
        import json

        evidence = record.get("evidence", "")
        round_number = record.get("round_number")
        hash_a = record.get("hash_a") or ""
        hash_b = record.get("hash_b") or ""
        try:
            payload = json.loads(evidence) if isinstance(evidence, str) else None
        except (TypeError, ValueError):
            payload = None
        if isinstance(payload, dict) and payload.get("kind") in (
            "attestation_equivocation",
            "vote_equivocation",
            "pbft_cross_view_vote_equivocation",
        ):
            from .slashing import PBFT_CROSS_VIEW_VOTE_EQUIVOCATION, _cross_view_message_order, _sorted_hash_pair

            kind = payload.get("kind")
            if kind in ("vote_equivocation", PBFT_CROSS_VIEW_VOTE_EQUIVOCATION):
                # The hash pair lives inside messages[] for vote evidence.
                vote_hashes = [str(m.get("block_hash", "")) for m in payload.get("messages", []) if isinstance(m, dict)]
                a, b = _sorted_hash_pair(vote_hashes[0] if vote_hashes else "", vote_hashes[1] if len(vote_hashes) > 1 else "")
            else:
                a, b = _sorted_hash_pair(str(payload.get("block_hash_a") or ""), str(payload.get("block_hash_b") or ""))
                payload["block_hash_a"], payload["block_hash_b"] = a, b
            # #1263: signature-bearing sub-records canonicalize by their hash
            # too, so observation order cannot change the persisted evidence.
            # #1940 F3-A: cross-view commit evidence orders messages by
            # (view_number, block_hash, signature) — the same key the event
            # builder used — so the persisted record stays byte-identical.
            for key, sort_field in (("attestations", "hash"), ("messages", "block_hash")):
                entries = payload.get(key)
                if isinstance(entries, list):
                    if key == "messages" and kind == PBFT_CROSS_VIEW_VOTE_EQUIVOCATION:
                        # Non-dict entries sort last-ish with a neutral key and
                        # are preserved — the same degrade-in-place treatment
                        # the same-view path gives malformed sub-records (the
                        # on-chain verifier rejects them; parsing must not).
                        payload[key] = sorted(
                            entries,
                            key=lambda e: _cross_view_message_order(e) if isinstance(e, dict) else (-1, "", ""),
                        )
                    else:
                        payload[key] = sorted(
                            entries, key=lambda e: str(e.get(sort_field, "")).lower() if isinstance(e, dict) else ""
                        )
            evidence = json.dumps(payload, sort_keys=True)
            hash_a, hash_b = a, b
            if round_number is None and payload.get("kind") == "attestation_equivocation":
                round_number = payload.get("round")
        return evidence, round_number, hash_a, hash_b

    def deactivate_absent_from(self, env_addresses: set[str]) -> list[str]:
        """Mark validators missing from the env set inactive; return their addresses.

        The persisted ConsensusState row would otherwise keep a validator that
        was dropped from ``VALIDATOR_SET`` alive in the proposer rotation
        forever: ``load_state`` restores the row and ``add_validator`` only
        knows how to add. Env stays the membership source of truth — this
        applies the removal side. A validator that is env-present but
        row-inactive stays inactive: re-enabling a deactivated validator is a
        deliberate act, not an env diff.

        #693: an empty ``env_addresses`` while validators are registered is a
        sentinel for a broken env read (empty/misparsed ``VALIDATOR_SET``),
        not a fleet-wide removal. Applying it deactivates every validator and
        ``save_state`` persists the wipe, so the active consensus set reads
        empty until manual repair — the hub1 2026-10-28 incident. Refuse the
        diff; a genuine full removal is done by deactivating each member, not
        by passing an empty env set.
        """
        if not env_addresses and self.validators:
            logger.error(
                "Refusing to deactivate the entire validator set: env diff is empty "
                "but %d validators are registered — treating it as a bad VALIDATOR_SET "
                "read, not a mass removal",
                len(self.validators),
            )
            return []
        deactivated = []
        for addr, validator in self.validators.items():
            if addr not in env_addresses and validator.is_active:
                validator.is_active = False
                validator.role = ValidatorRole.STANDBY
                deactivated.append(addr)
        if deactivated:
            self.save_state()
        return deactivated

    def _load_validator_set_from_settings(self) -> bool:
        """Load validators from settings when no persisted state is available."""
        import json

        validator_set = getattr(settings, "validator_set", "")
        if not validator_set:
            return False
        for v in json.loads(validator_set):
            self.add_validator(v.get("address"), Decimal(str(v.get("stake", "1000"))))
            if v.get("address") in self.validators:
                self.validators[v["address"]].role = ValidatorRole.VALIDATOR
                self.validators[v["address"]].is_active = True
        return True

    def load_state(self, *, slashing: bool = True) -> bool:
        """Load consensus state from DB on node startup.

        ``slashing=False`` leaves the in-memory slashing history untouched and
        never reads the ``slashing_events_json`` column (#2143): read-only RPC
        routes that only need validators/view/epoch must not pay for a history
        blob that reached 67 MB on hub. With ``slashing=True`` the parsed
        history is cached by the row fingerprint, so repeat loads of an
        unchanged row skip the JSON parse.
        """
        import json

        from sqlalchemy import func
        from sqlalchemy.orm import defer
        from sqlmodel import col

        from ..base_models import ConsensusState
        from ..database import session_scope

        try:
            with session_scope(self.chain_id) as session:
                row = (
                    session.query(ConsensusState)
                    .options(defer(ConsensusState.slashing_events_json))  # type: ignore[arg-type]
                    .filter_by(chain_id=self.chain_id)
                    .first()
                )
                if not row:
                    return self._load_validator_set_from_settings()
                self._pbft_view = row.current_view
                self._pbft_sequence = row.current_sequence
                self._current_epoch = row.current_epoch
                validator_set = json.loads(row.validator_set_json) if row.validator_set_json else {}
                self.validators = {}
                for addr, v_data in validator_set.items():
                    self.validators[addr] = Validator(
                        address=addr,
                        stake=Decimal(str(v_data.get("stake", "1000"))),
                        reputation=v_data.get("reputation", 1.0),
                        role=ValidatorRole(v_data.get("role", "standby")),
                        last_proposed=v_data.get("last_proposed", 0),
                        is_active=v_data.get("is_active", True),
                    )
                # V23-48: this used to say the history was "loaded for read-only inspection"
                # and that "the SlashingManager rebuilds its internal state lazily". Neither
                # was true -- slashing_events_json was written and never read, so every
                # penalty was forgotten on restart. That reset get_validator_slash_count to
                # zero, which reset the thresholds: a validator two strikes into a three-strike
                # unavailability rule started over each time the node came back.
                if slashing:
                    blob_len = (
                        session.query(func.length(col(ConsensusState.slashing_events_json)))
                        .filter(col(ConsensusState.chain_id) == self.chain_id)
                        .scalar()
                    )
                    self._load_slashing_history(session, ConsensusState, (row.updated_at, blob_len))
                # #1940 F3-B: restore this node's cross-view commit locks.
                # Entries below the persisted current sequence can never be
                # voted on again, so they are pruned on load as well as on arm.
                self._pbft_commit_locks = {
                    seq: block_hash
                    for seq, block_hash in self._parse_commit_locks(getattr(row, "pbft_commit_locks_json", "") or "").items()
                    if seq >= self._pbft_sequence
                }
                # #2005 F3-C: restore per-height VIEW_CHANGE state (floor,
                # prepared, commit-lock, proposal bodies). Same prune rule:
                # heights below the persisted current sequence can never be
                # voted on again.
                try:
                    self._pbft_view_change = {
                        seq: rec
                        for seq, rec in self._parse_view_change_records(
                            getattr(row, "pbft_view_change_json", "") or ""
                        ).items()
                        if seq >= self._pbft_sequence
                    }
                    self._pbft_vc_corrupt = False
                except ValueError as exc:
                    # Fail CLOSED (#2005 review): a corrupt record may have held
                    # a floor or lock; forgetting it is restart amnesia, so every
                    # VC-armed vote is refused until an operator repairs the row.
                    logger.error("pbft_view_change_json corrupt (%s): VC-armed votes refused", exc)
                    self._pbft_view_change = {}
                    self._pbft_vc_corrupt = True
            if self._chain_slashing_armed():
                self._report_slashing_divergence()
            return True
        except (
            ImportError,
            SQLAlchemyError,
            ArithmeticError,
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
        ) as e:
            logger.error("Failed to load consensus state for %s: %s", self.chain_id, e)
            return self._load_validator_set_from_settings()

    def _load_slashing_history(self, session: Any, model: Any, fingerprint: tuple[Any, Any]) -> None:
        """Restore the persisted slashing history, parsing only when the row changed.

        ``fingerprint`` is ``(updated_at, length(blob))``: ``save_state`` rewrites
        ``updated_at`` on every write, so an equal fingerprint means the stored
        blob is byte-for-byte the one parsed last time (#2143). The cache holds
        the capped parse result; a hit hands the manager a fresh list copy.
        """
        import json

        from .slashing import _max_events_per_height, cap_history_per_height

        cap = _max_events_per_height()
        cached = getattr(self, "_slashing_load_cache", None)
        if cached is not None and cached[0] == (fingerprint, cap):
            self._slashing_manager.slashing_events = list(cached[1])
            self._slashing_manager.pruned_summary = dict(cached[2])
            return
        raw = session.query(model.slashing_events_json).filter(model.chain_id == self.chain_id).scalar()
        records, summary = self._split_pruned_summary(json.loads(raw) if raw else [])
        events = cap_history_per_height(self._parse_slashing_events(records), cap)
        self._slashing_manager.pruned_summary = summary
        self._slashing_manager.slashing_events = events
        self._slashing_load_cache = ((fingerprint, cap), list(events), dict(summary))

    @staticmethod
    def _parse_commit_locks(raw: Any) -> dict[int, str]:
        """Rebuild ``{sequence: block_hash}`` commit locks from persisted JSON.

        Tolerant like ``_parse_slashing_events``: a malformed row yields ``{}``
        rather than failing the whole load. Keys must parse to non-negative
        ints and values must be non-empty strings; anything else is dropped.
        """
        import json

        try:
            data = json.loads(raw) if isinstance(raw, str) and raw else {}
        except (TypeError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        locks: dict[int, str] = {}
        for key, value in data.items():
            try:
                seq = int(key)
            except (TypeError, ValueError):
                continue
            if seq < 0 or not isinstance(value, str) or not value:
                continue
            locks[seq] = value
        return locks

    # ─── #1940 F3-B: cross-view commit locks ─────────────────────

    def pbft_commit_locks(self) -> dict[int, str]:
        """Snapshot of this node's persisted cross-view commit locks."""
        return dict(self._pbft_commit_locks)

    def pbft_commit_lock_get(self, sequence: int) -> str | None:
        """The committed ``block_hash`` locked at ``sequence``, if any."""
        return self._pbft_commit_locks.get(sequence)

    def pbft_commit_lock_arm(self, sequence: int, block_hash: str) -> bool:
        """Persist ``sequence -> block_hash`` as this node's commit lock.

        Called BEFORE the commit is broadcast (#1940 F3-B): a restart must
        not forget the vote. Locks for lower sequences are pruned — they can
        never be voted on again once a higher height arms. Fails closed like
        the #1268 vote journal: a ``save_state`` failure restores the
        previous in-memory state and returns False so the caller must not
        emit the commit.
        """
        pruned = {seq: self._pbft_commit_locks.pop(seq) for seq in [s for s in self._pbft_commit_locks if s < sequence]}
        previous = self._pbft_commit_locks.get(sequence)
        had_previous = sequence in self._pbft_commit_locks
        self._pbft_commit_locks[sequence] = block_hash
        if self.save_state():
            return True
        self._pbft_commit_locks.update(pruned)
        if had_previous:
            self._pbft_commit_locks[sequence] = previous  # type: ignore[assignment]
        else:
            self._pbft_commit_locks.pop(sequence, None)
        return False

    # ─── #2005 F3-C: VIEW_CHANGE protocol state ─────────────────
    #
    # One record per height: {"floor": int, "prepared": {"view","block_hash"}|None,
    # "commit_lock": {"view","block_hash","commit"}|None, "proposals": {hash: payload}}.
    # Every mutation persists BEFORE the corresponding network message may be
    # sent (design §7: write record, then broadcast; a write failure means no
    # message — the #1268 vote-journal precedent). All of it is dormant while
    # ``view_change_active(sequence)`` is false.

    def pbft_vc_records(self) -> dict[int, dict[str, Any]]:
        """Snapshot of the persisted per-height VIEW_CHANGE records."""
        return {seq: dict(rec) for seq, rec in self._pbft_view_change.items()}

    def _pbft_vc_record(self, sequence: int) -> dict[str, Any]:
        return self._pbft_view_change.setdefault(
            sequence, {"floor": None, "prepared": None, "commit_lock": None, "proposals": {}}
        )

    def pbft_vc_floor(self, sequence: int) -> int | None:
        """Highest view this node has sent a VIEW_CHANGE for at ``sequence``."""
        rec = self._pbft_view_change.get(sequence)
        if rec is None:
            return None
        floor = rec.get("floor")
        return floor if _is_strict_int(floor) else None

    def pbft_vc_commit_lock(self, sequence: int) -> dict[str, Any] | None:
        """This node's persisted commit-lock record at ``sequence``, if any."""
        rec = self._pbft_view_change.get(sequence)
        if rec is None:
            return None
        lock = rec.get("commit_lock")
        return dict(lock) if isinstance(lock, dict) else None

    def pbft_vc_proposal_get(self, sequence: int, block_hash: str) -> dict[str, Any] | None:
        """A persisted proposal body for ``(sequence, block_hash)``, if held."""
        rec = self._pbft_view_change.get(sequence)
        if rec is None:
            return None
        proposals = rec.get("proposals")
        if not isinstance(proposals, dict):
            return None
        payload = proposals.get(block_hash)
        return dict(payload) if isinstance(payload, dict) else None

    def _pbft_vc_mutate(self, sequence: int, mutator: Any) -> bool:
        """Apply ``mutator(record)`` to the height's VC record and persist.

        Fail closed like ``pbft_commit_lock_arm``: the in-memory record is
        restored on ``save_state`` failure and False is returned so the
        caller must not emit the gated message. Heights below ``sequence``
        are pruned — they can never be voted on again.
        """
        import copy

        if self._pbft_vc_corrupt:
            return False
        pruned = {seq: self._pbft_view_change.pop(seq) for seq in [s for s in self._pbft_view_change if s < sequence]}
        had_previous = sequence in self._pbft_view_change
        previous = copy.deepcopy(self._pbft_view_change.get(sequence))
        rec = self._pbft_vc_record(sequence)
        mutator(rec)
        if self.save_state():
            return True
        self._pbft_view_change.update(pruned)
        if had_previous and previous is not None:
            self._pbft_view_change[sequence] = previous
        else:
            self._pbft_view_change.pop(sequence, None)
        return False

    def pbft_vc_floor_raise(self, sequence: int, view: int) -> bool:
        """Persist ``floor(sequence) = max(floor, view)`` — before any VC send.

        The floor rule (#2005 §3): once raised, this node must never send
        PREPARE/COMMIT for the height at a lower view. Idempotent: a view at
        or below the stored floor is a no-op success.
        """
        current = self.pbft_vc_floor(sequence)
        if current is not None and view <= current:
            return True

        def _raise(rec: dict[str, Any]) -> None:
            rec["floor"] = view

        return self._pbft_vc_mutate(sequence, _raise)

    def pbft_vc_prepared_arm(self, sequence: int, view: int, block_hash: str) -> bool:
        """Persist this node's latest prepared ``(view, block_hash)``.

        Mirrors ``_prepared_heights`` but durable: only a strictly higher
        view replaces the record (same-view hash changes are refused by the
        caller before this runs).
        """
        rec_existing = self._pbft_view_change.get(sequence)
        existing = rec_existing.get("prepared") if rec_existing else None
        if isinstance(existing, dict):
            existing_view = existing.get("view")
            if _is_strict_int(existing_view) and isinstance(existing_view, int) and view <= existing_view:
                return True

        def _arm(rec: dict[str, Any]) -> None:
            rec["prepared"] = {"view": view, "block_hash": block_hash}

        return self._pbft_vc_mutate(sequence, _arm)

    def pbft_vc_commit_lock_arm(
        self, sequence: int, view: int, block_hash: str, commit: dict[str, Any], proof: list[dict[str, Any]]
    ) -> bool:
        """Persist this node's commit-lock ``{view, block_hash, commit, proof}``.

        ``proof`` is the PREPARE quorum certificate (#2005 Q1) carried inside
        VIEW_CHANGE ``lock.msgs``; an empty proof is refused — a lock no peer
        can verify must not be armed. ``commit`` is the node's own COMMIT. A
        different hash is refused; the same hash re-arms at a strictly higher
        view (the floor + NEW_VIEW rules make that later commit legal, and the
        F3-B ``pbft_commit_lock_arm`` already guards emission).
        """
        if not proof:
            return False
        existing = self.pbft_vc_commit_lock(sequence)
        if existing is not None:
            if str(existing.get("block_hash", "")).lower() != block_hash.lower():
                return False
            raw_view = existing.get("view")
            if not _is_strict_int(raw_view) or not isinstance(raw_view, int):
                return False
            existing_view = raw_view
            # #2005 r3: the SAME hash may advance to a higher view — a NEW_VIEW
            # that selects ("locked", H) makes a node that committed H at v
            # commit it again at v' > v, and without the advance that second
            # commit aborts before broadcast forever (permanent stall at n=4,
            # q=3 with two prior committers). Only the view moves; a lower
            # view is stale and a different hash stays refused.
            if view < existing_view:
                return False
            if view == existing_view:
                return True

        def _arm(rec: dict[str, Any]) -> None:
            rec["commit_lock"] = {
                "view": view,
                "block_hash": block_hash,
                "commit": dict(commit),
                "proof": [dict(m) for m in proof],
            }

        return self._pbft_vc_mutate(sequence, _arm)

    def pbft_vc_proposal_store(self, sequence: int, block_hash: str, payload: dict[str, Any]) -> bool:
        """Persist a pre-prepare proposal body before any PREPARE is sent.

        Option R (#2005 §5): a validator that cannot produce the decided
        block's body makes a commit quorum unrecoverable, so the body is
        stored fail-closed before the vote. Bounded: at most
        ``MAX_PROPOSALS_PER_SEQUENCE`` bodies per height and
        ``MAX_PROPOSAL_PAYLOAD_BYTES`` per body; both caps live in
        ``pbft_view_change``. Entries below the current sequence are pruned
        on seal like every other per-height record.
        """
        from .pbft_view_change import MAX_PROPOSAL_PAYLOAD_BYTES, MAX_PROPOSALS_PER_SEQUENCE

        import json

        try:
            size = len(json.dumps(payload, separators=(",", ":")))
        except (TypeError, ValueError):
            return False
        if size > MAX_PROPOSAL_PAYLOAD_BYTES:
            return False
        rec_existing = self._pbft_view_change.get(sequence)
        proposals = rec_existing.get("proposals") if rec_existing else None
        if isinstance(proposals, dict) and block_hash in proposals:
            return True  # already held — idempotent
        locked = (
            {
                str(r["block_hash"]).lower()
                for r in (rec_existing.get("commit_lock"), rec_existing.get("prepared"))
                if isinstance(r, dict) and r.get("block_hash")
            }
            if rec_existing
            else set()
        )

        if (
            isinstance(proposals, dict)
            and len(proposals) >= MAX_PROPOSALS_PER_SEQUENCE
            and all(str(h).lower() in locked for h in proposals)
        ):
            return False  # every held body is pinned by a lock — nothing evictable

        def _store(rec: dict[str, Any]) -> None:
            props = rec.get("proposals")
            if not isinstance(props, dict):
                props = {}
                rec["proposals"] = props
            # Bounded by EVICTION, not refusal (#2005 review): refusing at the
            # cap let a flood of junk proposals starve the legitimate one.
            # Oldest first, never a body the commit-lock / prepared record
            # still needs (Option R).
            while len(props) >= MAX_PROPOSALS_PER_SEQUENCE:
                victim = next((h for h in props if str(h).lower() not in locked), None)
                if victim is None:
                    return
                del props[victim]
            props[block_hash] = dict(payload)

        return self._pbft_vc_mutate(sequence, _store)

    @staticmethod
    def _parse_view_change_records(raw: Any) -> dict[int, dict[str, Any]]:
        """Rebuild ``{sequence: record}`` VC state from persisted JSON.

        Tolerant like ``_parse_commit_locks`` but LOUD on corrupt non-empty
        input (review N2 lesson): a silently dropped record is a restart-
        amnesia hole for the floor rule. Malformed entries are dropped
        individually; an unparseable top-level value logs an error.
        """
        import json

        if not raw:
            return {}
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            raise ValueError("pbft_view_change_json is not parseable JSON") from None
        if not isinstance(data, dict):
            raise ValueError("pbft_view_change_json is not a JSON object")
        records: dict[int, dict[str, Any]] = {}
        for key, value in data.items():
            try:
                seq = int(key)
            except (TypeError, ValueError):
                continue
            if seq < 0 or not isinstance(value, dict):
                continue
            raw_floor = value.get("floor")
            if raw_floor is not None and not _is_strict_int(raw_floor):
                # #2005 r3: a malformed floor must not silently become "no
                # floor" (restart amnesia) — fail closed like corrupt JSON.
                raise ValueError(f"pbft_view_change_json floor for height {key} is not an integer")
            rec: dict[str, Any] = {
                "floor": raw_floor,
                "prepared": value.get("prepared") if isinstance(value.get("prepared"), dict) else None,
                "commit_lock": value.get("commit_lock") if isinstance(value.get("commit_lock"), dict) else None,
                "proposals": value.get("proposals") if isinstance(value.get("proposals"), dict) else {},
            }
            records[seq] = rec
        return records

    # ─── B12: Consensus Metrics ───────────────────────────────────

    def collect_metrics(self) -> dict[str, Any]:
        """Collect consensus metrics for Prometheus export.

        Returns a dict of metric name -> value. The observability layer
        registers these as gauges/counters. Called periodically by the
        metrics collector.
        """
        active_count = sum(1 for v in self.validators.values() if v.is_active)
        return {
            "consensus_validators_active": active_count,
            "consensus_validators_total": len(self.validators),
            "consensus_rounds_total": self.consensus_attempts,
            "consensus_view_changes_total": getattr(self, "_view_change_count", 0),
            "consensus_byzantine_detections_total": sum(1 for v in self.validators.values() if not v.is_active),
            "consensus_slashing_events_total": len(self._slashing_manager.get_slashing_history()),
        }
