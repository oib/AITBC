"""#2475: leaderboard must be O(1) statements and rank by the live composite.

Before the fix ``_leaderboard_entries`` ran ``calculate_composite_trust_score``
per row — ~6 SQL statements each — on an unauthenticated route allowing
``limit`` up to 500, and the page was pre-selected by the *stored*
``trust_score`` cache column, so a drifted cache could exclude the true live
leaders. The batched computation collapses this to a fixed ~2 statements and
the trust_score category now ranks the whole candidate set by the reported
live score.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session

from coordinator_api.contexts.reputation.domain.reputation import AgentReputation

BASE = "/v1/reputation"


def _seed(db_session: Session, agent_id: str, **overrides: object) -> AgentReputation:
    fields: dict[str, object] = {"agent_id": agent_id}
    fields.update(overrides)
    rep = AgentReputation(**fields)  # type: ignore[arg-type]
    db_session.add(rep)
    db_session.commit()
    return rep


def _count_statements(db_engine, client: TestClient, url: str) -> tuple[list, int]:
    """GET ``url`` while counting SQL statements on the test engine."""
    statements: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    event.listen(db_engine, "before_cursor_execute", _count)
    try:
        resp = client.get(url)
    finally:
        event.remove(db_engine, "before_cursor_execute", _count)
    return resp.json(), len(statements)


class TestLeaderboardQueryBudget:
    def test_statement_count_is_bounded_not_per_row(self, client: TestClient, db_session: Session, db_engine) -> None:
        """25 profiles must not cost ~150 statements; the batch is ~2."""
        for i in range(25):
            _seed(db_session, f"agent-{i:02d}", trust_score=500.0 + i)

        body, count = _count_statements(db_engine, client, f"{BASE}/leaderboard?limit=100")

        assert isinstance(body, list)
        # Profiles select + community-feedback select (+ negligible overhead).
        # The pre-fix per-row path measured ~6 statements per profile.
        assert count <= 10, f"leaderboard ran {count} statements for 25 profiles"

    def test_large_limit_stays_bounded(self, client: TestClient, db_session: Session, db_engine) -> None:
        for i in range(30):
            _seed(db_session, f"bulk-{i:02d}")

        body, count = _count_statements(db_engine, client, f"{BASE}/leaderboard?limit=500")

        assert len(body) == 30
        assert count <= 10


class TestLeaderboardLiveRanking:
    """The auditor's stale-page repro: stored cache order != live order."""

    def _seed_drifted_pair(self, db_session: Session) -> None:
        # stale-high: stored 900 but terrible components -> live composite low.
        _seed(
            db_session,
            "stale-high",
            trust_score=900.0,
            performance_rating=1.0,
            reliability_score=10.0,
            uptime_percentage=50.0,
            success_rate=10.0,
            average_response_time=9000.0,
            jobs_completed=1,
            jobs_failed=9,
            dispute_count=10,
            transaction_count=10,
            total_earnings=Decimal("0"),
            certifications=[],
        )
        # fresh-low: stored 100 but excellent components -> live composite high.
        _seed(
            db_session,
            "fresh-low",
            trust_score=100.0,
            performance_rating=5.0,
            reliability_score=100.0,
            uptime_percentage=100.0,
            success_rate=100.0,
            average_response_time=0.0,
            jobs_completed=100,
            jobs_failed=0,
            dispute_count=0,
            transaction_count=10,
            total_earnings=Decimal("100"),
            certifications=["cert-a", "cert-b"],
        )

    def test_limit_one_returns_the_live_leader(self, client: TestClient, db_session: Session) -> None:
        self._seed_drifted_pair(db_session)
        board = client.get(f"{BASE}/leaderboard?limit=1").json()
        assert len(board) == 1
        assert board[0]["agent_id"] == "fresh-low"

    def test_page_is_sorted_by_reported_score(self, client: TestClient, db_session: Session) -> None:
        self._seed_drifted_pair(db_session)
        board = client.get(f"{BASE}/leaderboard?limit=10").json()
        assert [e["agent_id"] for e in board] == ["fresh-low", "stale-high"]
        scores = [e["trust_score"] for e in board]
        assert scores == sorted(scores, reverse=True)
        # The reported values are the live composites, not the stored decoys.
        assert board[0]["trust_score"] > board[1]["trust_score"]

    def test_non_trust_category_keeps_stored_column_ordering(self, client: TestClient, db_session: Session) -> None:
        """category=total_earnings still pages by that column; trust_score stays live."""
        _seed(db_session, "poor", total_earnings=Decimal("1"), trust_score=800.0)
        _seed(db_session, "rich", total_earnings=Decimal("500"), trust_score=100.0)
        board = client.get(f"{BASE}/leaderboard?category=total_earnings&limit=10").json()
        assert [e["agent_id"] for e in board] == ["rich", "poor"]
