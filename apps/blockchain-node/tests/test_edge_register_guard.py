"""EDGE-REG-CONSENSUS-1/#361 interim guard.

``POST /rpc/edge/register`` writes ``edge_node_registration`` — inside the
committed table set below v15, so a served call diverges that node's
committed fingerprint at the next block (the 21 Oct stall at 118). The
route now refuses while the table is committed for the version the *next*
block will carry, and lifts itself once the v15 pin activates
(``committed_tables_for_version`` drops the table at >= 15) — no second
deploy.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import gpu_resources as gpu_routes
from aitbc_chain.state.gpu_resources import EdgeNodeRegistration
from fastapi import HTTPException
from sqlmodel import Session, create_engine, select

CHAIN = "edge-guard-fixture"


def _engine():
    engine = create_engine("sqlite:///:memory:")
    chain_metadata.create_all(engine)
    return engine


def _bind_session_scope(monkeypatch, engine) -> None:
    @contextmanager
    def scope(chain_id: str = ""):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr("aitbc_chain.database.session_scope", scope)


def _pin_next_version(monkeypatch, version: int) -> None:
    """The guard asks which version the *next* block will carry — the same
    question mempool admission asks. Pinned here instead of env thresholds."""
    monkeypatch.setattr(
        "aitbc_chain.state.state_transition.get_block_version_for_height",
        lambda height: version,
    )


def _request() -> gpu_routes.EdgeNodeRegistrationRequest:
    return gpu_routes.EdgeNodeRegistrationRequest(
        node_id="edge-1",
        endpoint="https://edge.invalid",
        region="eu-west",
        gpu_count=1,
        total_vram=24,
        capabilities=["inference"],
        registered_by="0x" + "aa" * 20,
    )


def _rows(engine) -> list[EdgeNodeRegistration]:
    with Session(engine) as session:
        return session.exec(select(EdgeNodeRegistration)).all()


@pytest.mark.asyncio
async def test_register_refused_while_table_committed(monkeypatch):
    """v14-era chain: the table is committed → 4xx, and nothing is written
    on the node that served the call."""
    engine = _engine()
    _bind_session_scope(monkeypatch, engine)
    _pin_next_version(monkeypatch, 14)

    with pytest.raises(HTTPException) as exc:
        gpu_routes.register_edge_node(_request(), chain_id=CHAIN)

    assert exc.value.status_code == 400
    assert "edge_node_registration" in exc.value.detail
    assert "#361" in exc.value.detail
    assert _rows(engine) == []


@pytest.mark.asyncio
async def test_register_allowed_once_v15_committed_set(monkeypatch):
    """Self-lifting: once the next block would seal at >= v15 the table is
    out of the committed set and the same route writes again — this is the
    path wave Y restores without a second deploy."""
    engine = _engine()
    _bind_session_scope(monkeypatch, engine)
    _pin_next_version(monkeypatch, 15)

    result = gpu_routes.register_edge_node(_request(), chain_id=CHAIN)

    assert result["status"] == "registered"
    rows = _rows(engine)
    assert len(rows) == 1 and rows[0].node_id == "edge-1"


def _seed(engine, node_id: str, chain_id: str = CHAIN, **over) -> None:
    with Session(engine) as session:
        session.add(
            EdgeNodeRegistration(
                chain_id=chain_id,
                node_id=node_id,
                endpoint="https://edge.invalid",
                region="eu-west",
                gpu_count=1,
                total_vram=24,
                capabilities=["inference"],
                registered_by="0x" + "aa" * 20,
                **over,
            )
        )
        session.commit()


def _table_snapshot(engine) -> list[tuple]:
    with Session(engine) as session:
        return sorted(
            (r.chain_id, r.node_id, r.status, r.registered_by) for r in session.exec(select(EdgeNodeRegistration)).all()
        )


@pytest.mark.asyncio
async def test_list_nodes_returns_count_and_rows(monkeypatch):
    """GET /edge/nodes exists so wave-Y B4 can count committed rows through
    the RPC — no sqlite3, no list-less /edge/info guessing."""
    engine = _engine()
    _bind_session_scope(monkeypatch, engine)
    _seed(engine, "edge-1")
    _seed(engine, "edge-2", status="deactivated")

    result = gpu_routes.list_edge_nodes(chain_id=CHAIN)

    assert result["chain_id"] == CHAIN
    assert result["count"] == 2
    by_id = {n["node_id"]: n for n in result["nodes"]}
    assert by_id["edge-1"]["status"] == "active"
    assert by_id["edge-2"]["status"] == "deactivated"
    assert by_id["edge-1"]["registered_by"] == "0x" + "aa" * 20
    assert set(by_id["edge-1"]) == {
        "node_id",
        "endpoint",
        "region",
        "gpu_count",
        "total_vram",
        "capabilities",
        "registered_by",
        "status",
        "registered_at",
    }


@pytest.mark.asyncio
async def test_list_nodes_empty_table_returns_zero(monkeypatch):
    engine = _engine()
    _bind_session_scope(monkeypatch, engine)

    result = gpu_routes.list_edge_nodes(chain_id=CHAIN)

    assert result == {"chain_id": CHAIN, "count": 0, "nodes": []}


@pytest.mark.asyncio
async def test_list_nodes_filters_by_chain(monkeypatch):
    engine = _engine()
    _bind_session_scope(monkeypatch, engine)
    _seed(engine, "edge-other", chain_id="other-chain")

    result = gpu_routes.list_edge_nodes(chain_id=CHAIN)

    assert result["count"] == 0 and result["nodes"] == []


@pytest.mark.asyncio
async def test_list_nodes_writes_nothing(monkeypatch):
    """The route is the B4 read path: it must leave the committed table
    byte-identical — called twice, snapshot compared."""
    engine = _engine()
    _bind_session_scope(monkeypatch, engine)
    _seed(engine, "edge-1")
    before = _table_snapshot(engine)

    gpu_routes.list_edge_nodes(chain_id=CHAIN)
    gpu_routes.list_edge_nodes(chain_id=CHAIN)

    assert _table_snapshot(engine) == before
