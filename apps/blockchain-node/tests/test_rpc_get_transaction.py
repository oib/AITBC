"""Asking the chain whether it holds a transaction (V23-66).

The chain could describe its transactions in bulk but could not answer "do you have this one",
so nothing outside it could check a hash it had recorded. That matters for any record kept
beside the chain rather than in it: the coin-request database stores a `transaction_hash`
against every executed request, and the hub's chain reset on 2026-08-15 left those pointing at
transactions that no longer exist, with no way to find out.

The 404 is the part with a consumer. `aitbc coin-requests reopen` clears a request's hash so it
can be paid again, and it decides whether to allow that from this endpoint's answer — so a 404
for a transaction that *is* present would reissue a payout that was already made.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from aitbc_chain.base_models import Transaction

CHAIN_ID = "ait-test"
TX_HASH = "0x" + "2d" * 32


@pytest.fixture
def chain(monkeypatch):
    """A one-transaction chain, wired in place of the node's real session."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Transaction(
                chain_id=CHAIN_ID,
                tx_hash=TX_HASH,
                block_height=6,
                sender="ait1" + "fe" * 20,
                recipient="ait1" + "c1" * 20,
                payload={"amount": 100},
                type="TRANSFER",
                value=100,
                fee=10,
                nonce=0,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        session.commit()

    from contextlib import contextmanager

    import aitbc_chain.rpc.transactions as transactions_module

    @contextmanager
    def _session_scope(*_args, **_kwargs):
        with Session(engine) as open_session:
            yield open_session

    monkeypatch.setattr(transactions_module, "session_scope", _session_scope)
    monkeypatch.setattr(transactions_module, "get_chain_id", lambda _requested: CHAIN_ID)
    return transactions_module


async def _get(module, tx_hash: str):
    return await module.get_transaction.__wrapped__(None, tx_hash, CHAIN_ID)


async def test_a_transaction_the_chain_holds_is_returned(chain) -> None:
    result = await _get(chain, TX_HASH)

    assert result["tx_hash"] == TX_HASH
    assert result["block_height"] == 6
    assert result["value"] == 100
    assert result["recipient"] == "ait1" + "c1" * 20


async def test_a_transaction_the_chain_does_not_hold_is_a_404(chain) -> None:
    """What `reopen` reads as "this payout is not on the chain"."""
    with pytest.raises(HTTPException) as raised:
        await _get(chain, "0x" + "ab" * 32)

    assert raised.value.status_code == 404
    assert "not found" in raised.value.detail


async def test_the_lookup_is_scoped_to_the_chain(chain, monkeypatch) -> None:
    """A hash from another island must not read as present on this one."""
    monkeypatch.setattr(chain, "get_chain_id", lambda _requested: "ait-other")

    with pytest.raises(HTTPException) as raised:
        await _get(chain, TX_HASH)

    assert raised.value.status_code == 404
