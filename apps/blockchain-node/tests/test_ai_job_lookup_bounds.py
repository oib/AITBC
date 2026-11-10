"""#1625 pins: the AI job read paths no longer scan the full AI-job tx set —
/ai/job/{id} and the cancel fallback resolve the job by indexed predicates
(tx_hash or payload job_id), and /ai/stats aggregates in SQL."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from sqlmodel import Session, create_engine

from aitbc_chain.base_models import Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import ai_services


def _engine():
    engine = create_engine("sqlite:///:memory:")
    chain_metadata.create_all(engine)
    return engine


def _bind(monkeypatch: pytest.MonkeyPatch, engine) -> None:
    @contextmanager
    def scope(chain_id: str = ""):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr("aitbc_chain.rpc.ai_services.session_scope", scope)
    monkeypatch.setattr(
        "aitbc_chain.rpc.ai_services.metrics_registry", type("M", (), {"increment": staticmethod(lambda *a: None)})()
    )


def _seed(engine, rows: list[dict]) -> None:
    with Session(engine) as s:
        for i, row in enumerate(rows):
            s.add(
                Transaction(
                    chain_id="c",
                    tx_hash=row.get("tx_hash", f"0x{i:064x}"),
                    block_height=i,
                    sender=row.get("sender", "0x" + "aa" * 20),
                    recipient="ai_service",
                    payload=row.get("payload", {}),
                    type=row.get("type", "AI_JOB"),
                    status=row.get("status", "pending"),
                    nonce=i,
                )
            )
        s.commit()


def test_get_job_finds_tx_hash_identity(monkeypatch):
    """Mempool-submitted jobs carry no payload job_id — identity is tx_hash."""
    engine = _engine()
    _bind(monkeypatch, engine)
    _seed(engine, [{"tx_hash": "0xabc", "payload": {"job_type": "text", "payment": 1.0}}])
    out = ai_services.ai_get_job("0xabc")
    assert out["found"] is True and out["job"]["job_id"] == "0xabc"


def test_get_job_finds_payload_job_id(monkeypatch):
    engine = _engine()
    _bind(monkeypatch, engine)
    _seed(engine, [{"tx_hash": "0xdef", "payload": {"job_id": "legacy-1", "job_type": "text"}}])
    out = ai_services.ai_get_job("legacy-1")
    assert out["found"] is True and out["job"]["job_id"] == "legacy-1"


def test_get_job_tx_hash_does_not_match_a_payload_identified_job(monkeypatch):
    """A row whose payload carries job_id is identified by THAT, not its
    tx_hash — the SQL candidate set is a superset and Python stays the guard."""
    engine = _engine()
    _bind(monkeypatch, engine)
    _seed(engine, [{"tx_hash": "0x999", "payload": {"job_id": "other", "job_type": "text"}}])
    with pytest.raises(HTTPException) as exc:
        ai_services.ai_get_job("0x999")
    assert exc.value.status_code == 404


def test_get_job_ignores_non_ai_transactions(monkeypatch):
    engine = _engine()
    _bind(monkeypatch, engine)
    _seed(engine, [{"tx_hash": "0xtransfer", "type": "TRANSFER", "payload": {"job_id": "x"}}])
    with pytest.raises(HTTPException) as exc:
        ai_services.ai_get_job("x")
    assert exc.value.status_code == 404


def test_stats_aggregates_in_sql(monkeypatch):
    engine = _engine()
    _bind(monkeypatch, engine)
    _seed(
        engine,
        [
            {"tx_hash": "0xa", "payload": {"job_id": "j1", "job_type": "text", "payment": 2.0}, "status": "completed"},
            {"tx_hash": "0xb", "payload": {"job_id": "j2", "job_type": "image", "payment": 3.0}, "status": "completed"},
            {"tx_hash": "0xc", "payload": {"job_id": "j3", "job_type": "text"}, "status": "pending"},
            {"tx_hash": "0xd", "payload": {"job_type": "text"}, "status": "failed"},  # no job_id -> tx_hash identity
            {"tx_hash": "0xe", "type": "TRANSFER", "payload": {}},  # not an AI job
        ],
    )
    out = ai_services.ai_stats()
    assert out["total_jobs"] == 4
    assert out["status_breakdown"] == {"completed": 2, "pending": 1, "failed": 1}
    assert out["type_breakdown"] == {"text": 3, "image": 1}
    assert float(out["total_revenue"]) == pytest.approx(5.0)
    assert float(out["average_payment"]) == pytest.approx(2.5)


def test_stats_cancelled_overlay_moves_buckets(monkeypatch):
    """A cancelled completed job leaves the completed bucket AND the revenue."""
    engine = _engine()
    _bind(monkeypatch, engine)
    _seed(
        engine,
        [
            {"tx_hash": "0xa", "payload": {"job_id": "j1", "job_type": "text", "payment": 4.0}, "status": "completed"},
            {"tx_hash": "0xb", "payload": {"job_id": "j2", "job_type": "text", "payment": 1.0}, "status": "pending"},
        ],
    )
    with Session(engine) as s:
        s.add(ai_services.AIJobCancellation(job_id="j1", chain_id="c", tx_hash="0xa"))
        s.commit()
    out = ai_services.ai_stats()
    assert out["status_breakdown"] == {"cancelled": 1, "pending": 1}
    assert float(out["total_revenue"]) == pytest.approx(0.0)
