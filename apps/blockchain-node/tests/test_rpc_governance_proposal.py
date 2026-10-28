"""Read the sealed GOVERNANCE_PROPOSE record by proposal id (GAP-PROPOSAL-SHOW-1).

A v13 EXECUTE binds to the ``execution_payload`` its PROPOSE sealed in the
canonical transaction table. Until this endpoint the only way to see that
payload was a chain-DB read — an operator checking a payload before
submitting an EXECUTE had to know sqlite, and had to know which table.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlmodel import Session, create_engine

from aitbc_chain.metadata import chain_metadata

from aitbc_chain.base_models import Transaction

CHAIN_ID = "ait-test"
PROPOSAL_ID = "prop-17"
PROPOSE_HASH = "0x" + "ab" * 32
EXECUTE_HASH = "0x" + "cd" * 32


def _tx(tx_hash: str, tx_type: str, block_height: int, payload: dict) -> Transaction:
    return Transaction(
        chain_id=CHAIN_ID,
        tx_hash=tx_hash,
        block_height=block_height,
        sender="0xF5A930bBC90c15dB0bbf28f8485D18eEf24c3F43",
        recipient="0xF5A930bBC90c15dB0bbf28f8485D18eEf24c3F43",
        payload=payload,
        type=tx_type,
        value=0,
        fee=10,
        nonce=0,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )


@pytest.fixture
def wired(monkeypatch):
    """Wire a fresh in-memory chain and return the engine to seed."""
    engine = create_engine("sqlite://")
    chain_metadata.create_all(engine)

    from contextlib import contextmanager

    import aitbc_chain.rpc.transactions as transactions_module

    @contextmanager
    def _session_scope(*_args, **_kwargs):
        with Session(engine) as open_session:
            yield open_session

    from aitbc_chain.rpc import utils as rpc_utils

    monkeypatch.setattr(transactions_module, "session_scope", _session_scope)
    monkeypatch.setattr(rpc_utils.settings, "chain_id", CHAIN_ID)
    return transactions_module, engine


def _seed(engine, *txs: Transaction) -> None:
    with Session(engine) as session:
        for tx in txs:
            session.add(tx)
        session.commit()


async def _show(module, proposal_id: str, chain_id: str | None = CHAIN_ID):
    return await module.get_sealed_governance_proposal.__wrapped__(None, proposal_id, chain_id)


@pytest.mark.asyncio
async def test_sealed_propose_returns_execution_payload(wired) -> None:
    module, engine = wired
    _seed(
        engine,
        _tx(
            PROPOSE_HASH,
            "GOVERNANCE_PROPOSE",
            42,
            {
                "proposal_id": PROPOSAL_ID,
                "title": "raise block reward",
                "execution_payload": {"parameter": "block_reward", "value": "7"},
            },
        ),
    )

    result = await _show(module, PROPOSAL_ID)

    assert result["proposal_id"] == PROPOSAL_ID
    assert result["tx_hash"] == PROPOSE_HASH
    assert result["block_height"] == 42
    assert result["execution_payload"] == {"parameter": "block_reward", "value": "7"}
    assert result["executed"] is False
    assert result["execute_tx_hash"] is None


@pytest.mark.asyncio
async def test_execute_sealed_is_reported(wired) -> None:
    module, engine = wired
    _seed(
        engine,
        _tx(
            PROPOSE_HASH,
            "GOVERNANCE_PROPOSE",
            42,
            {"proposal_id": PROPOSAL_ID, "execution_payload": {"parameter": "p", "value": "v"}},
        ),
        _tx(EXECUTE_HASH, "GOVERNANCE_EXECUTE", 50, {"proposal_id": PROPOSAL_ID}),
    )

    result = await _show(module, PROPOSAL_ID)

    assert result["executed"] is True
    assert result["execute_tx_hash"] == EXECUTE_HASH
    assert result["execute_block_height"] == 50


@pytest.mark.asyncio
async def test_unknown_proposal_id_404s(wired) -> None:
    module, engine = wired
    _seed(
        engine,
        _tx(PROPOSE_HASH, "GOVERNANCE_PROPOSE", 42, {"proposal_id": "prop-other", "execution_payload": {}}),
    )

    with pytest.raises(HTTPException) as exc_info:
        await _show(module, "prop-missing")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_newest_propose_wins(wired) -> None:
    """A re-proposed id resolves to the newest sealed PROPOSE row."""
    module, engine = wired
    _seed(
        engine,
        _tx(PROPOSE_HASH, "GOVERNANCE_PROPOSE", 10, {"proposal_id": PROPOSAL_ID, "execution_payload": {"v": 1}}),
        _tx(
            "0x" + "ef" * 32,
            "GOVERNANCE_PROPOSE",
            20,
            {"proposal_id": PROPOSAL_ID, "execution_payload": {"v": 2}},
        ),
    )

    result = await _show(module, PROPOSAL_ID)

    assert result["block_height"] == 20
    assert result["execution_payload"] == {"v": 2}


@pytest.mark.asyncio
async def test_other_tx_types_do_not_match(wired) -> None:
    """A TRANSFER that happens to carry proposal_id must not resolve."""
    module, engine = wired
    _seed(
        engine,
        _tx(PROPOSE_HASH, "TRANSFER", 42, {"proposal_id": PROPOSAL_ID, "amount": 5}),
    )

    with pytest.raises(HTTPException) as exc_info:
        await _show(module, PROPOSAL_ID)
    assert exc_info.value.status_code == 404
