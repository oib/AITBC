"""Aggregate budget on automatic coin grants — the Sybil bound (V23 faucet review).

`has_prior_grant` counts a (sender, wallet) pair once, but both fields are strings the
caller writes: a fresh pair is a fresh identity, and each fresh pair used to collect the
auto-approve ceiling. The rolling hourly/daily budgets cap what the faucet pays out in a
window regardless of how many names a caller mints — past the cap the request parks at
manual review instead of being approved.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent_app.services import coin_request_policy
from aitbc.db import agent_db
from aitbc.models import CoinRequest, CoinRequestStatus

WALLET = "0xe0383C465aF763F2489B61Ec169bB06E485DAB95"
OTHER_WALLET = "0x335de516468598827245e10094A9c014F4894a02"
GRANT = coin_request_policy.DEFAULT_AUTO_APPROVE_MAX


@pytest.fixture
def session(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "coin_requests.db"))
    monkeypatch.setattr(agent_db, "_engine", None)
    monkeypatch.setattr(agent_db, "_SessionLocal", None)
    agent_db.init_db()
    with agent_db.get_db_session() as open_session:
        yield open_session
    agent_db._engine = None
    agent_db._SessionLocal = None


def _grant(session, request_id: str, wallet: str, *, when: datetime | None = None, amount: int = GRANT) -> None:
    """Record an auto-approved request as if it were created at `when`."""
    stamp = when or datetime.now(UTC).replace(tzinfo=None)
    session.add(
        CoinRequest(
            id=request_id,
            sender=f"sender-{request_id}",
            recipient="hub-coordinator",
            amount=amount,
            wallet_address=wallet,
            status=CoinRequestStatus.APPROVED,
            approval_mode="automatic",
            approved_by="coin-request-policy",
            created_at=stamp,
            expires_at=stamp + timedelta(hours=24),
        )
    )
    session.commit()


def _wallet(n: int) -> str:
    return f"0x{n:040x}"


class TestAutoGrantBudget:
    def test_under_budget_approves(self, session):
        status, reason = coin_request_policy.decide(session, "sender-a", GRANT, WALLET)
        assert status is CoinRequestStatus.APPROVED

    def test_hourly_budget_trips_to_pending(self, session, monkeypatch):
        """The window sum + the new amount over the cap -> manual review."""
        monkeypatch.setenv("COIN_REQUEST_AUTO_BUDGET_PER_HOUR", str(GRANT * 2))
        _grant(session, "r1", _wallet(1))
        _grant(session, "r2", _wallet(2))
        status, reason = coin_request_policy.decide(session, "sender-b", GRANT, _wallet(3))
        assert status is CoinRequestStatus.PENDING
        assert "hourly" in reason

    def test_old_grants_do_not_count(self, session, monkeypatch):
        """Grants older than the window free the budget again."""
        monkeypatch.setenv("COIN_REQUEST_AUTO_BUDGET_PER_HOUR", str(GRANT))
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
        _grant(session, "old-1", _wallet(1), when=old)
        status, _ = coin_request_policy.decide(session, "sender-c", GRANT, _wallet(2))
        assert status is CoinRequestStatus.APPROVED

    def test_daily_budget_trips_when_hourly_has_room(self, session, monkeypatch):
        monkeypatch.setenv("COIN_REQUEST_AUTO_BUDGET_PER_HOUR", str(GRANT * 100))
        monkeypatch.setenv("COIN_REQUEST_AUTO_BUDGET_PER_DAY", str(GRANT * 2))
        _grant(session, "r1", _wallet(1))
        _grant(session, "r2", _wallet(2))
        status, reason = coin_request_policy.decide(session, "sender-d", GRANT, _wallet(3))
        assert status is CoinRequestStatus.PENDING
        assert "daily" in reason

    def test_zero_budget_disables_automatic(self, session, monkeypatch):
        monkeypatch.setenv("COIN_REQUEST_AUTO_BUDGET_PER_HOUR", "0")
        status, _ = coin_request_policy.decide(session, "sender-e", GRANT, _wallet(1))
        assert status is CoinRequestStatus.PENDING

    def test_manual_approvals_do_not_spend_auto_budget(self, session, monkeypatch):
        """Operator-approved grants are outside the automatic budget."""
        monkeypatch.setenv("COIN_REQUEST_AUTO_BUDGET_PER_HOUR", str(GRANT * 2))
        _grant(session, "manual-1", _wallet(1))
        row = session.query(CoinRequest).filter(CoinRequest.id == "manual-1").one()
        row.approval_mode = "manual"
        session.commit()
        _grant(session, "auto-1", _wallet(2))
        status, _ = coin_request_policy.decide(session, "sender-f", GRANT, _wallet(3))
        assert status is CoinRequestStatus.APPROVED

    def test_budget_trip_increments_the_alert_metric(self, session, monkeypatch):
        """Alerting watches `coin_request_auto_budget_trips_total` — prove it moves."""
        from agent_app.monitoring.prometheus_metrics import metrics_registry

        monkeypatch.setenv("COIN_REQUEST_AUTO_BUDGET_PER_HOUR", str(GRANT * 2))
        _grant(session, "r1", _wallet(1))
        _grant(session, "r2", _wallet(2))
        trips = metrics_registry.counter("coin_request_auto_budget_trips_total", "", ["window"])
        before = trips.get_value(window="hourly")
        coin_request_policy.decide(session, "sender-x", GRANT, _wallet(3))
        assert trips.get_value(window="hourly") == before + 1

    def test_prior_grant_check_still_wins_on_reason(self, session, monkeypatch):
        """A repeat identity gets the specific reason, not the generic budget one."""
        monkeypatch.setenv("COIN_REQUEST_AUTO_BUDGET_PER_HOUR", str(GRANT))
        _grant(session, "r1", WALLET)
        status, reason = coin_request_policy.decide(session, "sender-g", GRANT, WALLET)
        assert status is CoinRequestStatus.PENDING
        assert "already been granted" in reason
