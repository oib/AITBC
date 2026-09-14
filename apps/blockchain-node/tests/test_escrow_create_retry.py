"""A failed ESCROW_LOCK submission must not leave residue that blocks a retry.

Regression coverage for the create-ordering wart: ``escrow/create`` used to
create the in-memory contract and the ``status="created"`` DB row *before*
broadcasting the lock transaction. A failed submit stranded both, and the
orphaned contract made a same-job_id retry die on "Invalid contract inputs"
even though no funds ever reached the chain.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlmodel import Session

import aitbc_chain.rpc.escrow_routes as escrow_routes
from aitbc_chain.contracts.escrow import EscrowManager, EscrowState
from aitbc_chain.models import Account, Escrow
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils import ait_to_units

# Deterministic, valid 0x addresses (same set as test_escrow_lock.py).
BUYER = "0xe8b0db006F34bf5b5d2B22553C017431E8e86e4F"
PROVIDER = "0xD4d85501E6cD447972Db19370307F1E3B1510016"
NODE_WALLET = "0xADC923a0928B8415E666206D3703a870C1d578CE"

JOB_ID = "job-orphan"
CHAIN_ID = "test-chain"


@pytest.fixture
def mgr() -> EscrowManager:
    return EscrowManager()


@pytest.fixture
def patched(monkeypatch, engine, mgr) -> EscrowManager:
    """Point the route at a fresh manager and the in-memory chain DB, with no lock on-chain."""
    monkeypatch.setattr(escrow_routes, "_NODE_WALLET", NODE_WALLET)
    monkeypatch.setattr(escrow_routes, "_CHAIN_ID", CHAIN_ID)
    monkeypatch.setattr(escrow_routes, "get_escrow_manager", lambda: mgr)
    monkeypatch.setattr(escrow_routes, "_find_existing_lock", AsyncMock(return_value=None))

    @contextmanager
    def scope(chain_id: str = ""):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(escrow_routes, "session_scope", scope)
    return mgr


def _lock_body() -> dict:
    """A create request carrying a fully-formed signed ESCROW_LOCK transaction."""
    lock_tx, _ = escrow_routes._build_lock_tx(JOB_ID, BUYER, PROVIDER, Decimal("1.0"), nonce=0)
    lock_tx["signature"] = "0xdeadbeef"
    return {
        "job_id": JOB_ID,
        "buyer": BUYER,
        "provider": PROVIDER,
        "amount": "1.0",
        "lock_tx": lock_tx,
    }


async def test_failed_lock_submit_leaves_no_orphan_and_retry_succeeds(patched, engine, monkeypatch):
    """First submit fails: no contract, no row; the same-job_id retry must succeed."""
    mgr = patched
    submit = AsyncMock(
        side_effect=[HTTPException(status_code=400, detail="submission failed"), "0xlockhash"],
    )
    monkeypatch.setattr(escrow_routes, "_submit_lock_tx", submit)

    with pytest.raises(HTTPException) as exc_info:
        await escrow_routes.create_escrow(_lock_body())
    assert exc_info.value.status_code == 400

    # Nothing may be left behind to block the retry: no in-memory contract
    # holding the job_id and no "created" Escrow row.
    assert not any(c.job_id == JOB_ID for c in mgr.escrow_contracts.values())
    with Session(engine) as session:
        assert session.get(Escrow, JOB_ID) is None

    result = await escrow_routes.create_escrow(_lock_body())

    assert result["success"] is True
    assert result["job_id"] == JOB_ID
    assert result["lock_tx_hash"] == "0xlockhash"
    assert submit.await_count == 2
    contract = next(c for c in mgr.escrow_contracts.values() if c.job_id == JOB_ID)
    assert contract.state is EscrowState.FUNDED
    with Session(engine) as session:
        row = session.get(Escrow, JOB_ID)
        assert row is not None
        assert row.status == "locked"
        assert row.lock_tx_hash == "0xlockhash"
        assert row.amount == ait_to_units(Decimal("1.0"))


async def test_retry_clears_residue_left_by_a_failed_create(patched, engine, monkeypatch):
    """A contract/row carrying a job_id with no on-chain lock is submit-failure residue.

    The pre-fix ordering could strand exactly this state, and ``load_from_db``
    revives it on every restart, so the create path must drop it rather than
    let it reject the retry as a duplicate.
    """
    mgr = patched
    monkeypatch.setattr(escrow_routes, "_submit_lock_tx", AsyncMock(return_value="0xlockhash"))

    # Seed the residue: an in-memory contract and a status="created" row while
    # no ESCROW_LOCK for the job exists on-chain.
    ok, _, stale_cid = await mgr.create_contract(
        job_id=JOB_ID,
        client_address=BUYER,
        agent_address=PROVIDER,
        amount=Decimal("1.0"),
    )
    assert ok
    with Session(engine) as session:
        for addr in (BUYER, PROVIDER):
            session.add(Account(chain_id=CHAIN_ID, address=canonical_address(addr), balance=0, nonce=0))
        session.add(
            Escrow(
                job_id=JOB_ID,
                chain_id=CHAIN_ID,
                buyer=canonical_address(BUYER),
                provider=canonical_address(PROVIDER),
                amount=ait_to_units(Decimal("1.0")),
                status="created",
                lock_tx_hash=None,
            )
        )
        session.commit()

    result = await escrow_routes.create_escrow(_lock_body())

    assert result["success"] is True
    assert result["lock_tx_hash"] == "0xlockhash"
    contracts = [c for c in mgr.escrow_contracts.values() if c.job_id == JOB_ID]
    assert len(contracts) == 1
    assert contracts[0].contract_id != stale_cid
    assert contracts[0].state is EscrowState.FUNDED
    with Session(engine) as session:
        row = session.get(Escrow, JOB_ID)
        assert row is not None
        assert row.status == "locked"
        assert row.lock_tx_hash == "0xlockhash"
