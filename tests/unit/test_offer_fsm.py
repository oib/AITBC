"""Unit tests for aitbc.marketplace.offer_fsm (v0.6.6 §A3).

Covers the full offer lifecycle state machine: valid transitions,
invalid transitions (raise ValueError), terminal states, and helper
methods (can_transition, is_terminal, valid_transitions, from_string).
"""

from __future__ import annotations

import pytest

from aitbc.marketplace.offer_fsm import OfferFSM, OfferStatus


# ---------------------------------------------------------------------------
# initial status
# ---------------------------------------------------------------------------


def test_initial_status() -> None:
    fsm = OfferFSM()
    assert fsm.status == OfferStatus.AVAILABLE


def test_initial_status_custom() -> None:
    fsm = OfferFSM(initial_status=OfferStatus.RESERVED)
    assert fsm.status == OfferStatus.RESERVED


# ---------------------------------------------------------------------------
# valid transitions
# ---------------------------------------------------------------------------


def test_valid_transition_available_to_reserved() -> None:
    fsm = OfferFSM()
    fsm.transition(OfferStatus.RESERVED)
    assert fsm.status == OfferStatus.RESERVED


def test_valid_transition_reserved_to_in_use() -> None:
    fsm = OfferFSM(OfferStatus.RESERVED)
    fsm.transition(OfferStatus.IN_USE)
    assert fsm.status == OfferStatus.IN_USE


def test_valid_transition_in_use_to_available() -> None:
    fsm = OfferFSM(OfferStatus.IN_USE)
    fsm.transition(OfferStatus.AVAILABLE)
    assert fsm.status == OfferStatus.AVAILABLE


def test_valid_transition_reserved_to_available() -> None:
    """Reserved → AVAILABLE is a release (offer returned to pool)."""
    fsm = OfferFSM(OfferStatus.RESERVED)
    fsm.transition(OfferStatus.AVAILABLE)
    assert fsm.status == OfferStatus.AVAILABLE


def test_valid_transition_available_to_delisted() -> None:
    fsm = OfferFSM()
    fsm.transition(OfferStatus.DELISTED)
    assert fsm.status == OfferStatus.DELISTED


def test_valid_transition_available_to_expired() -> None:
    fsm = OfferFSM()
    fsm.transition(OfferStatus.EXPIRED)
    assert fsm.status == OfferStatus.EXPIRED


def test_valid_transition_reserved_to_expired() -> None:
    fsm = OfferFSM(OfferStatus.RESERVED)
    fsm.transition(OfferStatus.EXPIRED)
    assert fsm.status == OfferStatus.EXPIRED


def test_valid_transition_in_use_to_delisted() -> None:
    fsm = OfferFSM(OfferStatus.IN_USE)
    fsm.transition(OfferStatus.DELISTED)
    assert fsm.status == OfferStatus.DELISTED


def test_full_lifecycle_available_reserved_in_use_available() -> None:
    """Full happy-path lifecycle: list → reserve → use → release."""
    fsm = OfferFSM()
    fsm.transition(OfferStatus.RESERVED)
    fsm.transition(OfferStatus.IN_USE)
    fsm.transition(OfferStatus.AVAILABLE)
    assert fsm.status == OfferStatus.AVAILABLE


# ---------------------------------------------------------------------------
# invalid transitions
# ---------------------------------------------------------------------------


def test_invalid_transition_available_to_in_use() -> None:
    """Cannot skip RESERVED — must reserve before using."""
    fsm = OfferFSM()
    with pytest.raises(ValueError, match="Invalid offer transition"):
        fsm.transition(OfferStatus.IN_USE)


def test_invalid_transition_delisted_to_anything() -> None:
    """Terminal state — no further transitions."""
    fsm = OfferFSM(OfferStatus.DELISTED)
    with pytest.raises(ValueError, match="Invalid offer transition"):
        fsm.transition(OfferStatus.AVAILABLE)


def test_invalid_transition_expired_to_anything() -> None:
    """Terminal state — no further transitions."""
    fsm = OfferFSM(OfferStatus.EXPIRED)
    with pytest.raises(ValueError, match="Invalid offer transition"):
        fsm.transition(OfferStatus.AVAILABLE)


def test_invalid_transition_in_use_to_reserved() -> None:
    """Cannot go back to RESERVED from IN_USE — must go to AVAILABLE first."""
    fsm = OfferFSM(OfferStatus.IN_USE)
    with pytest.raises(ValueError, match="Invalid offer transition"):
        fsm.transition(OfferStatus.RESERVED)


def test_invalid_transition_reserved_to_delisted() -> None:
    """Cannot delist while reserved — must release to AVAILABLE first."""
    fsm = OfferFSM(OfferStatus.RESERVED)
    with pytest.raises(ValueError, match="Invalid offer transition"):
        fsm.transition(OfferStatus.DELISTED)


# ---------------------------------------------------------------------------
# is_terminal
# ---------------------------------------------------------------------------


def test_is_terminal_delisted() -> None:
    fsm = OfferFSM(OfferStatus.DELISTED)
    assert fsm.is_terminal() is True


def test_is_terminal_expired() -> None:
    fsm = OfferFSM(OfferStatus.EXPIRED)
    assert fsm.is_terminal() is True


def test_is_terminal_not_available() -> None:
    fsm = OfferFSM(OfferStatus.AVAILABLE)
    assert fsm.is_terminal() is False


def test_is_terminal_not_reserved() -> None:
    fsm = OfferFSM(OfferStatus.RESERVED)
    assert fsm.is_terminal() is False


def test_is_terminal_not_in_use() -> None:
    fsm = OfferFSM(OfferStatus.IN_USE)
    assert fsm.is_terminal() is False


# ---------------------------------------------------------------------------
# can_transition
# ---------------------------------------------------------------------------


def test_can_transition_true() -> None:
    fsm = OfferFSM(OfferStatus.AVAILABLE)
    assert fsm.can_transition(OfferStatus.RESERVED) is True


def test_can_transition_false() -> None:
    fsm = OfferFSM(OfferStatus.AVAILABLE)
    assert fsm.can_transition(OfferStatus.IN_USE) is False


def test_can_transition_terminal() -> None:
    fsm = OfferFSM(OfferStatus.DELISTED)
    assert fsm.can_transition(OfferStatus.AVAILABLE) is False


# ---------------------------------------------------------------------------
# valid_transitions (static)
# ---------------------------------------------------------------------------


def test_valid_transitions_available() -> None:
    transitions = OfferFSM.valid_transitions(OfferStatus.AVAILABLE)
    assert transitions == {OfferStatus.RESERVED, OfferStatus.DELISTED, OfferStatus.EXPIRED}


def test_valid_transitions_reserved() -> None:
    transitions = OfferFSM.valid_transitions(OfferStatus.RESERVED)
    assert transitions == {OfferStatus.IN_USE, OfferStatus.AVAILABLE, OfferStatus.EXPIRED}


def test_valid_transitions_in_use() -> None:
    transitions = OfferFSM.valid_transitions(OfferStatus.IN_USE)
    assert transitions == {OfferStatus.AVAILABLE, OfferStatus.DELISTED}


def test_valid_transitions_delisted_empty() -> None:
    transitions = OfferFSM.valid_transitions(OfferStatus.DELISTED)
    assert transitions == set()


def test_valid_transitions_expired_empty() -> None:
    transitions = OfferFSM.valid_transitions(OfferStatus.EXPIRED)
    assert transitions == set()


def test_valid_transitions_returns_copy() -> None:
    """valid_transitions should return a copy so callers can't mutate the internal table."""
    t1 = OfferFSM.valid_transitions(OfferStatus.AVAILABLE)
    t1.add(OfferStatus.IN_USE)  # mutate the copy
    t2 = OfferFSM.valid_transitions(OfferStatus.AVAILABLE)
    assert OfferStatus.IN_USE not in t2


# ---------------------------------------------------------------------------
# from_string
# ---------------------------------------------------------------------------


def test_from_string_valid() -> None:
    assert OfferFSM.from_string("available") == OfferStatus.AVAILABLE
    assert OfferFSM.from_string("reserved") == OfferStatus.RESERVED
    assert OfferFSM.from_string("in_use") == OfferStatus.IN_USE
    assert OfferFSM.from_string("delisted") == OfferStatus.DELISTED
    assert OfferFSM.from_string("expired") == OfferStatus.EXPIRED


def test_from_string_invalid_raises() -> None:
    with pytest.raises(ValueError, match="Unknown offer status"):
        OfferFSM.from_string("unknown")


def test_from_string_empty_raises() -> None:
    with pytest.raises(ValueError, match="Unknown offer status"):
        OfferFSM.from_string("")


# ---------------------------------------------------------------------------
# StrEnum behavior
# ---------------------------------------------------------------------------


def test_offer_status_string_value() -> None:
    """OfferStatus is a StrEnum — values are strings."""
    assert OfferStatus.AVAILABLE == "available"
    assert OfferStatus.IN_USE == "in_use"
    assert str(OfferStatus.AVAILABLE) == "available"


# ---------------------------------------------------------------------------
# package re-export
# ---------------------------------------------------------------------------


def test_package_reexport() -> None:
    from aitbc.marketplace import OfferFSM as ExportedFSM, OfferStatus as ExportedStatus

    assert ExportedFSM is OfferFSM
    assert ExportedStatus is OfferStatus
