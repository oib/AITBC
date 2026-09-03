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

Two RPC handlers did the same thing from the other side, committing an Account row
directly rather than leaving it to consensus:

* rpc.accounts.faucet_request created and committed a zero-balance row even when
  block scoping meant the credit itself was only queued in the mempool. The row then
  blocked the very block that carried the credit, which froze all four validators on
  2026-09-03.
* rpc.accounts.create_account committed a zero-balance row unconditionally, with no
  transaction anywhere to reconcile it.

The tests below pin the invariants the fix relies on: a failing transaction
creates no accounts, a succeeding one creates the recipient itself so the
proposer does not have to, and neither RPC handler writes to the account table.
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


def test_faucet_state_transition_creates_recipient_account(session):
    """The block-time FAUCET path creates the recipient, so the RPC does not have to."""
    before = _addresses(session)
    assert RECIPIENT not in before

    tx = _tx("FAUCET", **{"from": "faucet", "value": 9_000, "fee": 0, "nonce": 0})
    with patch("aitbc_chain.state.state_transition.verify_transaction_signature", return_value=True):
        ok, msg = StateTransition().apply_transaction(session, CHAIN_ID, tx, "0x" + "ae" * 32)

    assert ok, msg
    assert _addresses(session) == before | {RECIPIENT}
    credited = session.get(Account, (CHAIN_ID, RECIPIENT))
    assert credited.balance == 9_000


def test_faucet_request_creates_no_account_row_when_block_scoped(session, monkeypatch):
    """A block-scoped faucet request must not commit an account row of its own.

    The credit is applied at block time, so a row committed here is a row the block
    headers do not account for: compute_state_root_full then disagrees with the parent
    header and the proposer refuses to build the very block that carries the credit.
    That deadlock froze all four validators on 2026-09-03.
    """
    import asyncio
    from contextlib import contextmanager

    from aitbc_chain import config as chain_config
    from aitbc_chain import mempool as mempool_module
    from aitbc_chain.rpc import accounts as accounts_rpc

    monkeypatch.setattr(chain_config.settings, "block_scoped_preregistered_transactions", True)
    monkeypatch.setattr(accounts_rpc, "get_chain_id", lambda _value=None: CHAIN_ID)

    @contextmanager
    def _scope(_chain_id):
        yield session

    monkeypatch.setattr(accounts_rpc, "session_scope", _scope)

    added: list[dict] = []

    class _Mempool:
        def add(self, tx, chain_id=None, tx_hash=None):
            added.append({"tx": tx, "chain_id": chain_id, "tx_hash": tx_hash})

    monkeypatch.setattr(mempool_module, "get_mempool", lambda: _Mempool())

    before = _addresses(session)
    result = asyncio.run(accounts_rpc.faucet_request(None, {"address": RECIPIENT, "amount": 1_000}))

    assert result["success"] is True
    session.flush()
    assert _addresses(session) == before

    assert len(added) == 1
    assert added[0]["tx"]["type"] == "FAUCET"
    assert added[0]["tx"]["to"] == result["address"]
    assert added[0]["tx"]["amount"] == 1_000
    assert added[0]["chain_id"] == CHAIN_ID
    assert added[0]["tx_hash"] == result["tx_hash"]


def test_register_account_creates_no_account_row(session, monkeypatch):
    """POST /rpc/register-account must not commit a row outside consensus.

    v0.25.5 removed this endpoint's internal callers because a row committed here is
    invisible to the block headers. The endpoint itself now reports rather than writes.
    """
    import asyncio
    from contextlib import contextmanager

    from aitbc_chain.rpc import accounts as accounts_rpc

    monkeypatch.setattr(accounts_rpc, "get_chain_id", lambda _value=None: CHAIN_ID)

    @contextmanager
    def _scope(_chain_id):
        yield session

    monkeypatch.setattr(accounts_rpc, "session_scope", _scope)

    before = _addresses(session)
    assert RECIPIENT not in before

    result = asyncio.run(accounts_rpc.create_account(None, {"address": RECIPIENT}))
    session.flush()

    assert _addresses(session) == before
    assert result["success"] is True
    assert result["created"] is False
    assert result["pending"] is True
    assert result["balance"] == 0

    # An address the chain already knows is reported, not re-created.
    existing = asyncio.run(accounts_rpc.create_account(None, {"address": SENDER}))
    session.flush()

    assert _addresses(session) == before
    assert existing["created"] is False
    assert existing["pending"] is False
    assert existing["balance"] == 1_000_000
