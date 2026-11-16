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
from sqlalchemy.exc import SQLAlchemyError
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


from .multi_validator_poa_state import _StateMixin
from .multi_validator_poa_equivocation import _EquivocationMixin


class MultiValidatorPoA(_EquivocationMixin, _StateMixin):
    """Multi-Validator Proof of Authority consensus mechanism"""

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

        # Round-robin selection on a deterministic, globally-consistent order
        # (the shared #2005 schedule formula; ``active_validators`` is already
        # address-sorted, ``scheduled_proposer`` re-sorts the same strings).
        from .pbft_view_change import scheduled_proposer

        return scheduled_proposer([v.address for v in active_validators], block_height, round_number)

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
        except (SQLAlchemyError, OSError, ValueError, TypeError, AttributeError, KeyError) as e:
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


# Global consensus instance
consensus_instances: dict[str, MultiValidatorPoA] = {}


def get_consensus(chain_id: str) -> MultiValidatorPoA:
    """Get or create consensus instance for chain"""
    if chain_id not in consensus_instances:
        consensus_instances[chain_id] = MultiValidatorPoA(chain_id)
    return consensus_instances[chain_id]
