"""Regression tests for the proposer-side account-row leak.

The block header state_root is a full scan of the account table, so a
row that exists only on the proposer changes the header that proposer signs and
no other validator can reproduce it. That is the mechanism behind the block
1804 and 2846 state-root divergences.

Two paths used to create account rows and then abandon them:

* consensus.poa._propose_block created the recipient Account before
  calling apply_transaction. When apply_transaction returned False
  the loop did continue and the row stayed in the session, which was then
  committed with the rest of the block. It was also wrong for BRIDGE_LOCK,
  where the state transition deliberately creates no recipient account.
* state_transition.validate_transaction called _ensure_account for the
  LIQUIDITY_* types *before* the payload checks that return False.

The tests below pin the invariants the fix relies on: a failing transaction
creates no accounts, and a succeeding one creates the recipient itself so the
proposer does not have to.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc_chain.base_models import Account
from aitbc_chain.database import chain_metadata
from aitbc_chain.state.state_transition import StateTransition

CHAIN_ID = "ait-test"
SENDER = "0x1d8B34f249b96169E48E956b00c307898FbaF087"
RECIPIENT = "0x17B9ED0c216932F6457c491808FF4d28bcbb679d"


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    chain_metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN_ID, address=SENDER, balance=1_000_000, nonce=0))
        session.commit()
        yield session


def _addresses(session: Session) -> set[str]:
    return set(session.exec(select(Account.address).where(Account.chain_id == CHAIN_ID)).all())


def _tx(tx_type: str, **overrides) -> dict:
    tx = {
        "from": SENDER,
        "to": RECIPIENT,
        "value": 0,
        "fee": 1_000,
        "nonce": 0,
        "chain_id": CHAIN_ID,
        "type": tx_type,
        "signature": "0x" + "aa" * 65,
    }
    tx.update(overrides)
    return tx


def test_successful_transfer_creates_recipient_account(session):
    """The state transition creates the recipient itself; the proposer must not."""
    before = _addresses(session)
    assert RECIPIENT not in before

    tx = _tx("TRANSFER", value=5_000)
    with patch("aitbc_chain.state.state_transition.verify_transaction_signature", return_value=True):
        ok, msg = StateTransition().apply_transaction(session, CHAIN_ID, tx, "0x" + "ab" * 32)

    assert ok, msg
    assert _addresses(session) == before | {RECIPIENT}


def test_rejected_transaction_leaves_no_account_row(session):
    """A MESSAGE with a non-zero value is rejected and must not create the recipient."""
    before = _addresses(session)

    tx = _tx("MESSAGE", value=5_000)
    with patch("aitbc_chain.state.state_transition.verify_transaction_signature", return_value=True):
        ok, err = StateTransition().apply_transaction(session, CHAIN_ID, tx, "0x" + "ac" * 32)

    assert not ok
    assert "value=0" in err
    session.flush()
    assert _addresses(session) == before


@pytest.mark.parametrize(
    ("tx_type", "payload"),
    [
        ("LIQUIDITY_DEPOSIT", {}),
        ("LIQUIDITY_DEPOSIT", {"pool_id": "pool-a"}),
        ("LIQUIDITY_WITHDRAW", {}),
        ("LIQUIDITY_CLAIM", {}),
    ],
)
def test_invalid_liquidity_payload_leaves_no_account_row(session, tx_type, payload):
    """validate_transaction must reject a bad payload before it ensures accounts."""
    before = _addresses(session)

    tx = _tx(tx_type, value=5_000, payload=payload)
    with patch("aitbc_chain.state.state_transition.verify_transaction_signature", return_value=True):
        ok, err = StateTransition().validate_transaction(session, CHAIN_ID, tx, "0x" + "ad" * 32)

    assert not ok, err
    session.flush()
    assert _addresses(session) == before
