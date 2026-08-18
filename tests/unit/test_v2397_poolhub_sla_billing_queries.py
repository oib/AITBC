"""V23-97 — Pool Hub's SLA-violation and billing-usage queries never built.

Three call sites spelled the SQLAlchemy operator ``isnot_``.  There is no such
operator: a column offers ``is_``, ``is_not``, and the legacy alias ``isnot``.
The trailing underscore turned every one of those lines into an
``AttributeError`` raised while *constructing* the statement — before any
database was touched, so no query ever ran and no connection error was logged.

What that reached:

* ``GET /v1/sla/violations?resolved=true`` — 500, every time.
* ``POST /v1/sla/billing/sync`` — 500 for one miner and for all miners, which is
  the whole of Pool Hub's billing export.

The tests that covered these two services were deleted in ``ea97ba9aa``
("delete skipped integration tests"), leaving only stale ``__pycache__``
bytecode behind, which is why a typo in a query filter survived unnoticed.

These tests exercise the real service methods against a recording session, so
they fail on the construction of the statement exactly as production did.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from poolhub.models import MatchResult, SLAViolation
from poolhub.services.billing_integration import BillingIntegration
from poolhub.services.sla_collector import SLACollector

REPO_ROOT = Path(__file__).resolve().parents[2]


class _StubResult:
    """Answers the three shapes these services ask a Result for."""

    def __init__(self, rows: list[Any] | None = None, scalar_value: Any = None) -> None:
        self._rows = list(rows or [])
        self._scalar = scalar_value

    def scalars(self) -> _StubResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalar(self) -> Any:
        return self._scalar

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


class _Transaction:
    async def __aenter__(self) -> _Transaction:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class RecordingSession:
    """AsyncSession stand-in that keeps every statement it is handed.

    The point is that a statement has to be *built* before it can be recorded:
    with ``isnot_`` these methods raised before reaching ``execute`` at all.
    """

    def __init__(self, results: list[_StubResult] | None = None) -> None:
        self.statements: list[Any] = []
        self._results = list(results or [])

    async def execute(self, stmt: Any) -> _StubResult:
        self.statements.append(stmt)
        return self._results.pop(0) if self._results else _StubResult()

    def begin(self) -> _Transaction:
        return _Transaction()


def _sql(stmt: Any) -> str:
    return " ".join(str(stmt).split())


def _python_sources() -> list[Path]:
    skip = {"__pycache__", "node_modules", ".venv", "venv", "site-packages", ".git"}
    files: list[Path] = []
    for top in ("apps", "aitbc", "cli"):
        for path in (REPO_ROOT / top).rglob("*.py"):
            if not skip.intersection(path.parts):
                files.append(path)
    return files


# --- the root cause, stated once ------------------------------------------------


def test_isnot_underscore_is_not_a_column_operator() -> None:
    """The spelling that was used does not exist; the two that do are named here."""
    assert not hasattr(SLAViolation.resolved_at, "isnot_")
    assert hasattr(SLAViolation.resolved_at, "is_not")
    assert not hasattr(MatchResult.eta_ms, "isnot_")
    assert hasattr(MatchResult.eta_ms, "is_not")


def test_no_call_site_still_uses_the_nonexistent_operator() -> None:
    """A repo-wide sweep: ``.isnot_(`` cannot run anywhere, so it must not appear."""
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{n}"
        for path in _python_sources()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if ".isnot_(" in line
    ]
    assert offenders == [], f"`.isnot_(` raises AttributeError at statement build time: {offenders}"


# --- SLA violations -------------------------------------------------------------


async def test_resolved_violations_can_be_queried_at_all() -> None:
    """``resolved=True`` is the branch that used ``isnot_``; it raised before executing."""
    session = RecordingSession([_StubResult(rows=[])])

    violations = await SLACollector(session).get_sla_violations(resolved=True)

    assert violations == []
    assert "resolved_at IS NOT NULL" in _sql(session.statements[0])


async def test_unresolved_violations_still_filter_on_null() -> None:
    """The working branch keeps working: unresolved means resolved_at IS NULL."""
    session = RecordingSession([_StubResult(rows=[])])

    await SLACollector(session).get_sla_violations(resolved=False)

    sql = _sql(session.statements[0])
    assert "resolved_at IS NULL" in sql
    assert "IS NOT NULL" not in sql


async def test_a_resolved_query_can_also_be_narrowed_to_one_miner() -> None:
    """Both filters compose — the miner predicate is not lost on the resolved path."""
    session = RecordingSession([_StubResult(rows=[])])

    await SLACollector(session).get_sla_violations(miner_id="miner-1", resolved=True)

    sql = _sql(session.statements[0])
    assert "resolved_at IS NOT NULL" in sql
    assert "miner_id =" in sql


# --- billing sync ---------------------------------------------------------------


async def test_collecting_one_miners_usage_builds_its_query() -> None:
    """``sync_miner_usage`` -> ``_collect_miner_usage`` raised on the eta_ms filter."""
    session = RecordingSession([_StubResult(scalar_value=0), _StubResult(rows=[])])
    start = dt.datetime(2026, 8, 17, tzinfo=dt.UTC)

    usage = await BillingIntegration(session)._collect_miner_usage("miner-1", start, start + dt.timedelta(hours=1))

    assert set(usage) == {"gpu_hours", "api_calls", "compute_hours"}
    assert "eta_ms IS NOT NULL" in _sql(session.statements[1])


async def test_syncing_all_miners_usage_builds_its_query() -> None:
    """The batched path raised inside its transaction, so the whole sync 500'd."""
    session = RecordingSession(
        [
            _StubResult(rows=[SimpleNamespace(miner_id="miner-1")]),
            _StubResult(scalar_value=0),
            _StubResult(rows=[]),
        ]
    )

    result = await BillingIntegration(session).sync_all_miners_usage(hours_back=1)

    assert result["miners_processed"] == 1
    assert result["miners_failed"] == 0
    assert "eta_ms IS NOT NULL" in _sql(session.statements[2])


async def test_a_sync_with_no_miners_never_reaches_the_usage_query() -> None:
    """Guards the early return, so the query assertions above are about real work."""
    session = RecordingSession([_StubResult(rows=[])])

    result = await BillingIntegration(session).sync_all_miners_usage(hours_back=1)

    assert result["miners_processed"] == 0
    assert len(session.statements) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
