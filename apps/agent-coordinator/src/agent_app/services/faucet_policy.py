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

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
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


def address_spellings(address: str) -> list[str]:
    """Every way the same address can be written, so a lookup cannot miss one.

    `ait1<body>`, `aitbc1<body>` and `0x<body>` are the same twenty bytes, and the prior-grant
    check below is only worth anything if it sees through that. `canonical_address` strips a
    prefix only when exactly 40 hex characters follow, so this never widens to a different
    account (V23-54, V23-63).
    """
    canonical = canonical_address(address)
    body = canonical.removeprefix("0x")
    if canonical.startswith("0x") and len(body) == 40:
        return [f"0x{body}", f"ait1{body}", f"aitbc1{body}"]
    return [canonical]


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

    return CoinRequestStatus.APPROVED, "first grant for this agent and wallet, within the automatic ceiling"
