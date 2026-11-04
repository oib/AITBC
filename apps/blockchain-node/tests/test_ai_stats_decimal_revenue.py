"""Pin: the stats endpoint sums float wire payments into Decimal revenue (#1033).

Drives the REAL ``ai_stats()`` with seeded completed jobs carrying float
``payment`` payload fields — the regression the validator found: the
accumulator went Decimal while the boundary still added raw floats and
``Decimal + float`` raises TypeError. Reverting the boundary conversion
fails this test (verified as a mutation).
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from aitbc_chain.base_models import Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import ai_services
from sqlmodel import Session, create_engine


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
    # the stats route bumps a metric; keep it out of the loop
    monkeypatch.setattr(
        "aitbc_chain.rpc.ai_services.metrics_registry", type("M", (), {"increment": staticmethod(lambda *a: None)})()
    )


def _seed(engine, payments: list[float | None]) -> None:
    with Session(engine) as s:
        for i, pay in enumerate(payments):
            payload = {"job_id": f"j{i}", "job_type": "text", "prompt": "x"}
            if pay is not None:
                payload["payment"] = pay
            s.add(
                Transaction(
                    chain_id="c",
                    tx_hash=f"0x{i:064x}",
                    block_height=i,
                    sender="0x" + "aa" * 20,
                    recipient="ai_service",
                    payload=payload,
                    type="AI_JOB",
                    status="completed",
                    nonce=i,
                )
            )
        s.commit()


def test_float_payments_sum_to_decimal_revenue(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine()
    _bind(monkeypatch, engine)
    _seed(engine, [12.5, 0.25, None])
    out = ai_services.ai_stats()
    assert out["total_revenue"] == pytest.approx(12.75) or str(out["total_revenue"]) in ("12.75", "12.75000000000000000")
