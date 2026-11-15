"""
Multi-Validator Proof of Authority Consensus Implementation
Extends single validator PoA to support multiple validators with rotation

# ════════════════════════════════════════════════════════════════
# v0.7.5: All 12 security review findings fixed (6 Critical + 6 High).
# Guard now reads from settings.multi_validator_consensus_enabled
# instead of MULTI_VALIDATOR_CONSENSUS_ENABLED env var.
# Keep guard in place until B14 test suite passes.
# ════════════════════════════════════════════════════════════════
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from sqlmodel import Session

from ..models import Block

logger = get_logger(__name__)


def proposer_round(parent_timestamp: datetime | None, block_timestamp: datetime, round_seconds: int) -> int:
    """Derive a block's proposer round from on-chain timestamps.

    Round 0 belongs to the scheduled proposer for the height. Each
    ``round_seconds`` that elapse without a block advances the round by one and
    hands the slot to the next validator in the round-robin. Both inputs come
    from block headers, so every node derives the same round for the same block
    and no view-change messages have to be exchanged to agree on who may
    propose.
    """
    if parent_timestamp is None or round_seconds <= 0:
        return 0
    if parent_timestamp.tzinfo is None:
        parent_timestamp = parent_timestamp.replace(tzinfo=UTC)
    if block_timestamp.tzinfo is None:
        block_timestamp = block_timestamp.replace(tzinfo=UTC)
    elapsed = (block_timestamp - parent_timestamp).total_seconds()
    if elapsed <= 0:
        return 0
    return int(elapsed // round_seconds)


def _verify_block_signature_gated(block: Block, proposer: str) -> bool:
    """#1298: proposal-domain verification at/above the armed activation
    height; legacy verify_block_signature below it (extracted to keep
    ``validate_block`` under the C901 ratchet)."""
    from aitbc.crypto.consensus_signing import (
        DOMAIN_BLOCK_PROPOSAL,
        block_header_message,
        verify_block_signature,
        verify_consensus_message_domain,
    )

    activation = getattr(settings, "consensus_domain_separation_height", None)
    if activation is not None and isinstance(block.height, int) and block.height >= activation:
        return verify_consensus_message_domain(
            block_header_message(block), block.signature or "", proposer, DOMAIN_BLOCK_PROPOSAL
        )
    return verify_block_signature(block, block.signature or "", proposer)


class ValidatorRole(Enum):
    PROPOSER = "proposer"
    VALIDATOR = "validator"
    STANDBY = "standby"


@dataclass
class Validator:
    address: str
    # V23-48: Decimal, so a slash deducts an exact quantity. apply_slashing computes
    # stake * slash_rate and records the result on the event; in binary float that product
    # is the thing being reported as "amount slashed", so it has to be exact.
    stake: Decimal
    reputation: float
    role: ValidatorRole
    last_proposed: int
    is_active: bool
    hybrid_score: float = 0.0


def _is_strict_int(value: Any) -> bool:
    """Strictly ``int`` — ``bool`` is an ``int`` subclass and must not pass."""
    return isinstance(value, int) and not isinstance(value, bool)


def _non_empty_str(value: Any) -> bool:
    """``str`` with non-zero length (rejects None, "", and non-str)."""
    return isinstance(value, str) and bool(value)


def _cross_view_message_shape(msg: dict[str, Any]) -> bool:
    """Shape gate for cross-view commit evidence (#1940 F3-A): COMMIT type,
    strict-int ``sequence_number``/``view_number``, non-empty str
    ``block_hash``/``digest``/``signature`` — anything less could never
    satisfy the on-chain evidence gate, so it produces no event at all."""
    return (
        msg.get("message_type") == "commit"
        and _is_strict_int(msg.get("sequence_number"))
        and _is_strict_int(msg.get("view_number"))
        and _non_empty_str(msg.get("block_hash"))
        and _non_empty_str(msg.get("digest"))
        and _non_empty_str(msg.get("signature"))
    )


class MultiValidatorPoA:
    """Multi-Validator Proof of Authority consensus mechanism"""

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

        # B3: block signature verification toggle
        self._require_block_signatures: bool = getattr(settings, "bridge_block_signature_required", True)

        # B4: slashing manager (imported here to avoid circular import at module load)
        from .slashing import SlashingManager

        self._slashing_manager = SlashingManager()

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

        # #1940 F4: optional session factory for chain-state reads
        # (_current_head_height / _chain_deactivated_addresses). The
        # attestation post-state probe injects one bound to its scratch
        # session so speculative schedule/deactivation checks can never open
        # a production session_scope. None keeps the production default.
        self._chain_state_session_factory = chain_state_session_factory

        if load_state:
            self.load_state()

    @classmethod
    def from_settings(
        cls,
        chain_id: str,
        *,
        chain_state_session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
    ) -> "MultiValidatorPoA":
        """Build a consensus instance directly from settings without touching the DB."""
        instance = cls(chain_id, load_state=False, chain_state_session_factory=chain_state_session_factory)
        instance._load_validator_set_from_settings()
        return instance

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

    def remove_validator(self, address: str) -> bool:
        """Remove a validator from the consensus"""
        if address not in self.validators:
            return False

        validator = self.validators[address]
        validator.is_active = False
        validator.role = ValidatorRole.STANDBY
        self.save_state()
        return True

    def select_proposer(self, block_height: int, round_number: int = 0) -> str | None:
        """Select the proposer for a height and round using round-robin.

        ``round_number`` is the view. It advances when the scheduled proposer
        does not produce a block within ``consensus_proposer_round_seconds`` of
        the parent block, so an unavailable proposer no longer stalls the
        chain: the slot moves to the next validator in the same deterministic
        order.
        """
        # A validator deactivated on-chain (#1198) is excluded from every
        # selection/validation predicate below. Markers sealed in blocks at
        # or below ``block_height - 1`` are in the parent state a proposal at
        # ``block_height`` builds on, so they apply.
        deactivated = self._chain_deactivated_addresses(block_height - 1)
        active_validators = sorted(
            (
                v
                for v in self.validators.values()
                if v.is_active
                and v.role in [ValidatorRole.PROPOSER, ValidatorRole.VALIDATOR]
                and canonical_address(v.address) not in deactivated
            ),
            key=lambda v: v.address,
        )

        if not active_validators:
            return None

        # Round-robin selection on a deterministic, globally-consistent order.
        proposer_index = (block_height + max(0, round_number)) % len(active_validators)
        return active_validators[proposer_index].address

    def validate_block(self, block: Block, proposer: str, parent_timestamp: datetime | None = None) -> bool:
        """Validate a proposed block.

        When ``parent_timestamp`` is supplied the proposer is also checked
        against the schedule: the block must come from the validator that owns
        its height and the round its own timestamp implies. Without the parent
        timestamp the round cannot be derived and only membership, role and
        signature are checked, which is the pre-v0.25.6 behaviour.
        """
        if proposer not in self.validators:
            return False

        validator = self.validators[proposer]
        if not validator.is_active:
            return False
        # #1198: an on-chain deactivation marker sealed before this block's
        # parent excludes the proposer identically on every node. A missing
        # height resolves to "all markers" — conservative toward exclusion.
        block_height = block.height if isinstance(block.height, int) else None
        if canonical_address(validator.address) in self._chain_deactivated_addresses(
            block_height - 1 if block_height is not None else None
        ):
            return False

        # Check if validator is allowed to propose
        if validator.role not in [ValidatorRole.PROPOSER, ValidatorRole.VALIDATOR]:
            return False

        # v0.25.6: enforce the rotation. Round-robin selection alone decided
        # nothing until now, because nothing checked that the block came from
        # the validator whose turn it was.
        if parent_timestamp is not None and getattr(settings, "consensus_enforce_proposer_schedule", True):
            round_number = proposer_round(
                parent_timestamp, block.timestamp, getattr(settings, "consensus_proposer_round_seconds", 120)
            )
            expected = self.select_proposer(block.height, round_number)
            if expected and expected != proposer:
                logger.warning(
                    "Block %s proposed by %s but round %s at that height belongs to %s",
                    block.height,
                    proposer,
                    round_number,
                    expected,
                )
                return False

        # B3: verify block signature (C1)
        if block.signature:
            if not _verify_block_signature_gated(block, proposer):
                return False
        elif self._require_block_signatures:
            return False

        # Additional validation logic here
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
        except Exception as e:
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
        except Exception as e:
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
        except Exception as e:
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

    def _cross_view_draft_min_height(self, head: int | None) -> int | None:
        """Local ``validator_deactivation_pbft_cross_view_evidence_height``
        chain parameter resolved at ``head`` (#1940 F3-A) — the draft-side
        floor for cross-view evidence claims. ``None`` when headless,
        unarmed, malformed or unreadable: fail closed, cite nothing (the
        apply gate decides the real verdict either way)."""
        if head is None:
            return None
        try:
            from ..database import session_scope
            from ..state.deactivation_evidence import _cross_view_evidence_height

            with session_scope(self.chain_id) as session:
                return _cross_view_evidence_height(session, self.chain_id, head)
        except Exception as e:  # noqa: BLE001 - draft-side lookup is advisory; the gate re-verifies
            logger.warning("Cross-view evidence height lookup failed drafting deactivations for %s: %s", self.chain_id, e)
            return None

    def draft_deactivation_txs(self) -> dict[str, list[dict[str, Any]]]:
        """Draft ``VALIDATOR_DEACTIVATE`` txs for divergent validators (#1198).

        Auto-draft half of the approved migration ordering: for every
        locally-deactivated validator with no on-chain marker and an active
        bond, emit a ready-to-sign payload (``validator_address``,
        ``evidence_hash`` over its slashing history, ``bond_id``). Validators
        without an active bond are listed under ``skipped`` — Q2: they cannot
        be deactivated on-chain; env removal is their only recourse.
        """
        from sqlmodel import select

        from ..base_models import Bond
        from ..database import session_scope

        # Bond.provider spellings vary (raw env vs EIP-55); compare canonical
        # forms — same rule the apply-path bond gate uses.
        provider_bonds: dict[str, Bond] = {}
        try:
            with session_scope(self.chain_id) as session:
                for b in session.exec(select(Bond).where(Bond.chain_id == self.chain_id, Bond.status == "active")).all():
                    provider_bonds.setdefault(canonical_address(b.provider), b)
        except Exception as e:
            logger.error("Bond scan failed drafting deactivations for %s: %s", self.chain_id, e)
            return {"drafts": [], "skipped": [{"address": a, "reason": f"bond scan failed: {e}"} for a in self.validators]}

        deactivated = self._chain_deactivated_addresses(None)
        # #1206: only evidence sealed at least ``finality_depth`` blocks deep
        # may be cited — a reorg must not be able to invalidate the justification
        # a drafted VALIDATOR_DEACTIVATE commits to. An unreadable head falls
        # back to no cutoff (availability over silent correctness, same rule as
        # _chain_deactivated_addresses).
        head = self._current_head_height()
        depth = int(getattr(settings, "consensus_slashing_evidence_finality_depth", 10))
        evidence_cutoff = head - depth if head is not None else None
        # #1959: when ``validator_deactivation_evidence_ttl_blocks`` is armed,
        # don't draft evidence the apply gate will expire — read the same
        # parameter at the same head so draft and gate agree. Lookup failure
        # falls back to no floor (the gate itself still decides at apply).
        evidence_min_height = None
        if head is not None:
            try:
                from sqlalchemy.exc import SQLAlchemyError

                from ..state.state_transition import _chain_parameter_value

                with session_scope(self.chain_id) as session:
                    ttl_raw = _chain_parameter_value(
                        session, self.chain_id, "validator_deactivation_evidence_ttl_blocks", head
                    )
                ttl = int(str(ttl_raw).strip())
                if ttl > 0:
                    evidence_min_height = head - ttl
            except (SQLAlchemyError, ValueError, TypeError) as e:
                logger.warning("Evidence TTL lookup failed drafting deactivations for %s: %s", self.chain_id, e)
        # #1940 F3-A: cross-view commit equivocation claims verify on-chain
        # only at/above the ``validator_deactivation_pbft_cross_view_evidence_height``
        # chain parameter resolved at the apply height — the gate fails closed
        # on anything else, so a v2 draft must not cite a claim that can
        # never verify. Same head-scoped lookup rule as the TTL floor; an
        # unset/malformed/failed lookup resolves to "cite nothing" (the
        # apply gate decides the real verdict either way).
        cross_view_min_height = self._cross_view_draft_min_height(head)
        drafts: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for addr, v in self.validators.items():
            events = self._slashing_manager.events_for(
                addr, max_block_height=evidence_cutoff, min_block_height=evidence_min_height
            )
            has_evidence = bool(events)
            if v.is_active and not has_evidence:
                continue
            canon = canonical_address(addr)
            if canon in deactivated:
                continue
            entry = {"address": addr, "canonical_address": canon}
            bond = provider_bonds.get(canon)
            if bond is None:
                skipped.append({**entry, "reason": "no active bond — cannot deactivate on-chain (Q2)"})
                continue
            drafts.append(
                {
                    **entry,
                    "type": "VALIDATOR_DEACTIVATE",
                    "value": 0,
                    "payload": self._deactivation_payload(
                        addr, canon, bond.bond_id, events, evidence_cutoff, evidence_min_height, cross_view_min_height
                    ),
                }
            )
        return {"drafts": drafts, "skipped": skipped}

    def _deactivation_payload(
        self,
        addr: str,
        canon: str,
        bond_id: str,
        events: list[Any],
        evidence_cutoff: int | None,
        evidence_min_height: int | None = None,
        cross_view_min_height: int | None = None,
    ) -> dict[str, Any]:
        """Build the VALIDATOR_DEACTIVATE payload (#1263).

        Emits ``evidence_version: 2`` with the full canonical event list only
        when at least one equivocation event carries signature material —
        unsigned equivocation claims are excluded from the submitted bundle
        (they could never verify and would fail the armed gate), while
        non-equivocation events stay as hash-bound informational records.
        Without signature-bearing evidence the draft stays v1 audit-only.
        """
        from .slashing import SlashingManager, event_is_equivocation_claim, event_signature_evidence, slashing_event_record

        # #1940 F3-A: cross-view commit equivocation claims are citable in a
        # v2 bundle only at/above the armed on-chain activation height — the
        # apply gate fails closed on anything else, and an unverifiable
        # equivocation claim fails the WHOLE marker, so such events are
        # excluded here entirely (they remain in the v1 audit hash and in
        # local slashing history; they are just never submitted as v2
        # evidence). ``cross_view_min_height=None`` therefore excludes every
        # cross-view claim — matching the gate, which also fails closed when
        # the parameter is unset or malformed.
        from .slashing import PBFT_CROSS_VIEW_VOTE_EQUIVOCATION, _evidence_payload

        def _cross_view_citable(e: Any) -> bool:
            ep = _evidence_payload(e)
            if ep is None or ep.get("kind") != PBFT_CROSS_VIEW_VOTE_EQUIVOCATION:
                return True
            sequence = ep.get("sequence")
            return (
                isinstance(sequence, int)
                and not isinstance(sequence, bool)
                and cross_view_min_height is not None
                and sequence >= cross_view_min_height
            )

        citable = [e for e in events if _cross_view_citable(e)]
        signed_equiv = [e for e in citable if event_signature_evidence(e) is not None]
        if not signed_equiv:
            return {
                "validator_address": canon,
                "evidence_hash": self._slashing_manager.evidence_hash(
                    addr, max_block_height=evidence_cutoff, min_block_height=evidence_min_height
                ),
                "bond_id": bond_id,
            }
        keep = [e for e in citable if not (event_is_equivocation_claim(e) and event_signature_evidence(e) is None)]
        keep.sort(
            key=lambda e: (
                e.block_height,
                e.condition.value,
                e.evidence,
                e.round_number if e.round_number is not None else -1,
                e.hash_a,
                e.hash_b,
            )
        )
        bundle_mgr = SlashingManager()
        bundle_mgr.slashing_events = keep
        return {
            "validator_address": canon,
            "evidence_hash": bundle_mgr.evidence_hash(canon),
            "bond_id": bond_id,
            "evidence_version": 2,
            "evidence": [slashing_event_record(e) for e in keep],
        }

    def reload_state_if_anomalous(self) -> bool:
        """Sentinel re-read for the empty-active-view failure (#693).

        A consensus participant set that reads empty while validators are
        registered — in memory or via ``VALIDATOR_SET`` — is never a steady
        state: it means the in-memory view was poisoned by a transient empty
        load (e.g. a failed startup DB read that fell back to an unparseable
        env set, or a wipe that predates the empty-env guard). Serving the
        empty view silently degrades the node to proposing/attesting as if it
        were alone, which is what produced the hub1 2026-10-28 reject storm.

        Forces a fresh ``load_state`` (DB row first, env fallback) and returns
        True when a re-read ran. Callers should re-read the participants after
        this returns. Returns False when the view is healthy or genuinely
        unconfigured, so single-validator islands are never penalised.
        """
        if self.get_consensus_participants():
            return False
        registered = any(v.role in (ValidatorRole.PROPOSER, ValidatorRole.VALIDATOR) for v in self.validators.values())
        env_configured = bool(getattr(settings, "validator_set", "") or "")
        if not registered and not env_configured:
            return False
        logger.error(
            "Consensus participant set reads EMPTY for chain %s while %d validator(s) "
            "are registered%s — forcing a state re-read (#693)",
            self.chain_id,
            len(self.validators),
            " and VALIDATOR_SET is configured" if env_configured else "",
        )
        return self.load_state()

    def can_resume_consensus(self) -> bool:
        """Check if consensus can resume after network partition"""
        if not self.network_partitioned:
            return True

        # Require minimum time after partition healing
        if self.last_partition_healed > 0:
            return (time.time() - self.last_partition_healed) >= 5.0

        return False

    def mark_validator_partitioned(self, address: str) -> bool:
        """Mark a validator as partitioned"""
        if address not in self.validators:
            return False

        self.partitioned_validators.add(address)
        return True

    async def validate_transaction_async(self, transaction: object) -> bool:
        """Asynchronously validate a transaction"""
        # Simulate async validation
        await asyncio.sleep(0.001)

        # Basic validation
        if not hasattr(transaction, "tx_id"):
            return False

        # H2: delegate to state transition checks
        if hasattr(transaction, "amount") and getattr(transaction, "amount", 0) < 0:
            return False
        if hasattr(transaction, "chain_id") and not getattr(transaction, "chain_id", ""):
            return False

        return True

    async def attempt_consensus(self, block_hash: str = "", round: int = 1) -> bool:
        """Attempt to reach consensus via real PBFT delegation (B8 / H1)"""
        self.consensus_attempts += 1

        # Check if enough validators are available
        active_validators = self.get_consensus_participants()
        if len(active_validators) < 2:
            return False

        # Check if partitioned validators are too many
        if len(self.partitioned_validators) > len(self.validators) // 2:
            return False

        # Delegate to PBFT consensus
        from .pbft import PBFTConsensus

        pbft = PBFTConsensus(self, chain_id=self.chain_id)
        proposer = self.select_proposer(round)
        if not proposer:
            return False

        # Pre-prepare
        if not await pbft.pre_prepare_phase(proposer, block_hash or hashlib.sha256(str(time.time()).encode()).hexdigest()):
            return False

        # Prepare phase — collect from all active validators
        key = f"{pbft.state.current_sequence + 1}:{pbft.state.current_view}"
        pre_prepare = pbft.state.pre_prepare_messages.get(key)
        if not pre_prepare:
            return False
        for validator in active_validators:
            await pbft.prepare_phase(validator, pre_prepare)

        # Commit phase
        prepared_msgs = pbft.state.prepared_messages.get(key, [])
        if prepared_msgs and len(prepared_msgs) >= pbft.required_messages:
            for msg in prepared_msgs:
                await pbft.commit_phase(msg.sender, msg)

        committed = pbft.state.committed_messages.get(key, [])
        return len(committed) >= pbft.required_messages

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
            if msg["round"] == round and msg["block_hash"] != block_hash:
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

            # Check for conflicting messages in same round
            rounds: dict[int, set[str]] = {}
            for msg in messages:
                if msg["round"] not in rounds:
                    rounds[msg["round"]] = set()
                rounds[msg["round"]].add(msg["block_hash"])

            # Byzantine if any round has multiple block hashes — slash the offender
            for round_num, block_hashes in rounds.items():
                if len(block_hashes) <= 1:
                    continue
                detected = True
                event = self._vote_equivocation_event(validator, store, messages, round_num, block_hashes)
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
            # — observation order cannot change the evidence.
            best_pair = min(
                self._cross_view_conflicting_pairs(seq_msgs),
                key=self._cross_view_pair_key,
                default=None,
            )
            if best_pair is None:
                continue
            event = self._slashing_manager.cross_view_vote_equivocation_event(
                validator,
                sequence,
                "commit",
                {k: best_pair[0].get(k) for k in self._VOTE_EVIDENCE_FIELDS},
                {k: best_pair[1].get(k) for k in self._VOTE_EVIDENCE_FIELDS},
            )
            self._apply_equivocation_slash(validator, event)
            detected = True
        return detected

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
    def _cross_view_conflicting_pairs(seq_msgs: list[dict[str, Any]]):
        """Yield canonically-ordered ``(lo, hi)`` record pairs that conflict:
        different ``view_number`` AND different ``block_hash``."""
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
            else:
                self.validators[validator].is_active = False
                # Persist the deactivation — a restart must not clear
                # a byzantine verdict and reset the slash history.
                self.save_state()

    _VOTE_EVIDENCE_FIELDS = ("message_type", "sender", "view_number", "sequence_number", "digest", "block_hash", "signature")

    def _vote_equivocation_event(
        self,
        validator: str,
        store: dict[str, list[dict[str, Any]]],
        messages: list[dict[str, Any]],
        round_num: int,
        block_hashes: set[str],
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
            if msg.get("round") == round_num and msg.get("block_hash") in block_hashes:
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
        )
        if persist:
            self.save_state()
        return event

    def get_state_snapshot(self) -> dict[str, Any]:
        """Get a snapshot of the current blockchain state"""
        return {
            "chain_id": self.chain_id,
            "validators": {
                addr: {"stake": str(v.stake), "role": v.role.value, "is_active": v.is_active, "reputation": v.reputation}
                for addr, v in self.validators.items()
            },
            "network_partitioned": self.network_partitioned,
            "partitioned_validators": list(self.partitioned_validators),
            "consensus_attempts": self.consensus_attempts,
            "timestamp": time.time(),
        }

    def calculate_state_hash(self, state: dict[str, Any]) -> str:
        """Calculate hash of blockchain state"""
        import json

        state_str = json.dumps(state, sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()

    def create_block(self, height: int = 0, parent_hash: str = "", transactions: list | None = None) -> dict[str, Any]:
        """Create a new block (B9 / H3)"""
        proposer = self.select_proposer(height)
        timestamp = time.time()
        tx_hashes = sorted([getattr(tx, "tx_id", str(tx)) for tx in (transactions or [])])
        hash_content = f"{self.chain_id}:{height}:{parent_hash}:{timestamp}:{tx_hashes}"
        block_hash = hashlib.sha256(hash_content.encode()).hexdigest()
        # Sign the block hash if we have a private key
        signature = ""
        block = {
            "block_height": height,
            "proposer": proposer,
            "timestamp": timestamp,
            "hash": block_hash,
            "parent_hash": parent_hash,
            "transactions": tx_hashes,
            "signature": signature,
        }
        return block

    def add_transaction(self, transaction: object) -> bool:
        """Add a transaction to the block"""
        return hasattr(transaction, "tx_id")

    def simulate_crash(self) -> None:
        """Simulate a crash (for testing)"""
        self._crashed_state = self.get_state_snapshot()

    def recover_from_crash(self) -> None:
        """Recover from a crash (for testing)"""
        if hasattr(self, "_crashed_state"):
            self._crashed_state = None  # type: ignore[assignment]

    def recover_state(self, state: dict[str, Any]) -> bool:
        """Recover state from snapshot (for testing)"""
        try:
            self.validators = {}
            for addr, v_data in state.get("validators", {}).items():
                self.validators[addr] = Validator(
                    address=addr,
                    stake=v_data.get("stake", 1000.0),
                    reputation=v_data.get("reputation", 1.0),
                    role=ValidatorRole(v_data.get("role", "STANDBY")),
                    last_proposed=0,
                    is_active=v_data.get("is_active", True),
                )
            self.network_partitioned = state.get("network_partitioned", False)
            self.consensus_attempts = state.get("consensus_attempts", 0)
            return True
        except Exception as e:  # noqa: BLE001 - restore failure means start from defaults
            logger.debug("consensus state restore failed: %s", type(e).__name__)
            return False

    def update_validator_reputation(self, address: str, delta: float) -> bool:
        """Update validator reputation"""
        if address not in self.validators:
            return False

        validator = self.validators[address]
        validator.reputation = max(0.0, min(1.0, validator.reputation + delta))
        return True

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

        slashing_events = [slashing_event_record(e) for e in self._slashing_manager.get_slashing_history()]
        try:
            with session_scope(self.chain_id) as session:
                existing = session.query(ConsensusState).filter_by(chain_id=self.chain_id).first()
                if existing:
                    existing.current_view = self._pbft_view
                    existing.current_sequence = self._pbft_sequence
                    existing.current_epoch = self._current_epoch
                    existing.validator_set_json = json.dumps(validator_set)
                    existing.slashing_events_json = json.dumps(slashing_events)
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
                        )
                    )
                # session_scope closes without committing — without this the
                # write above was silently rolled back on every call and
                # consensus_state stayed empty fleet-wide.
                session.commit()
            return True
        except Exception as e:
            logger.error("Failed to save consensus state for %s: %s", self.chain_id, e)
            return False

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
                evidence, round_number, hash_a, hash_b = MultiValidatorPoA._canonical_evidence_fields(record)
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

    def load_state(self) -> bool:
        """Load consensus state from DB on node startup."""
        import json

        from ..base_models import ConsensusState
        from ..database import session_scope

        try:
            with session_scope(self.chain_id) as session:
                row = session.query(ConsensusState).filter_by(chain_id=self.chain_id).first()
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
                self._slashing_manager.slashing_events = self._parse_slashing_events(
                    json.loads(row.slashing_events_json) if row.slashing_events_json else []
                )
            if self._chain_slashing_armed():
                self._report_slashing_divergence()
            return True
        except Exception as e:
            logger.error("Failed to load consensus state for %s: %s", self.chain_id, e)
            return self._load_validator_set_from_settings()

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


# Global consensus instance
consensus_instances: dict[str, MultiValidatorPoA] = {}


def get_consensus(chain_id: str) -> MultiValidatorPoA:
    """Get or create consensus instance for chain"""
    if chain_id not in consensus_instances:
        consensus_instances[chain_id] = MultiValidatorPoA(chain_id)
    return consensus_instances[chain_id]
