"""Offer state machine for compute/GPU marketplace (v0.6.6 §A1).

Provides a formal finite state machine for offer lifecycle management.
Validates state transitions and rejects invalid ones. Terminal states
(DELISTED, EXPIRED) cannot transition further.

States:
    AVAILABLE  → offer is listed and bookable
    RESERVED   → offer is matched/locked for a consumer
    IN_USE     → offer is actively being used (compute running)
    DELISTED   → offer is permanently removed by provider (terminal)
    EXPIRED    → offer timed out without being used (terminal)

Valid transitions:
    AVAILABLE → RESERVED, DELISTED, EXPIRED
    RESERVED  → IN_USE, AVAILABLE (release), EXPIRED
    IN_USE    → AVAILABLE (completed), DELISTED
    DELISTED  → (terminal)
    EXPIRED   → (terminal)
"""

from __future__ import annotations

import logging
from enum import StrEnum

logger = logging.getLogger(__name__)


class OfferStatus(StrEnum):
    """Lifecycle states for a compute/GPU offer."""

    AVAILABLE = "available"  # Offer is listed and bookable
    RESERVED = "reserved"  # Offer is matched/locked for a consumer
    IN_USE = "in_use"  # Offer is actively being used (compute running)
    DELISTED = "delisted"  # Offer is permanently removed by provider
    EXPIRED = "expired"  # Offer timed out without being used


# Valid state transitions: {current_status: set_of_allowed_next_statuses}
_TRANSITIONS: dict[OfferStatus, set[OfferStatus]] = {
    OfferStatus.AVAILABLE: {OfferStatus.RESERVED, OfferStatus.DELISTED, OfferStatus.EXPIRED},
    OfferStatus.RESERVED: {OfferStatus.IN_USE, OfferStatus.AVAILABLE, OfferStatus.EXPIRED},
    OfferStatus.IN_USE: {OfferStatus.AVAILABLE, OfferStatus.DELISTED},
    OfferStatus.DELISTED: set(),  # terminal
    OfferStatus.EXPIRED: set(),  # terminal
}


class OfferFSM:
    """Finite state machine for offer lifecycle.

    Validates state transitions and rejects invalid ones.
    Terminal states (DELISTED, EXPIRED) cannot transition further.
    """

    def __init__(self, initial_status: OfferStatus = OfferStatus.AVAILABLE) -> None:
        self._status = initial_status

    @property
    def status(self) -> OfferStatus:
        """Current offer status."""
        return self._status

    def can_transition(self, new_status: OfferStatus) -> bool:
        """Check if a transition is valid without performing it."""
        return new_status in _TRANSITIONS.get(self._status, set())

    def transition(self, new_status: OfferStatus) -> OfferStatus:
        """Transition to a new status.

        Raises ValueError if the transition is invalid.
        Returns the new status.
        """
        if not self.can_transition(new_status):
            raise ValueError(f"Invalid offer transition: {self._status.value} → {new_status.value}")
        old = self._status
        self._status = new_status
        logger.info("Offer transitioned: %s → %s", old.value, new_status.value)
        return self._status

    def is_terminal(self) -> bool:
        """Check if the current status is terminal (no further transitions)."""
        return len(_TRANSITIONS.get(self._status, set())) == 0

    @staticmethod
    def valid_transitions(status: OfferStatus) -> set[OfferStatus]:
        """Return the set of valid next statuses from a given status."""
        return _TRANSITIONS.get(status, set()).copy()

    @staticmethod
    def from_string(status: str) -> OfferStatus:
        """Convert a string to OfferStatus.

        Raises ValueError if the string is not a valid status.
        """
        try:
            return OfferStatus(status)
        except ValueError as e:
            raise ValueError(f"Unknown offer status: '{status}'") from e
