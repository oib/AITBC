"""#2774: GET /contracts list_contracts was an unbounded .all() on a public
endpoint. Now a bounded page (limit ≤500, offset ≤500) with a true total.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc_chain.base_models import SmartContract
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import contract_service as cs_mod


@pytest.fixture
def engine(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as s:
        for i in range(1200):
            s.add(
                SmartContract(
                    chain_id="",
                    address=f"0x{i:040x}",
                    name=f"c{i}",
                    deployer="0x" + "00" * 20,
                    bytecode="",
                    abi={},
                    state={},
                    status="deployed",
                    deployed_at=base + timedelta(seconds=i),
                )
            )
        s.add(
            SmartContract(
                chain_id="",
                address="0xdead",
                name="destroyed",
                deployer="0x" + "00" * 20,
                bytecode="",
                abi={},
                state={},
                status="destroyed",
            )
        )
        s.commit()

    @contextmanager
    def _scope(chain_id: str = "", **kwargs):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(cs_mod, "session_scope", _scope)
    return engine


def test_default_page_is_bounded(engine):
    result = cs_mod.contract_service.list_contracts()
    assert result["total"] == 1200
    assert len(result["contracts"]) == 100
    assert result["limit"] == 100 and result["offset"] == 0


def test_limit_capped_at_500(engine):
    result = cs_mod.contract_service.list_contracts(limit=10_000)
    assert len(result["contracts"]) == 500
    assert result["limit"] == 500


def test_offset_pagination(engine):
    page1 = cs_mod.contract_service.list_contracts(limit=100, offset=0)
    page2 = cs_mod.contract_service.list_contracts(limit=100, offset=100)
    assert len(page1["contracts"]) == 100 and len(page2["contracts"]) == 100
    addrs1 = {c["address"] for c in page1["contracts"]}
    addrs2 = {c["address"] for c in page2["contracts"]}
    assert not addrs1 & addrs2
    # newest first: page1 holds the highest deployed_at
    assert max(c["deployed_at"] for c in page1["contracts"]) >= max(c["deployed_at"] for c in page2["contracts"])


def test_negative_and_huge_offset_clamped(engine):
    result = cs_mod.contract_service.list_contracts(limit=5, offset=-3)
    assert result["offset"] == 0
    assert len(result["contracts"]) == 5
    result = cs_mod.contract_service.list_contracts(limit=5, offset=999_999)
    assert result["offset"] == 100_000
    assert result["contracts"] == []
    # offset cap must not strand the tail: last page is reachable
    tail = cs_mod.contract_service.list_contracts(limit=500, offset=1000)
    assert len(tail["contracts"]) == 200


def test_destroyed_contracts_excluded(engine):
    result = cs_mod.contract_service.list_contracts(limit=5000)
    assert all(c["status"] == "deployed" for c in result["contracts"])
    assert "0xdead" not in {c["address"] for c in result["contracts"]}


def test_rpc_wrapper_passes_pagination():
    from aitbc_chain.rpc.contracts import list_contracts

    class _Svc:
        @staticmethod
        def list_contracts(**kwargs):
            return kwargs

    import aitbc_chain.rpc.contracts as cmod

    orig = cmod.contract_service
    cmod.contract_service = _Svc()
    try:
        assert list_contracts(Mock(), limit=7, offset=9) == {"limit": 7, "offset": 9}
    finally:
        cmod.contract_service = orig
