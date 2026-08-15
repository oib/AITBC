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

    from aitbc_chain.rpc import utils as rpc_utils

    monkeypatch.setattr(transactions_module, "session_scope", _session_scope)
    # Deliberately not monkeypatching `get_chain_id`. Stubbing it as `lambda _requested: ...`
    # swallows the argument, which is how the omitted-parameter defect below reached the hub
    # and 404'd every hash on the chain. Configure the node instead and let the real
    # resolution run.
    monkeypatch.setattr(rpc_utils.settings, "chain_id", CHAIN_ID)
    return transactions_module


async def _get(module, tx_hash: str, chain_id: str | None = CHAIN_ID):
    return await module.get_transaction.__wrapped__(None, tx_hash, chain_id)


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


async def test_the_lookup_is_scoped_to_the_chain(chain) -> None:
    """A hash from another island must not read as present on this one."""
    with pytest.raises(HTTPException) as raised:
        await _get(chain, TX_HASH, chain_id="ait-other")

    assert raised.value.status_code == 404


@pytest.mark.parametrize("omitted", [None, ""])
async def test_an_omitted_chain_id_means_this_node_s_own_chain(chain, omitted) -> None:
    """The defect that reached the hub, in one test.

    `get_chain_id` falls back to the configured chain for None only; an empty string comes
    back as an empty string, and `chain_id == ""` matches nothing. Callers that omitted the
    parameter — the documented default, and what `coin-requests reconcile` did — got a 404
    for every hash on the chain. That reads as "no payout was ever made", which is the exact
    state that invites reopening requests that were paid perfectly well.
    """
    result = await _get(chain, TX_HASH, chain_id=omitted)

    assert result["chain_id"] == CHAIN_ID
