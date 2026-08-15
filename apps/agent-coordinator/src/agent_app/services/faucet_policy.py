"""How much the hub will pay an agent without a human saying so (V23-62).

The hub already had this rule, in `websocket.agent_stream.request_coins_handler`: an agent's
first request is granted automatically, anything after that waits for manual approval. That
rule lived inside the WebSocket handler because the WebSocket was the only way to create a
request. Registration is a second way in, so the rule moves somewhere both can reach.

The rule is what makes registration safe to expose. Without it, a caller could register a
request for any amount and immediately execute it, which is the defect the execute fix closed
wearing a second coat of paint. With it, the shared API key buys a request *subject to policy*
rather than a payment, and anything outside the policy needs a hub operator.
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger
from aitbc.models import CoinRequest, CoinRequestStatus

logger = get_logger(__name__)

# 100 AIT in seconds — matches INITIAL_COIN_AMOUNT in websocket.agent_stream, which is the
# grant the hub has always made automatically.
DEFAULT_AUTO_APPROVE_MAX = 360000


def auto_approve_ceiling() -> int:
    """The largest amount the hub will approve without a human.

    Set `FAUCET_AUTO_APPROVE_MAX` to 0 to turn automatic approval off entirely, which makes
    every registered request wait for an operator.
    """
    raw = os.getenv("FAUCET_AUTO_APPROVE_MAX")
    if raw is None:
        return DEFAULT_AUTO_APPROVE_MAX
    try:
        ceiling = int(raw)
    except ValueError:
        logger.warning("FAUCET_AUTO_APPROVE_MAX=%r is not an integer; using %s", raw, DEFAULT_AUTO_APPROVE_MAX)
        return DEFAULT_AUTO_APPROVE_MAX
    return max(ceiling, 0)


def has_prior_grant(session: Session, sender: str) -> bool:
    """Has this agent already been granted coins?

    Counts approved requests whether or not they have been executed yet. `agent_stream` counts
    only executed ones, which is safe there because it signs immediately — the gap between
    approving and paying is microseconds. Here the gap is however long the operator takes to
    run `execute`, so counting only executed requests would let an agent register twice, collect
    two approvals and spend both.
    """
    return (
        session.query(CoinRequest)
        .filter(CoinRequest.sender == sender, CoinRequest.status == CoinRequestStatus.APPROVED)
        .first()
        is not None
    )


def decide(session: Session, sender: str, amount: int) -> tuple[CoinRequestStatus, str]:
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
    if has_prior_grant(session, sender):
        return CoinRequestStatus.PENDING, f"{sender} has already been granted coins"

    return CoinRequestStatus.APPROVED, "first grant for this agent, within the automatic ceiling"
