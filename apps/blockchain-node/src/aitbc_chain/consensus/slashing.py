"""Slashing conditions: detection and penalties for validator misbehaviour.

V23-48. ``SlashingEvent.slash_amount`` was not an amount. It held a *rate* — 0.05 to 0.5,
straight from ``slash_rates`` — and ``apply_slashing`` multiplied it by ``validator.stake``
to get the quantity actually deducted, which was then **discarded**. Nothing recorded how
much a validator lost.

So ``calculate_total_slashed`` summed rates and returned them as "total amount slashed": three
double-signs reported 1.5, meaning 1.5 AIT to anyone reading it, when the real total depended
on a stake nobody had written down. It could not be fixed by changing that function, because
the number it needed had never been stored.

The event now carries three separate quantities:

    slash_rate       the fraction, set at detection      (0.05 - 0.5)
    stake_before     the stake at the moment of slashing (None until applied)
    slashed_amount   what was actually deducted          (None until applied)

``stake_before`` is what makes the record auditable rather than merely correct: with the rate
and the pre-slash stake, ``slashed_amount`` can be re-derived and checked, and a validator can
be shown *why* it lost what it lost.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .multi_validator_poa import Validator, ValidatorRole


class SlashingCondition(Enum):
    DOUBLE_SIGN = "double_sign"
    UNAVAILABLE = "unavailable"
    INVALID_BLOCK = "invalid_block"
    SLOW_RESPONSE = "slow_response"


@dataclass
class SlashingEvent:
    validator_address: str
    condition: SlashingCondition
    evidence: str
    block_height: int
    timestamp: float
    # not-money: a fraction of stake (0.05-0.5) from slash_rates. Was called `slash_amount`,
    # which is what made `calculate_total_slashed` wrong -- see the module docstring.
    slash_rate: float
    # Both None until apply_slashing() runs: a detected event is not a levied one, and
    # recording an amount for a penalty that was never applied would be its own lie.
    stake_before: Decimal | None = None
    slashed_amount: Decimal | None = None
    # #1206 canonical evidence fields: structured equivocation data so the
    # evidence bundle/hash is reproducible on any node. ``hash_a``/``hash_b``
    # are the two conflicting digests in sorted order; ``round_number`` is the
    # consensus round (None for height-only locks and non-equivocation events).
    round_number: int | None = None
    hash_a: str = ""
    hash_b: str = ""

    @property
    def is_applied(self) -> bool:
        """Whether this event actually cost the validator anything."""
        return self.slashed_amount is not None


# Below this, a validator is demoted to standby. Named because it is now compared against a
# Decimal stake, and a bare `100` next to money reads as a magic number.
MIN_ACTIVE_STAKE = Decimal("100")


def _sorted_hash_pair(hash_a: str, hash_b: str) -> tuple[str, str]:
    """Canonical order for an equivocation pair — observation order must not
    change the evidence (#1206)."""
    return (hash_a, hash_b) if hash_a.lower() <= hash_b.lower() else (hash_b, hash_a)


def _equivocation_dedup_key(event: SlashingEvent) -> str:
    """Canonical dedup key for a slashing event (#1206 / #1263).

    Covers validator, condition, height and the structured equivocation
    fields — deliberately excludes ``timestamp`` (wall-clock, differs per
    observer), ``stake_before``/``slashed_amount`` (local mutation), and the
    ``evidence`` payload whenever the structured hash pair is present: the
    same offense recorded as legacy free-text, hash-only JSON, or
    signature-bearing JSON is ONE event (#1263), and re-observation can
    never double-append or double-slash. Non-equivocation events (no hash
    pair) keep ``evidence`` in the key so distinct offenses stay distinct.
    """
    from aitbc.crypto.signature_recovery import canonical_address

    payload = {
        "validator_address": canonical_address(event.validator_address),
        "condition": event.condition.value,
        "block_height": event.block_height,
        "round_number": event.round_number,
        "hash_a": event.hash_a,
        "hash_b": event.hash_b,
    }
    if not (event.hash_a or event.hash_b):
        payload["evidence"] = event.evidence
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _evidence_payload(event: SlashingEvent) -> dict | None:
    """Parsed JSON payload of ``event.evidence``, or None for free-text/legacy."""
    try:
        payload = json.loads(event.evidence)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def event_signature_evidence(event: SlashingEvent) -> dict | None:
    """The signature-bearing payload of an equivocation event (#1263), or None.

    Returns the parsed evidence dict when it carries a non-empty
    ``attestations`` (attestation equivocation) or ``messages`` (vote
    equivocation) list — the material on-chain verification needs. Hash-only
    and free-text records return None: they stay advisory but can never
    satisfy the ``validator_deactivation_evidence_required`` gate.
    """
    payload = _evidence_payload(event)
    if payload is None:
        return None
    for key in ("attestations", "messages"):
        entries = payload.get(key)
        if isinstance(entries, list) and entries:
            return payload
    return None


def event_is_equivocation_claim(event: SlashingEvent) -> bool:
    """Whether the event claims an equivocation offense (verifiable or not)."""
    payload = _evidence_payload(event)
    if payload is not None:
        return payload.get("kind") in ("attestation_equivocation", "vote_equivocation")
    return event.evidence.startswith("Double sign detected")


def slashing_event_record(event: SlashingEvent) -> dict:
    """Canonical persisted/draft record shape for a SlashingEvent (#1263).

    Single source for ``ConsensusState.slashing_events_json`` and the
    ``VALIDATOR_DEACTIVATE`` v2 ``evidence`` payload — the two must stay
    byte-identical or ``evidence_hash`` binding breaks.
    """
    return {
        "validator_address": event.validator_address,
        "condition": event.condition.value,
        "evidence": event.evidence,
        "block_height": event.block_height,
        "timestamp": event.timestamp,
        "slash_rate": event.slash_rate,
        "stake_before": None if event.stake_before is None else str(event.stake_before),
        "slashed_amount": None if event.slashed_amount is None else str(event.slashed_amount),
        "round_number": event.round_number,
        "hash_a": event.hash_a,
        "hash_b": event.hash_b,
    }


class SlashingManager:
    """Manages validator slashing conditions and penalties"""

    def __init__(self) -> None:
        self.slashing_events: list[SlashingEvent] = []
        self.slash_rates = {
            SlashingCondition.DOUBLE_SIGN: 0.5,  # 50% slash
            SlashingCondition.UNAVAILABLE: 0.1,  # 10% slash
            SlashingCondition.INVALID_BLOCK: 0.3,  # 30% slash
            SlashingCondition.SLOW_RESPONSE: 0.05,  # 5% slash
        }
        self.slash_thresholds = {
            SlashingCondition.DOUBLE_SIGN: 1,  # Immediate slash
            SlashingCondition.UNAVAILABLE: 3,  # After 3 offenses
            SlashingCondition.INVALID_BLOCK: 1,  # Immediate slash
            SlashingCondition.SLOW_RESPONSE: 5,  # After 5 offenses
        }

    def detect_double_sign(self, validator: str, block_hash1: str, block_hash2: str, height: int) -> SlashingEvent | None:
        """Detect double signing (validator signed two different blocks at same height)"""
        if block_hash1 == block_hash2:
            return None

        hash_a, hash_b = _sorted_hash_pair(block_hash1, block_hash2)
        return SlashingEvent(
            validator_address=validator,
            condition=SlashingCondition.DOUBLE_SIGN,
            evidence=f"Double sign detected: {hash_a} vs {hash_b} at height {height}",
            block_height=height,
            timestamp=time.time(),
            slash_rate=self.slash_rates[SlashingCondition.DOUBLE_SIGN],
            hash_a=hash_a,
            hash_b=hash_b,
        )

    def detect_unavailability(self, validator: str, missed_blocks: int, height: int) -> SlashingEvent | None:
        """Detect validator unavailability (missing consensus participation)"""
        if missed_blocks < self.slash_thresholds[SlashingCondition.UNAVAILABLE]:
            return None

        return SlashingEvent(
            validator_address=validator,
            condition=SlashingCondition.UNAVAILABLE,
            evidence=f"Missed {missed_blocks} consecutive blocks",
            block_height=height,
            timestamp=time.time(),
            slash_rate=self.slash_rates[SlashingCondition.UNAVAILABLE],
        )

    def detect_invalid_block(self, validator: str, block_hash: str, reason: str, height: int) -> SlashingEvent | None:
        """Detect invalid block proposal"""
        return SlashingEvent(
            validator_address=validator,
            condition=SlashingCondition.INVALID_BLOCK,
            evidence=f"Invalid block {block_hash}: {reason}",
            block_height=height,
            timestamp=time.time(),
            slash_rate=self.slash_rates[SlashingCondition.INVALID_BLOCK],
        )

    def detect_slow_response(
        self, validator: str, response_time: float, threshold: float, height: int
    ) -> SlashingEvent | None:
        """Detect slow consensus participation"""
        if response_time <= threshold:
            return None

        return SlashingEvent(
            validator_address=validator,
            condition=SlashingCondition.SLOW_RESPONSE,
            evidence=f"Slow response: {response_time}s (threshold: {threshold}s)",
            block_height=height,
            timestamp=time.time(),
            slash_rate=self.slash_rates[SlashingCondition.SLOW_RESPONSE],
        )

    def apply_slashing(self, validator: Validator, event: SlashingEvent) -> bool:
        """Levy the penalty on the validator, and record what it cost.

        The pre-slash stake and the deducted amount are written onto the event. Without
        them the penalty is unreconstructable the moment the stake changes again, which is
        what left `calculate_total_slashed` with nothing to sum but rates.
        """
        # #1206: an equivalent event already on record means this offense was
        # already observed — re-slashing would double-charge the validator and
        # double-count the evidence. Return False without mutating stake; but
        # #1263 still upgrades the recorded evidence in place when this
        # observation carries signatures the old record lacked.
        new_key = _equivocation_dedup_key(event)
        for existing in self.slashing_events:
            if _equivocation_dedup_key(existing) == new_key:
                if event_signature_evidence(event) is not None and event_signature_evidence(existing) is None:
                    existing.evidence = event.evidence
                return False

        stake_before = validator.stake
        slashed_amount = stake_before * Decimal(str(event.slash_rate))
        validator.stake = stake_before - slashed_amount

        event.stake_before = stake_before
        event.slashed_amount = slashed_amount

        # Demote validator role if stake is too low
        if validator.stake < MIN_ACTIVE_STAKE:
            validator.role = ValidatorRole.STANDBY

        # Record slashing event
        self.slashing_events.append(event)

        return True

    def get_validator_slash_count(self, validator_address: str, condition: SlashingCondition) -> int:
        """Get count of slashing events for validator and condition"""
        return len(
            [
                event
                for event in self.slashing_events
                if event.validator_address == validator_address and event.condition == condition
            ]
        )

    def should_slash(self, validator: str, condition: SlashingCondition) -> bool:
        """Check if validator should be slashed for condition"""
        current_count = self.get_validator_slash_count(validator, condition)
        threshold = self.slash_thresholds.get(condition, 1)
        return current_count >= threshold

    def get_slashing_history(self, validator_address: str | None = None) -> list[SlashingEvent]:
        """Get slashing history for validator or all validators"""
        if validator_address:
            return [event for event in self.slashing_events if event.validator_address == validator_address]
        return self.slashing_events.copy()

    def events_for(self, validator_address: str, *, max_block_height: int | None = None) -> list[SlashingEvent]:
        """This validator's events, optionally bounded by sealed height (#1263).

        Same matching and height rule as ``evidence_bundle`` — the draft path
        needs the events themselves (not just the hash) to assemble the v2
        ``evidence`` payload.
        """
        from aitbc.crypto.signature_recovery import canonical_address

        target = canonical_address(validator_address)
        return [
            e
            for e in self.slashing_events
            if (canonical_address(e.validator_address) == target or e.validator_address == validator_address)
            and (max_block_height is None or e.block_height <= max_block_height)
        ]

    def calculate_total_slashed(self, validator_address: str) -> Decimal:
        """Total stake actually deducted from this validator.

        Sums `slashed_amount`, which only applied events carry -- a detected-but-never-levied
        event contributes nothing, because nothing was taken. Previously this summed
        `slash_amount`, which held the *rate*, so three double-signs reported 1.5 regardless
        of how much stake had really been lost.
        """
        events = self.get_slashing_history(validator_address)
        return sum((e.slashed_amount for e in events if e.slashed_amount is not None), Decimal("0"))

    def _dedup_or_upgrade(self, event: SlashingEvent) -> SlashingEvent:
        """Return the on-record equivalent of ``event``, upgrading it in place.

        #1263: when the new observation carries signature material and the
        recorded one doesn't (e.g. the first signature predated capture, or a
        restart lost the in-memory index), the existing event's evidence is
        replaced — same offense, strictly better evidence — rather than
        appending a duplicate or keeping the unverifiable record forever.
        """
        new_key = _equivocation_dedup_key(event)
        for existing in self.slashing_events:
            if _equivocation_dedup_key(existing) != new_key:
                continue
            if event_signature_evidence(event) is not None and event_signature_evidence(existing) is None:
                existing.evidence = event.evidence
            return existing
        self.slashing_events.append(event)
        return event

    def record_attestation_equivocation(
        self,
        validator_address: str,
        height: int,
        round_number: int | None,
        block_hash_a: str,
        block_hash_b: str,
        proposer: str = "",
        attestations: list[dict] | None = None,
    ) -> SlashingEvent:
        """Record attestation-layer equivocation evidence (#1198 / #1242 / #1263).

        Advisory only: appends a DOUBLE_SIGN event so the evidence bundle and
        divergence tooling see it. Deactivation is never applied here — under
        ``CONSENSUS_CHAIN_SLASHING_ENABLED`` the on-chain
        ``VALIDATOR_DEACTIVATE`` marker is the only thing that removes a
        validator from the active set, and it requires the slash authority's
        signature. ``round_number`` is ``None`` for legacy (height-only) locks.

        #1206: the hash pair is stored in canonical sorted order and the event
        carries structured ``round_number``/``hash_a``/``hash_b`` fields, so
        the same observed equivocation produces byte-identical evidence on
        every node. #1263: ``attestations`` carries the two signed attestation
        records (sorted by hash) that on-chain verification recovers — without
        them the event stays advisory-only and can never satisfy the
        ``validator_deactivation_evidence_required`` gate.
        """
        hash_a, hash_b = _sorted_hash_pair(block_hash_a, block_hash_b)
        evidence = {
            "kind": "attestation_equivocation",
            "height": height,
            "round": round_number,
            "block_hash_a": hash_a,
            "block_hash_b": hash_b,
            "proposer": proposer,
        }
        if attestations:
            evidence["attestations"] = sorted(attestations, key=lambda a: str(a.get("hash", "")).lower())
        event = SlashingEvent(
            validator_address=validator_address,
            condition=SlashingCondition.DOUBLE_SIGN,
            evidence=json.dumps(evidence, sort_keys=True),
            block_height=height,
            timestamp=time.time(),
            slash_rate=self.slash_rates[SlashingCondition.DOUBLE_SIGN],
            round_number=round_number,
            hash_a=hash_a,
            hash_b=hash_b,
        )
        return self._dedup_or_upgrade(event)

    def vote_equivocation_event(
        self,
        validator_address: str,
        view: int,
        phase: str,
        message_a: dict,
        message_b: dict,
    ) -> SlashingEvent:
        """Build a PBFT prepare/commit vote-equivocation event (#1263).

        ``message_a``/``message_b`` are the signed-field subsets of the two
        conflicting PBFT messages (``message_type``, ``sender``,
        ``view_number``, ``sequence_number``, ``digest``, ``block_hash``,
        ``signature``), stored canonically sorted by ``block_hash``. Like
        ``detect_double_sign`` this only *builds* the event — the caller
        levies it via ``apply_slashing``. The event mirrors
        ``detect_double_sign``'s shape — ``block_height`` holds the view
        number and ``round_number`` stays None — so the dedup key matches a
        legacy record of the same offense.
        """
        hash_a, hash_b = _sorted_hash_pair(str(message_a.get("block_hash", "")), str(message_b.get("block_hash", "")))
        ordered = sorted((message_a, message_b), key=lambda m: str(m.get("block_hash", "")).lower())
        evidence = {
            "kind": "vote_equivocation",
            "view": view,
            "sequence": message_a.get("sequence_number"),
            "phase": phase,
            "messages": ordered,
        }
        return SlashingEvent(
            validator_address=validator_address,
            condition=SlashingCondition.DOUBLE_SIGN,
            evidence=json.dumps(evidence, sort_keys=True),
            block_height=view,
            timestamp=time.time(),
            slash_rate=self.slash_rates[SlashingCondition.DOUBLE_SIGN],
            hash_a=hash_a,
            hash_b=hash_b,
        )

    def evidence_bundle(self, validator_address: str, *, max_block_height: int | None = None) -> dict:
        """Canonical evidence bundle for ``validator_address`` (#1198 / #1206).

        The ``evidence_hash`` a ``VALIDATOR_DEACTIVATE`` payload commits to is
        the sha256 of this bundle's canonical JSON. #1206 made it reproducible
        across nodes: wall-clock ``timestamp`` and the locally-mutated
        ``stake_before``/``slashed_amount`` are excluded, structured equivocation
        fields are included, and ``max_block_height`` bounds the bundle to
        events sealed at or below that height (the draft path's finality
        filter).
        """
        from aitbc.crypto.signature_recovery import canonical_address

        target = canonical_address(validator_address)
        events = []
        for e in self.slashing_events:
            if canonical_address(e.validator_address) != target and e.validator_address != validator_address:
                continue
            if max_block_height is not None and e.block_height > max_block_height:
                continue
            events.append(
                {
                    "condition": e.condition.value,
                    "evidence": e.evidence,
                    "block_height": e.block_height,
                    "round_number": e.round_number,
                    "hash_a": e.hash_a,
                    "hash_b": e.hash_b,
                }
            )
        events.sort(
            key=lambda e: (e["block_height"], e["condition"], e["evidence"], e["round_number"] or -1, e["hash_a"], e["hash_b"])
        )
        # #1263: canonicalize the wrapper address too — env spellings of the
        # same validator differ across nodes, and the hash must not.
        return {"validator_address": canonical_address(validator_address), "events": events}

    def evidence_hash(self, validator_address: str, *, max_block_height: int | None = None) -> str:
        """sha256 over the canonical evidence bundle — the payload value."""
        canonical = json.dumps(
            self.evidence_bundle(validator_address, max_block_height=max_block_height),
            sort_keys=True,
            separators=(",", ":"),
        )
        return "0x" + hashlib.sha256(canonical.encode()).hexdigest()

    def calculate_total_slashed_by_condition(self, validator_address: str) -> dict[SlashingCondition, Decimal]:
        """The same total, broken down by what earned it."""
        totals: dict[SlashingCondition, Decimal] = {}
        for event in self.get_slashing_history(validator_address):
            if event.slashed_amount is None:
                continue
            totals[event.condition] = totals.get(event.condition, Decimal("0")) + event.slashed_amount
        return totals


# Global slashing manager
slashing_manager = SlashingManager()
