"""The window between a result being delivered and the escrow being paid out (G3).

Before this, ``POST /v1/miners/{job_id}/result`` released the escrow in the same
request that recorded the work, so the provider signed off on its own payment: the
act of submitting a result was the act of collecting for it. A customer who got a
wrong, empty or truncated answer had no moment in which the money was still
recoverable.

An acceptance window puts a bounded pause there. The result is recorded and the
escrow stays locked, now in ``pending_acceptance``. Inside the window the customer
may release early by accepting, or move the payment to ``disputed`` by rejecting
it. If neither happens the sweeper releases on expiry, so a customer who simply
walks away cannot strand a provider's earnings.

Both new states describe money that is still locked on-chain, which is why release
and refund keep accepting them.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

PENDING_ACCEPTANCE = "pending_acceptance"
DISPUTED = "disputed"

# Terminal state for an escrow whose release kept failing past the retry bound:
# the funds are still locked on-chain, but every automatic release path has given
# up and an operator has to reset it (or refund it) deliberately. Deliberately
# NOT in HELD_STATES -- every release sweeper's candidate set is built from it,
# so leaving the set is what stops the retries. Fits job_payments.status (20).
SETTLEMENT_FAILED = "settlement_failed"

# Payment states in which the escrow is still funded and settlement in either
# direction is still possible. Both fit job_payments.status (max_length=20).
HELD_STATES = frozenset({"escrowed", PENDING_ACCEPTANCE, DISPUTED})

# Held plus the terminal-release state: everything still backed by on-chain
# escrow money. Refund paths accept this wider set -- a payment whose release
# failed terminally is still the customer's money and must stay refundable.
REFUNDABLE_STATES = HELD_STATES | {SETTLEMENT_FAILED}

# An hour is long enough to look at a result and short enough that a provider is
# not financing the customer's inattention.
DEFAULT_WINDOW_SECONDS = 3600
DEFAULT_MAX_WINDOW_SECONDS = 7 * 24 * 3600

# Twenty attempts at the slowest sweeper interval (300 s) is ~100 minutes of
# retries before a stuck release goes terminal -- long enough to ride out a
# transient RPC outage, short enough that a permanently blocked release stops
# hammering the chain the same day rather than forever.
DEFAULT_MAX_RELEASE_ATTEMPTS = 20

META_DEADLINE = "acceptance_deadline"
META_OPENED_AT = "acceptance_opened_at"
META_DISPUTE_REASON = "dispute_reason"
META_DISPUTED_AT = "disputed_at"
META_RELEASE_ATTEMPTS = "release_attempts"
META_RELEASE_BLOCKED_AT = "release_blocked_at"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def default_window_seconds() -> int:
    """The operator's acceptance window in seconds. Zero releases on result, as before."""
    return max(0, _env_int("COORDINATOR_ACCEPTANCE_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS))


def max_window_seconds() -> int:
    """The longest window a single job may ask for."""
    return max(0, _env_int("COORDINATOR_ACCEPTANCE_WINDOW_MAX_SECONDS", DEFAULT_MAX_WINDOW_SECONDS))


def window_seconds_for(constraints: dict[str, Any] | None) -> int:
    """How long this job's customer gets to accept, clamped to the operator's ceiling.

    A job may name its own window through ``constraints.acceptance_window_seconds`` --
    it is the buyer's money that waits -- but not one longer than the operator allows.
    Without the clamp a submission could hold a provider's earnings for years, which
    is the same imbalance in the other direction.
    """
    window = default_window_seconds()
    if isinstance(constraints, dict):
        raw = constraints.get("acceptance_window_seconds")
        if raw is not None:
            try:
                window = max(0, int(raw))
            except (TypeError, ValueError):
                logger.warning("Ignoring unreadable acceptance_window_seconds %r", raw)
    return min(window, max_window_seconds())


def deadline_from(meta: dict[str, Any] | None) -> datetime | None:
    """Read the recorded acceptance deadline, or None if there is not a readable one."""
    if not isinstance(meta, dict):
        return None
    raw = meta.get(META_DEADLINE)
    if not raw:
        return None
    try:
        deadline = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        logger.warning("Unreadable acceptance deadline %r", raw)
        return None
    return deadline if deadline.tzinfo else deadline.replace(tzinfo=UTC)


def deadline_passed(meta: dict[str, Any] | None, now: datetime | None = None) -> bool:
    """Whether the customer's window has closed.

    A held payment carrying no readable deadline is treated as expired. It either
    predates this feature or lost its metadata, and releasing to the provider that
    did the work beats leaving the escrow unsettleable forever.
    """
    deadline = deadline_from(meta)
    if deadline is None:
        return True
    return (now or datetime.now(UTC)) >= deadline


def opened_window(meta: dict[str, Any] | None, window_seconds: int, now: datetime | None = None) -> dict[str, Any]:
    """Return ``meta`` with this job's acceptance window stamped onto it.

    The deadline lives in ``job_payments.meta_data`` beside the provider address and
    offer terms rather than in a column of its own, so no migration is needed to add
    a window to a running deployment.
    """
    opened_at = now or datetime.now(UTC)
    stamped = dict(meta or {})
    stamped[META_OPENED_AT] = opened_at.isoformat()
    stamped[META_DEADLINE] = (opened_at + timedelta(seconds=max(0, window_seconds))).isoformat()
    return stamped


def max_release_attempts() -> int:
    """How many times a held payment may be released before it goes terminal."""
    return max(1, _env_int("COORDINATOR_RELEASE_MAX_ATTEMPTS", DEFAULT_MAX_RELEASE_ATTEMPTS))


__all__ = [
    "DEFAULT_MAX_RELEASE_ATTEMPTS",
    "DEFAULT_MAX_WINDOW_SECONDS",
    "DEFAULT_WINDOW_SECONDS",
    "DISPUTED",
    "HELD_STATES",
    "META_DEADLINE",
    "META_DISPUTED_AT",
    "META_DISPUTE_REASON",
    "META_OPENED_AT",
    "META_RELEASE_ATTEMPTS",
    "META_RELEASE_BLOCKED_AT",
    "PENDING_ACCEPTANCE",
    "REFUNDABLE_STATES",
    "SETTLEMENT_FAILED",
    "deadline_from",
    "deadline_passed",
    "default_window_seconds",
    "max_release_attempts",
    "max_window_seconds",
    "opened_window",
    "window_seconds_for",
]
