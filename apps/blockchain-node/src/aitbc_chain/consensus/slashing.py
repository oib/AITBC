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

    @property
    def is_applied(self) -> bool:
        """Whether this event actually cost the validator anything."""
        return self.slashed_amount is not None


# Below this, a validator is demoted to standby. Named because it is now compared against a
# Decimal stake, and a bare `100` next to money reads as a magic number.
MIN_ACTIVE_STAKE = Decimal("100")


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

        return SlashingEvent(
            validator_address=validator,
            condition=SlashingCondition.DOUBLE_SIGN,
            evidence=f"Double sign detected: {block_hash1} vs {block_hash2} at height {height}",
            block_height=height,
            timestamp=time.time(),
            slash_rate=self.slash_rates[SlashingCondition.DOUBLE_SIGN],
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

    def calculate_total_slashed(self, validator_address: str) -> Decimal:
        """Total stake actually deducted from this validator.

        Sums `slashed_amount`, which only applied events carry -- a detected-but-never-levied
        event contributes nothing, because nothing was taken. Previously this summed
        `slash_amount`, which held the *rate*, so three double-signs reported 1.5 regardless
        of how much stake had really been lost.
        """
        events = self.get_slashing_history(validator_address)
        return sum((e.slashed_amount for e in events if e.slashed_amount is not None), Decimal("0"))

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
