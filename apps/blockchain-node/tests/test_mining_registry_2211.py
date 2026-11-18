"""#2211 — ``/rpc/mining/*`` consistency.

The mining endpoints used to keep state in ``start_mining_route.miners`` — a
function attribute, i.e. per-process memory — while the RPC runs ``--workers
N``. Writes landed on one worker's dict and reads hit whichever worker
answered; ``status``/``list`` additionally preferred the unrelated
coordinator-api ``/v1/miners`` AI-job registry, so the four endpoints could
never agree. State now lives in the chain.db ``miner_registry`` table
(SERVICE_STATE_TABLES — node-local bookkeeping, no PoW exists on this
PBFT/PoA chain), shared by every worker.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from aitbc_chain.base_models import MinerRegistry
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import router as rpc_router
from fastapi import HTTPException
from sqlmodel import Session, create_engine, select

ADMIN = "0x" + "ab" * 20
MINER = "0x" + "cd" * 20


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    chain_metadata.create_all(eng)
    return eng


@pytest.fixture()
def bound(engine, monkeypatch):
    """Point the routes' session_scope at the in-memory engine (shared store)."""

    @contextmanager
    def scope(chain_id: str = ""):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(rpc_router, "session_scope", scope)
    monkeypatch.setattr(rpc_router, "get_authenticated_address", lambda request, credentials=None: ADMIN)
    return engine


def _req() -> MagicMock:
    return MagicMock()


def _rows(engine) -> list[MinerRegistry]:
    with Session(engine) as session:
        return session.exec(select(MinerRegistry)).all()


def test_start_status_list_agree(bound):
    """The reported sequence: start → status/list must see the same miner."""
    out = rpc_router.start_mining_route(_req(), {"miner_address": MINER, "threads": 1})
    assert out["status"] == "started"
    assert out["simulated"] is True

    status = rpc_router.get_mining_status_route(_req())
    assert status["status"] == "mining"
    assert status["active_count"] == 1
    assert status["source"] == "chain.db"
    assert status["simulated"] is True
    assert status["miners"][0]["address"] == MINER
    assert status["miners"][0]["enabled"] is True

    listing = rpc_router.list_miners_route(_req())
    assert listing["count"] == 1
    assert listing["miners"][0]["address"] == MINER
    assert listing["source"] == "chain.db"


def test_stop_then_status_and_list_agree(bound):
    """stop must be visible to status AND list — the old dict kept showing enabled."""
    rpc_router.start_mining_route(_req(), {"miner_address": MINER, "threads": 2})
    out = rpc_router.stop_mining_route(_req())
    assert out["status"] == "stopped"

    status = rpc_router.get_mining_status_route(_req())
    assert status["status"] == "idle"
    assert status["active_count"] == 0
    assert status["miners"][0]["enabled"] is False
    assert status["miners"][0]["stopped_at"] is not None

    listing = rpc_router.list_miners_route(_req())
    assert listing["count"] == 1
    assert listing["miners"][0]["enabled"] is False


def test_state_survives_across_sessions(bound):
    """Cross-worker property: a *different* session (another worker process)
    sees the same rows — the store is chain.db, not process memory."""
    rpc_router.start_mining_route(_req(), {"miner_address": MINER, "threads": 3})
    # A fresh Session on the same engine stands in for a second uvicorn worker.
    with Session(bound) as session:
        row = session.exec(select(MinerRegistry).where(MinerRegistry.miner_address == MINER)).one()
        assert row.enabled is True
        assert row.threads == 3
        assert row.chain_id == "bc-2.test"  # conftest pins settings.chain_id


def test_restart_updates_single_row(bound):
    rpc_router.start_mining_route(_req(), {"miner_address": MINER, "threads": 1})
    rpc_router.stop_mining_route(_req())
    rpc_router.start_mining_route(_req(), {"miner_address": MINER, "threads": 8})
    rows = _rows(bound)
    assert len(rows) == 1
    assert rows[0].enabled is True
    assert rows[0].threads == 8
    assert rows[0].stopped_at is None


def test_other_chain_rows_not_visible(bound):
    """Registry is chain-scoped: rows for another chain must not leak in."""
    with Session(bound) as session:
        session.add(
            MinerRegistry(
                chain_id="other-chain",
                miner_address=MINER,
                threads=1,
                enabled=True,
                authorized_by=ADMIN,
                started_at=datetime.now(UTC),
            )
        )
        session.commit()
    status = rpc_router.get_mining_status_route(_req())
    assert status["status"] == "idle"
    assert status["miners"] == []


def test_empty_registry_is_idle(bound):
    status = rpc_router.get_mining_status_route(_req())
    assert status == {
        "status": "idle",
        "miners": [],
        "active_count": 0,
        "source": "chain.db",
        "simulated": True,
        "note": rpc_router._MINING_SIMULATED_NOTE,
    }
    listing = rpc_router.list_miners_route(_req())
    assert listing["count"] == 0
    assert listing["source"] == "chain.db"


def test_start_validates_input(bound):
    with pytest.raises(HTTPException) as exc:
        rpc_router.start_mining_route(_req(), {})
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        rpc_router.start_mining_route(_req(), {"miner_address": MINER, "threads": 0})
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        rpc_router.start_mining_route(_req(), {"miner_address": MINER, "threads": "many"})
    assert exc.value.status_code == 400
