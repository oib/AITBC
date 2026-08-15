"""A second grant to the same wallet, for the price of a new name (V23-67).

`req-follower-1782118019` was granted 100 AIT to `ait1c10f…`. `req-follower-1782118019-v2`
was granted 100 AIT to the same `ait1c10f…` and auto-approved, because it declared
`sender="follower-ait-reset"` where the first declared `sender="follower"`.

`has_prior_grant` keyed on `sender` alone. `sender` is a string in the registration body —
the caller writes it, nothing checks it against an identity, and changing it costs nothing.
So the faucet's one-grant-per-agent rule was really one-grant-per-*name*, and the wallet
that actually receives the money was never counted against.

The address is counted canonically for the reason V23-63 cost a day: `ait1<body>`,
`aitbc1<body>` and `0x<body>` are the same twenty bytes. Matching the stored string exactly
would have left the same bypass available to anyone who respelled the destination.

The WebSocket handler had the identical defect and is the worse of the two, because it signs
and submits on the spot rather than writing a row for an operator.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent_app.services import faucet_policy
from aitbc.db import agent_db
from aitbc.models import CoinRequest, CoinRequestStatus

WALLET = "ait1" + "c1" * 20
OTHER_WALLET = "ait1" + "d4" * 20
GRANT = faucet_policy.DEFAULT_AUTO_APPROVE_MAX


@pytest.fixture
def session(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "coin_requests.db"))
    monkeypatch.setattr(agent_db, "_engine", None)
    monkeypatch.setattr(agent_db, "_SessionLocal", None)
    agent_db.init_db()
    with agent_db.get_db_session() as open_session:
        yield open_session
    agent_db._engine = None
    agent_db._SessionLocal = None


def _grant(session, request_id: str, sender: str, wallet: str, *, executed: bool = True) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    session.add(
        CoinRequest(
            id=request_id,
            sender=sender,
            recipient="hub-coordinator",
            amount=GRANT,
            wallet_address=wallet,
            status=CoinRequestStatus.APPROVED,
            approval_mode="automatic",
            approved_by="faucet-policy",
            created_at=now,
            expires_at=now + timedelta(days=1),
            transaction_hash="0x" + "2d" * 32 if executed else None,
        )
    )
    session.flush()


# --- The bypass that was used ------------------------------------------------------------


def test_renaming_the_sender_does_not_buy_a_second_grant(session) -> None:
    """The hub's own sequence, replayed. This is the finding."""
    _grant(session, "req-follower-1782118019", "follower", WALLET)

    status, reason = faucet_policy.decide(session, "follower-ait-reset", GRANT, WALLET)

    assert status == CoinRequestStatus.PENDING
    assert WALLET in reason


@pytest.mark.parametrize("respelled", ["0x" + "c1" * 20, "aitbc1" + "c1" * 20, "0x" + "C1" * 20])
def test_respelling_the_wallet_does_not_buy_a_second_grant(session, respelled: str) -> None:
    """Counting the destination is only worth anything if it sees through the spellings."""
    _grant(session, "req-1", "follower", WALLET)

    status, _ = faucet_policy.decide(session, "someone-else", GRANT, respelled)

    assert status == CoinRequestStatus.PENDING


@pytest.mark.parametrize("stored_as", ["0x" + "c1" * 20, "aitbc1" + "c1" * 20])
def test_the_prior_grant_is_found_however_it_was_stored(session, stored_as: str) -> None:
    """Rows predate the canonicalisation, so the stored side varies too."""
    _grant(session, "req-1", "follower", stored_as)

    status, _ = faucet_policy.decide(session, "someone-else", GRANT, WALLET)

    assert status == CoinRequestStatus.PENDING


# --- What must still work ----------------------------------------------------------------


def test_a_genuinely_new_agent_and_wallet_is_still_granted(session) -> None:
    """Widening the check must not stop the faucet doing its job."""
    _grant(session, "req-1", "follower", WALLET)

    status, _ = faucet_policy.decide(session, "brand-new-agent", GRANT, OTHER_WALLET)

    assert status == CoinRequestStatus.APPROVED


def test_the_first_grant_of_all_is_approved(session) -> None:
    status, _ = faucet_policy.decide(session, "follower", GRANT, WALLET)

    assert status == CoinRequestStatus.APPROVED


def test_the_same_agent_asking_for_a_different_wallet_is_still_stopped(session) -> None:
    """Why the sender clause stays: the destination check alone would allow this."""
    _grant(session, "req-1", "follower", WALLET)

    status, _ = faucet_policy.decide(session, "follower", GRANT, OTHER_WALLET)

    assert status == CoinRequestStatus.PENDING


def test_an_unexecuted_approval_still_counts(session) -> None:
    """A registered row waits for an operator to run `execute`; it is a grant regardless."""
    _grant(session, "req-1", "follower", WALLET, executed=False)

    status, _ = faucet_policy.decide(session, "renamed", GRANT, WALLET)

    assert status == CoinRequestStatus.PENDING


def test_a_pending_request_is_not_a_grant(session) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    session.add(
        CoinRequest(
            id="req-waiting",
            sender="follower",
            recipient="hub-coordinator",
            amount=GRANT,
            wallet_address=WALLET,
            status=CoinRequestStatus.PENDING,
            approval_mode="manual",
            created_at=now,
            expires_at=now + timedelta(days=1),
        )
    )
    session.flush()

    status, _ = faucet_policy.decide(session, "follower", GRANT, WALLET)

    assert status == CoinRequestStatus.APPROVED


def test_a_non_address_wallet_is_not_expanded(session) -> None:
    """Agent ids reach this field too; they must be matched as themselves, not widened."""
    assert faucet_policy.address_spellings("hub-coordinator") == ["hub-coordinator"]
    assert faucet_policy.address_spellings("ait1short") == ["ait1short"]


def test_two_different_wallets_do_not_collapse(session) -> None:
    assert not set(faucet_policy.address_spellings(WALLET)) & set(faucet_policy.address_spellings(OTHER_WALLET))
