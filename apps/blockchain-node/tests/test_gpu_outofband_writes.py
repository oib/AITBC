"""FORK-OOB-WRITERS-1 / issue #382 — ``gpu_resources`` routes must not write
committed tables outside a block.

``register_gpu`` and ``allocate_gpu`` used to insert (or update)
``GPURegistration``/``GPUAllocation`` rows inside ``session_scope`` — both
tables are in ``COMMITTED_TABLES`` at v14 *and* v15. The write landed only
on the node that served the RPC call, so two nodes with identical chains
but different call history diverged in the side-table fingerprint at the
next block. Worse than the escrow case: a shadow row also survives the seal
— ``handle_gpu_registration`` updates an existing row without rewriting
``registered_by``/``registered_at``, so the RPC-shadowed values persisted
even after the transaction landed.

The routes now submit the signed transaction envelope through market
admission (``POST /transactions/market``, same path as escrow's lock) and
write nothing. Unsigned legacy field bodies are refused with a 4xx.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aitbc.crypto.crypto import derive_ethereum_address
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.mempool import compute_tx_hash
import aitbc_chain.rpc.gpu_resources as gpu_routes
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state import side_root_shadow
from aitbc_chain.state.gpu_resources import GPUAllocation, GPURegistration
from aitbc_chain.state.state_transition import StateTransition
from fastapi import HTTPException
from sqlmodel import Session, create_engine, select

CHAIN = "gpu-oob-fixture"
BLOCK_VERSION = 14

REGISTRANT_KEY = "0x" + "55" * 32
REGISTRANT = derive_ethereum_address(REGISTRANT_KEY)
GPU_ID = "gpu_test_42"


def _engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    chain_metadata.create_all(engine)
    return engine


def _seed(engine) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=REGISTRANT, balance=10_000_000, nonce=0))
        session.commit()


def _fingerprint(engine) -> str:
    with Session(engine) as session:
        conn = session.connection().connection
        return side_root_shadow.committed_fingerprint(conn, BLOCK_VERSION)["fingerprint"]


def _register_request(tx: dict[str, Any] | None):
    """Duck-typed request: ``model_dump()`` feeds the new envelope contract;
    the legacy attrs let the unfixed handler take its row-write path, so the
    same test body exercises both trees."""
    return SimpleNamespace(
        model_dump=lambda: {"tx": tx},
        gpu_id=GPU_ID,
        miner_id="miner-test",
        model="RTX 4090",
        memory_gb=24,
        cuda_version="",
        region="",
        capabilities=[],
        price_per_hour="0.05",
        registered_by=REGISTRANT,
    )


def _allocate_request(tx: dict[str, Any] | None):
    return SimpleNamespace(
        model_dump=lambda: {"tx": tx},
        gpu_id=GPU_ID,
        client_id="client-1",
        duration_hours=2.0,
        total_cost="0.10",
        allocated_by=REGISTRANT,
    )


def _gpu_register_tx() -> dict[str, Any]:
    tx: dict[str, Any] = {
        "chain_id": CHAIN,
        "type": "GPU_REGISTER",
        "from": REGISTRANT,
        "to": "0x0000000000000000000000000000000000000000",
        "amount": 0,
        "value": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": 0,
        "payload": {
            "gpu_id": GPU_ID,
            "miner_id": "miner-test",
            "model": "RTX 4090",
            "memory_gb": 24,
            "price_per_hour": "0.05",
        },
    }
    tx["signature"] = sign_transaction_data(tx, REGISTRANT_KEY)
    tx["tx_hash"] = compute_tx_hash(tx)
    return tx


def _gpu_allocate_tx(allocation_id: str = "alloc_oobtest1", nonce: int = 1) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "chain_id": CHAIN,
        "type": "GPU_ALLOCATE",
        "from": REGISTRANT,
        "to": "0x0000000000000000000000000000000000000000",
        "amount": 0,
        "value": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": nonce,
        "payload": {
            "gpu_id": GPU_ID,
            "allocation_id": allocation_id,
            "client_id": "client-1",
            "duration_hours": 2.0,
            "total_cost": "0.10",
        },
    }
    tx["signature"] = sign_transaction_data(tx, REGISTRANT_KEY)
    tx["tx_hash"] = compute_tx_hash(tx)
    return tx


def _mock_submit(monkeypatch) -> AsyncMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"success": True, "transaction_hash": "0x" + "ab" * 32}
    post = AsyncMock(return_value=resp)
    monkeypatch.setattr("aitbc.network.SharedHttpClient.post", post)
    return post


def _bind_session_scope(monkeypatch, engine) -> None:
    """Point ``database.session_scope`` at the test engine — a no-op on the
    fixed route (it never opens a session) but lets the unfixed route take
    its real write path so the phantom row is what the test catches."""

    @contextmanager
    def scope(chain_id: str = ""):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr("aitbc_chain.database.session_scope", scope)


def _apply(engine, tx: dict[str, Any]) -> tuple[bool, str]:
    with Session(engine) as session:
        ok, err = StateTransition().apply_transaction(
            session, CHAIN, dict(tx), tx["tx_hash"], block_version=BLOCK_VERSION, block_height=2
        )
        if ok:
            session.commit()
        return ok, err


@pytest.mark.asyncio
async def test_register_writes_no_row_and_two_nodes_agree(monkeypatch):
    """Node A serves the register call; node B never sees it. The fixed
    route writes no ``gpu_registration`` row on A — after the same sealed
    tx applies on both, the committed fingerprints are equal. On the old
    route A's shadow row (RPC-time ``registered_at``, caller-supplied
    ``registered_by``) survives the seal and the fingerprints diverge."""
    post = _mock_submit(monkeypatch)
    engine_a, engine_b = _engine(), _engine()
    _seed(engine_a)
    _seed(engine_b)
    _bind_session_scope(monkeypatch, engine_a)

    tx = _gpu_register_tx()
    result = await gpu_routes.register_gpu(_register_request(tx), chain_id=CHAIN)

    assert result["status"] == "submitted"
    assert result["tx_hash"] == "0x" + "ab" * 32
    assert post.await_count == 1

    # No row on the serving node — the route did not touch session_scope.
    with Session(engine_a) as session:
        assert session.exec(select(GPURegistration)).all() == []
    assert _fingerprint(engine_a) == _fingerprint(engine_b)

    # Seal the identical transaction on both nodes.
    ok_a, _ = _apply(engine_a, tx)
    ok_b, _ = _apply(engine_b, tx)
    assert ok_a and ok_b
    assert _fingerprint(engine_a) == _fingerprint(engine_b)


@pytest.mark.asyncio
async def test_allocate_writes_no_row_and_register_then_allocate(monkeypatch):
    """Register seals first, then allocate: both tables stay in lockstep on
    the two nodes; the allocate route itself writes nothing."""
    _mock_submit(monkeypatch)
    engine_a, engine_b = _engine(), _engine()
    _seed(engine_a)
    _seed(engine_b)
    _bind_session_scope(monkeypatch, engine_a)

    reg_tx = _gpu_register_tx()
    assert _apply(engine_a, reg_tx)[0] and _apply(engine_b, reg_tx)[0]
    assert _fingerprint(engine_a) == _fingerprint(engine_b)

    alloc_tx = _gpu_allocate_tx()
    result = await gpu_routes.allocate_gpu(_allocate_request(alloc_tx), chain_id=CHAIN)
    assert result["status"] == "submitted"
    assert result["allocation_id"] == "alloc_oobtest1"

    with Session(engine_a) as session:
        assert session.exec(select(GPUAllocation)).all() == []

    ok_a, _ = _apply(engine_a, alloc_tx)
    ok_b, _ = _apply(engine_b, alloc_tx)
    assert ok_a and ok_b
    assert _fingerprint(engine_a) == _fingerprint(engine_b)


def test_allocate_before_register_rejected_onchain():
    """The apply path refuses an allocation for a GPU with no registration
    row — ordering the raw RPC route never enforced."""
    engine = _engine()
    _seed(engine)
    ok, err = _apply(engine, _gpu_allocate_tx(nonce=0))
    assert not ok
    assert "not found" in err.lower()


@pytest.mark.asyncio
async def test_unsigned_and_legacy_bodies_refused():
    """No ``tx`` → clear 400; wrong type / missing signature / missing
    sender → 400. Nothing is written, nothing is submitted."""
    with pytest.raises(HTTPException) as exc:
        await gpu_routes.register_gpu(_register_request(None))
    assert exc.value.status_code == 400 and "signed GPU_REGISTER" in exc.value.detail

    tx = _gpu_register_tx()
    tx["type"] = "GPU_ALLOCATE"
    with pytest.raises(HTTPException) as exc:
        await gpu_routes.register_gpu(_register_request(tx))
    assert exc.value.status_code == 400

    tx = _gpu_register_tx()
    tx["signature"] = ""
    with pytest.raises(HTTPException) as exc:
        await gpu_routes.register_gpu(_register_request(tx))
    assert exc.value.status_code == 400

    tx = _gpu_allocate_tx()
    del tx["payload"]["allocation_id"]
    with pytest.raises(HTTPException) as exc:
        await gpu_routes.allocate_gpu(_allocate_request(tx), chain_id=CHAIN)
    assert exc.value.status_code == 400 and "allocation_id" in exc.value.detail
