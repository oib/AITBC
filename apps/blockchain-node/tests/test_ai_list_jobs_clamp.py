"""#1057 pin: ai_list_jobs no longer scans the whole table on every call."""

from __future__ import annotations

from contextlib import contextmanager

from aitbc_chain.base_models import Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import ai_services
from sqlmodel import Session, create_engine


def _engine():
    engine = create_engine("sqlite:///:memory:")
    chain_metadata.create_all(engine)
    return engine


def _bind(monkeypatch, engine) -> None:
    @contextmanager
    def scope(chain_id: str = ""):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr("aitbc_chain.rpc.ai_services.session_scope", scope)


def _seed(engine, n: int) -> None:
    with Session(engine) as s:
        for i in range(n):
            s.add(
                Transaction(
                    chain_id="c",
                    tx_hash=f"0x{i:064x}",
                    block_height=i,
                    sender="0x" + "aa" * 20,
                    recipient="ai_service",
                    payload={"job_id": f"j{i}", "job_type": "text", "prompt": "x", "payment": 1.0},
                    type="AI_JOB",
                    status="pending",
                    nonce=i,
                )
            )
        s.commit()


def test_default_limit_clamps_results(monkeypatch):
    engine = _engine()
    _bind(monkeypatch, engine)
    _seed(engine, 30)
    out = ai_services.ai_list_jobs(limit=10)
    assert len(out["jobs"]) == 10 and out["limit"] == 10


def test_limit_capped_at_500_and_offset_paginates(monkeypatch):
    engine = _engine()
    _bind(monkeypatch, engine)
    _seed(engine, 40)
    out = ai_services.ai_list_jobs(limit=9999, offset=30)
    assert out["limit"] == 500 and len(out["jobs"]) == 10
    assert out["offset"] == 30


def test_negative_limit_clamped_up(monkeypatch):
    engine = _engine()
    _bind(monkeypatch, engine)
    _seed(engine, 5)
    out = ai_services.ai_list_jobs(limit=-50)
    assert out["limit"] == 1 and len(out["jobs"]) == 1
