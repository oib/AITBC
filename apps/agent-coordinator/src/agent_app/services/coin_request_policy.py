"""How much the hub will pay an agent without a human saying so (V23-62).

The hub already had this rule, in `websocket.agent_stream.request_coins_handler`: an agent's
first request is granted automatically, anything after that waits for manual approval. That
rule lived inside the WebSocket handler because the WebSocket was the only way to create a
request. Registration is a second way in, so the rule moves somewhere both can reach.

The rule is what makes registration safe to expose. Without it, a caller could register a
request for any amount and immediately execute it, which is the defect the execute fix closed
wearing a second coat of paint. With it, the shared API key buys a request *subject to policy*
rather than a payment, and anything outside the policy needs a hub operator.

V23 review addendum: the per-identity rule alone is not enough — `sender` and
`wallet_address` are caller-supplied and cost nothing to mint, so "one grant per
pair" is "one grant per fresh pair". The rolling hourly/daily budgets below cap
the aggregate the faucet can pay in a window no matter how many identities
appear; past them, requests park at manual review and a warning is logged.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.models import CoinRequest, CoinRequestStatus
from aitbc.utils.units import ait_to_units

from ..monitoring.prometheus_metrics import metrics_registry

logger = get_logger(__name__)

# 3 AIT in compute-units — matches INITIAL_COIN_AMOUNT in websocket.agent_stream, which is the
# grant the hub makes automatically.
DEFAULT_AUTO_APPROVE_MAX = ait_to_units(3)

# Rolling-window budgets for automatic grants. The per-identity rule stops
# repeats, but `sender` is a caller-supplied string and `wallet_address` is
# free to mint — nothing proves either, so "one grant per agent and wallet" is
# one grant per fresh pair. Without an aggregate cap a loop of novel pairs
# drains the faucet at request speed: 3 AIT each, hundreds a minute. The
# budget bounds the worst case whatever the identities are: past it, requests
# wait for an operator. Defaults cover a fleet-onboarding burst (four nodes
# registered within seconds on 2026-09-09) many times over.
#
# The check reads the window sum before the caller's row is written, so it is
# an advisory bound rather than an invariant: N racing registrations can each
# see the pre-insert sum. Overshoot is bounded by concurrent callers — the
# per-IP rate limit on /register keeps that small — versus the unbounded drain
# this closes.
DEFAULT_AUTO_BUDGET_PER_HOUR = ait_to_units(24)  # ~8 maximum-size grants
DEFAULT_AUTO_BUDGET_PER_DAY = ait_to_units(60)  # ~20 maximum-size grants


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(int(raw), 0)
    except ValueError:
        logger.warning("%s=%r is not an integer; using %s", name, raw, default)
        return default


def auto_approve_ceiling() -> int:
    """The largest amount the hub will approve without a human.

    Set `COIN_REQUEST_AUTO_APPROVE_MAX` to 0 to turn automatic approval off entirely, which makes
    every registered request wait for an operator.
    """
    return _env_int("COIN_REQUEST_AUTO_APPROVE_MAX", DEFAULT_AUTO_APPROVE_MAX)


def auto_budget_per_hour() -> int:
    """The most the faucet may auto-grant in any rolling hour.

    `COIN_REQUEST_AUTO_BUDGET_PER_HOUR=0` parks every request at manual review
    (same effect as disabling the ceiling). The per-day knob is
    `COIN_REQUEST_AUTO_BUDGET_PER_DAY`.
    """
    return _env_int("COIN_REQUEST_AUTO_BUDGET_PER_HOUR", DEFAULT_AUTO_BUDGET_PER_HOUR)


def auto_budget_per_day() -> int:
    return _env_int("COIN_REQUEST_AUTO_BUDGET_PER_DAY", DEFAULT_AUTO_BUDGET_PER_DAY)


def _auto_granted_since(session: Session, since: datetime) -> int:
    """Total amount auto-approved since `since` (created_at is stored naive-UTC)."""
    total = (
        session.query(func.coalesce(func.sum(CoinRequest.amount), 0))
        .filter(
            CoinRequest.status == CoinRequestStatus.APPROVED,
            CoinRequest.approval_mode == "automatic",
            CoinRequest.created_at >= since,
        )
        .scalar()
    )
    return int(total or 0)


def address_spellings(address: str) -> list[str]:
    """The canonical 0x spelling of an address, for a case-insensitive lookup.

    The hub now stores and accepts only EIP-55 secp256k1/EVM addresses, so the
    prior-grant check only needs the canonical `0x` form. `canonical_address`
    returns that form for valid 0x addresses and lowercases anything else, so
    non-address strings (such as node ids that also reach this field) are still
    matched as themselves.
    """
    return [canonical_address(address).lower()]


def has_prior_grant(session: Session, sender: str, wallet_address: str) -> bool:
    """Has this destination — or this agent — already been granted coins?

    Counts approved requests whether or not they have been executed yet. `agent_stream` counts
    only executed ones, which is safe there because it signs immediately — the gap between
    approving and paying is microseconds. Here the gap is however long the operator takes to
    run `execute`, so counting only executed requests would let an agent register twice, collect
    two approvals and spend both.

    Keyed on the destination as well as the sender, because `sender` is a self-declared string
    in the registration body and nothing ties it to an identity. Keying on it alone meant a
    caller could collect a second automatic grant to the same wallet just by renaming itself,
    which is how `req-follower-1782118019-v2` auto-approved after `req-follower-1782118019`
    had already been granted: same `wallet_address`, `sender` changed from `follower` to
    `follower-ait-reset` (V23-67). The wallet is the thing that receives the money, so it is
    the thing the ceiling has to be counted against.

    The sender check stays as well. It costs one clause and catches an agent asking twice for
    two different wallets, which the destination check alone would allow.
    """
    return (
        session.query(CoinRequest)
        .filter(
            CoinRequest.status == CoinRequestStatus.APPROVED,
            or_(
                CoinRequest.sender == sender,
                func.lower(CoinRequest.wallet_address).in_(address_spellings(wallet_address)),
            ),
        )
        .first()
        is not None
    )


def decide(session: Session, sender: str, amount: int, wallet_address: str) -> tuple[CoinRequestStatus, str]:
    """Return the status a newly registered request should take, and why.

    The reason is returned rather than logged here so the caller can hand it back to whoever
    registered the request — an operator who can see "over the automatic ceiling" knows to go
    and approve it, where a bare `pending` tells them nothing.
    """
    ceiling = auto_approve_ceiling()

    if ceiling == 0:
        return CoinRequestStatus.PENDING, "automatic approval is disabled on this hub"
    if amount > ceiling:
        return CoinRequestStatus.PENDING, f"amount {amount} is above the automatic ceiling of {ceiling}"
    if has_prior_grant(session, sender, wallet_address):
        return CoinRequestStatus.PENDING, f"{sender} or {wallet_address} has already been granted coins"

    now = datetime.now(UTC).replace(tzinfo=None)
    hour_budget = auto_budget_per_hour()
    hour_spent = _auto_granted_since(session, now - timedelta(hours=1))
    day_budget = auto_budget_per_day()
    day_spent = _auto_granted_since(session, now - timedelta(hours=24))
    # Expose the running totals — alerting watches these rather than journals.
    metrics_registry.gauge("coin_request_auto_granted_window", "Automatic coin grants in the rolling window", ["window"]).set(
        float(hour_spent), window="hourly"
    )
    metrics_registry.gauge("coin_request_auto_granted_window", "Automatic coin grants in the rolling window", ["window"]).set(
        float(day_spent), window="daily"
    )
    if hour_spent + amount > hour_budget:
        metrics_registry.counter(
            "coin_request_auto_budget_trips_total", "Requests parked by an exhausted automatic budget", ["window"]
        ).inc(window="hourly")
        logger.warning(
            "Automatic coin-request hourly budget exceeded: %s already granted + %s requested > %s. "
            "Request parks at manual review. Sustained trips mean either a fleet-wide rollout or a "
            "drain attempt — check the sender/wallet mix before approving.",
            hour_spent,
            amount,
            hour_budget,
        )
        return CoinRequestStatus.PENDING, "the automatic hourly budget is exhausted"

    if day_spent + amount > day_budget:
        metrics_registry.counter(
            "coin_request_auto_budget_trips_total", "Requests parked by an exhausted automatic budget", ["window"]
        ).inc(window="daily")
        logger.warning(
            "Automatic coin-request daily budget exceeded: %s already granted + %s requested > %s. "
            "Request parks at manual review.",
            day_spent,
            amount,
            day_budget,
        )
        return CoinRequestStatus.PENDING, "the automatic daily budget is exhausted"

    return CoinRequestStatus.APPROVED, "first grant for this agent and wallet, within the automatic ceiling"
