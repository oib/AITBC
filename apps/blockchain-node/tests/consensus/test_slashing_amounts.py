"""What a slashing penalty actually cost, and whether it survives a restart.

V23-48. `SlashingEvent.slash_amount` held a *rate* — 0.05 to 0.5 from `slash_rates` — and
`apply_slashing` multiplied it by the validator's stake to get the quantity deducted, then
threw that quantity away. `calculate_total_slashed` summed the rates and returned them as
"total amount slashed", so three double-signs reported 1.5 regardless of how much stake had
really been taken.

Two things had to change for that function to be fixable at all: the amount has to be
recorded when it is levied, and the history has to survive a restart. It did not — the
persisted `slashing_events_json` was written and never read back, which also silently reset
the offence counters that drive the thresholds.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, Validator, ValidatorRole
from aitbc_chain.consensus.slashing import SlashingCondition, SlashingEvent, SlashingManager

ADDR = "0x" + "aa" * 20
OTHER = "0x" + "bb" * 20


def _validator(stake: str = "1000") -> Validator:
    return Validator(
        address=ADDR,
        stake=Decimal(stake),
        reputation=1.0,
        role=ValidatorRole.VALIDATOR,
        last_proposed=0,
        is_active=True,
    )


@pytest.fixture
def manager() -> SlashingManager:
    return SlashingManager()


# ---------------------------------------------------------------------------------------
# The defect
# ---------------------------------------------------------------------------------------


def test_the_event_separates_the_rate_from_the_amount(manager):
    """A detected event carries a rate and no amount, because nothing has been taken yet."""
    event = manager.detect_double_sign(ADDR, "hashA", "hashB", 10)

    assert event.slash_rate == 0.5
    assert event.slashed_amount is None
    assert event.stake_before is None
    assert event.is_applied is False


def test_applying_records_what_it_cost(manager):
    validator = _validator("1000")
    event = manager.detect_double_sign(ADDR, "hashA", "hashB", 10)

    manager.apply_slashing(validator, event)

    assert event.stake_before == Decimal("1000")
    assert event.slashed_amount == Decimal("500.0")
    assert validator.stake == Decimal("500.0")
    assert event.is_applied is True
    # the three are consistent, which is what makes the record auditable
    assert event.stake_before * Decimal(str(event.slash_rate)) == event.slashed_amount


def test_total_slashed_is_an_amount_not_a_sum_of_rates(manager):
    """The headline fix.

    Three double-signs at 50% on a 1000 stake take 500, then 250, then 125 — 875 in total.
    The old implementation summed the rates and answered 1.5.
    """
    validator = _validator("1000")
    for i in range(3):
        event = manager.detect_double_sign(ADDR, f"hashA{i}", f"hashB{i}", 10 + i)
        manager.apply_slashing(validator, event)

    assert manager.calculate_total_slashed(ADDR) == Decimal("875.0")
    assert validator.stake == Decimal("125.0")
    # stake lost + stake remaining == stake started with, exactly
    assert manager.calculate_total_slashed(ADDR) + validator.stake == Decimal("1000")

    rates = sum(e.slash_rate for e in manager.get_slashing_history(ADDR))
    assert rates == 1.5, "the old answer, kept here so the difference is legible"


def test_total_slashed_is_exact_where_float_would_not_be(manager):
    """A 5% slow-response penalty on 0.1 stake. In binary float this is 0.005000000000000001."""
    validator = _validator("0.1")
    event = manager.detect_slow_response(ADDR, response_time=10.0, threshold=1.0, height=1)
    manager.apply_slashing(validator, event)

    assert manager.calculate_total_slashed(ADDR) == Decimal("0.005")
    assert 0.1 * 0.05 != 0.005, "the float product this replaces"


def test_detected_but_unapplied_events_contribute_nothing(manager):
    """`should_slash` gates whether a detection is levied, so unlevied events exist."""
    validator = _validator("1000")
    applied = manager.detect_double_sign(ADDR, "a", "b", 1)
    manager.apply_slashing(validator, applied)

    detected_only = manager.detect_invalid_block(ADDR, "hash", "bad state root", 2)
    manager.slashing_events.append(detected_only)

    assert detected_only.slashed_amount is None
    assert manager.calculate_total_slashed(ADDR) == Decimal("500.0"), "only the levied one counts"


def test_totals_are_per_validator(manager):
    v1, v2 = _validator("1000"), Validator(OTHER, Decimal("200"), 1.0, ValidatorRole.STANDBY, 0, True)
    manager.apply_slashing(v1, manager.detect_double_sign(ADDR, "a", "b", 1))
    e2 = manager.detect_double_sign(OTHER, "a", "b", 1)
    e2.validator_address = OTHER
    manager.apply_slashing(v2, e2)

    assert manager.calculate_total_slashed(ADDR) == Decimal("500.0")
    assert manager.calculate_total_slashed(OTHER) == Decimal("100.0")


def test_breakdown_by_condition(manager):
    validator = _validator("1000")
    manager.apply_slashing(validator, manager.detect_double_sign(ADDR, "a", "b", 1))  # 50% of 1000
    manager.apply_slashing(validator, manager.detect_invalid_block(ADDR, "h", "why", 2))  # 30% of 500

    totals = manager.calculate_total_slashed_by_condition(ADDR)

    assert totals[SlashingCondition.DOUBLE_SIGN] == Decimal("500.0")
    assert totals[SlashingCondition.INVALID_BLOCK] == Decimal("150.0")
    assert sum(totals.values()) == manager.calculate_total_slashed(ADDR)


def test_demotion_still_happens_below_the_minimum(manager):
    """The threshold comparison now runs against a Decimal; pin that it still fires."""
    validator = _validator("150")
    manager.apply_slashing(validator, manager.detect_double_sign(ADDR, "a", "b", 1))

    assert validator.stake == Decimal("75.0")
    assert validator.role is ValidatorRole.STANDBY


# ---------------------------------------------------------------------------------------
# Persistence — the history was write-only
# ---------------------------------------------------------------------------------------


def test_persisted_records_round_trip():
    applied = SlashingEvent(
        validator_address=ADDR,
        condition=SlashingCondition.DOUBLE_SIGN,
        evidence="double sign at 10",
        block_height=10,
        timestamp=1700000000.0,
        slash_rate=0.5,
        stake_before=Decimal("1000"),
        slashed_amount=Decimal("500.0"),
    )
    record = {
        "validator_address": applied.validator_address,
        "condition": applied.condition.value,
        "evidence": applied.evidence,
        "block_height": applied.block_height,
        "timestamp": applied.timestamp,
        "slash_rate": applied.slash_rate,
        "stake_before": str(applied.stake_before),
        "slashed_amount": str(applied.slashed_amount),
    }
    # it must survive JSON, which is what the column actually holds
    parsed = MultiValidatorPoA._parse_slashing_events(json.loads(json.dumps([record])))

    assert len(parsed) == 1
    assert parsed[0].slash_rate == 0.5
    assert parsed[0].stake_before == Decimal("1000")
    assert parsed[0].slashed_amount == Decimal("500.0")
    assert parsed[0].condition is SlashingCondition.DOUBLE_SIGN


def test_legacy_records_keep_their_rate_and_admit_the_amount_is_unknown():
    """Pre-V23-48 rows carry `slash_amount` holding the rate, and no amount at all.

    The deducted quantity was never written down, and it cannot be re-derived because the
    stake at the time was not recorded either. So it stays None and is excluded from totals —
    a total over old history is a lower bound, which is the honest answer rather than a
    fabricated one.
    """
    legacy = {
        "validator_address": ADDR,
        "condition": "double_sign",
        "evidence": "double sign at 10",
        "block_height": 10,
        "timestamp": 1700000000.0,
        "slash_amount": 0.5,  # the rate, under the old name
    }

    parsed = MultiValidatorPoA._parse_slashing_events([legacy])

    assert parsed[0].slash_rate == 0.5, "the legacy value was a rate and is read as one"
    assert parsed[0].slashed_amount is None
    assert parsed[0].stake_before is None
    assert parsed[0].is_applied is False

    manager = SlashingManager()
    manager.slashing_events = parsed
    assert manager.calculate_total_slashed(ADDR) == Decimal("0"), "unknown is not 0.5"


def test_unreadable_records_are_skipped_not_fatal():
    """One corrupt row must not take the whole history with it on startup."""
    good = {
        "validator_address": ADDR,
        "condition": "double_sign",
        "evidence": "",
        "block_height": 1,
        "timestamp": 0.0,
        "slash_rate": 0.5,
    }
    parsed = MultiValidatorPoA._parse_slashing_events(
        [{"condition": "double_sign"}, {"validator_address": ADDR, "condition": "not-a-condition"}, good]
    )

    assert len(parsed) == 1
    assert parsed[0].validator_address == ADDR


def test_an_empty_history_parses_to_nothing():
    assert MultiValidatorPoA._parse_slashing_events([]) == []
