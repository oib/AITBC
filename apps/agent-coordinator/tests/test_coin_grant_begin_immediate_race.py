"""#v11 item 9: BEGIN IMMEDIATE claim atomicity under thread concurrency.

``_budgeted_claim_coin_request`` fuses the rolling-budget SUM reads, the
optional prior-grant probe and the claim INSERT into one BEGIN IMMEDIATE
transaction. These tests race real threads against a real SQLite file to
prove the check-and-claim cannot be split by a concurrent writer:

* N concurrent first-grant claims for the same wallet -> exactly one wins;
* M concurrent grants against a small hourly budget -> claimed total never
  exceeds the budget (the pre-fix two-transaction pair let both racers pass
  the same 'spent' read).
"""

from __future__ import annotations

import sqlite3
import threading


from agent_app.websocket import agent_stream


def _fresh_db(tmp_path) -> str:
    """An empty coin_requests ledger the production opener can converge."""
    db = tmp_path / "agent_conc.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE coin_requests (id TEXT, sender TEXT, recipient TEXT, amount INTEGER, "
        "wallet_address TEXT, status TEXT, approval_mode TEXT, approved_by TEXT, approved_at TEXT, "
        "created_at TEXT, expires_at TEXT, transaction_hash TEXT, audit_log TEXT)"
    )
    conn.commit()
    conn.close()
    return str(db)


def _race(fn, n: int) -> list:
    results: list = [None] * n
    barrier = threading.Barrier(n)

    def worker(i: int) -> None:
        barrier.wait(timeout=10)
        results[i] = fn(i)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def test_concurrent_first_grants_single_winner(tmp_path, monkeypatch):
    """8 threads race the same wallet's first grant: exactly one 'claimed',
    the rest 'prior_grant' — never two payouts for one wallet."""
    db = _fresh_db(tmp_path)
    monkeypatch.setenv("AGENT_DB_PATH", db)
    monkeypatch.delenv("HERMES_DB_PATH", raising=False)
    # Budgets are env AIT amounts; patch the unit-space readers directly.
    from agent_app.services import coin_request_policy as policy

    monkeypatch.setattr(policy, "auto_budget_per_hour", lambda: 1_000_000)
    monkeypatch.setattr(policy, "auto_budget_per_day", lambda: 1_000_000)

    wallet = "0x" + "cc" * 20

    def attempt(i: int):
        return agent_stream._budgeted_claim_coin_request(f"agent-{i}", 5, wallet, first_grant=True)

    outcomes = _race(attempt, 8)
    claimed = [o for o in outcomes if o[1] == "claimed"]
    prior = [o for o in outcomes if o[1] == "prior_grant"]
    unavailable = [o for o in outcomes if o[1] == "unavailable"]
    assert not unavailable, f"ledger unavailable under race: {unavailable}"
    assert len(claimed) == 1, f"expected exactly one winner, got {outcomes}"
    assert len(prior) == 7


def test_concurrent_grants_never_exceed_budget(tmp_path, monkeypatch):
    """6 threads x amount 5 against a 12-unit hourly budget: at most two
    claims commit (0->5->10 fit, the third would make 15 > 12)."""
    db = _fresh_db(tmp_path)
    monkeypatch.setenv("AGENT_DB_PATH", db)
    monkeypatch.delenv("HERMES_DB_PATH", raising=False)
    from agent_app.services import coin_request_policy as policy

    monkeypatch.setattr(policy, "auto_budget_per_hour", lambda: 12)
    monkeypatch.setattr(policy, "auto_budget_per_day", lambda: 1_000_000)

    def attempt(i: int):
        return agent_stream._budgeted_claim_coin_request(f"agent-{i}", 5, f"0x{i:040x}")

    outcomes = _race(attempt, 6)
    claimed = [o for o in outcomes if o[1] == "claimed"]
    budgeted = [o for o in outcomes if o[1] == "budget"]
    assert not [o for o in outcomes if o[1] == "unavailable"]
    assert len(claimed) == 2, f"budget overspent: {outcomes}"
    assert len(budgeted) == 4

    # And the ledger agrees: APPROVED automatic rows total exactly 10.
    conn = sqlite3.connect(db)
    try:
        total = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM coin_requests WHERE status='APPROVED' AND approval_mode='automatic'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert total == 10
