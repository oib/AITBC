"""Pytest configuration for exchange service tests.

The exchange service runs via ``apps.exchange.simple_exchange.server``.
Tests import from ``apps.exchange.simple_exchange.*`` modules.
"""

# The repo root is on `pythonpath` in pyproject.toml, which is what makes
# `apps.exchange.simple_exchange.*` importable. Nothing is inserted here on purpose.
#
# This file used to do `sys.path.insert(0, parents[2])`, and `parents[2]` is `apps/`, not the
# repo root. Putting `apps/` on sys.path changes how pytest derives module names for every
# other suite: `apps.agent-coordinator.tests.conftest` becomes `agent-coordinator.tests
# .conftest`. A conftest already imported under the first name is then imported *again* under
# the second, so two module objects exist for one file — and a fixture that patches a class
# attribute in one copy is invisible to a test reading it from the other. That is what made
# the agent-coordinator coin-request tests fail in a full run while passing alone (V23-69).

import sqlite3

import pytest


@pytest.fixture
def exchange_db(tmp_path, monkeypatch):
    """Point the exchange handlers + operation ledger at a temp database."""
    db_path = str(tmp_path / "exchange.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_type TEXT NOT NULL CHECK(order_type IN ('BUY', 'SELL')),
            amount TEXT NOT NULL,
            price TEXT NOT NULL,
            total TEXT NOT NULL,
            filled TEXT DEFAULT '0',
            remaining TEXT NOT NULL,
            status TEXT DEFAULT 'open' CHECK(status IN ('open', 'filled', 'cancelled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_address TEXT,
            tx_hash TEXT,
            amount_ticks INTEGER,
            price_ticks INTEGER,
            filled_ticks INTEGER DEFAULT 0,
            remaining_ticks INTEGER
        );
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount TEXT NOT NULL,
            price TEXT NOT NULL,
            total TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("EXCHANGE_API_KEY", "test-key")
    # get_db_path() resolves EXCHANGE_DATABASE_URL at call time, so env works
    # even where a previous suite popped and re-imported the handler modules
    # (test_http_contract does exactly that — setattr would patch a stale copy).
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{db_path}")
    # The ledger singleton caches per path — drop any stale entry.
    from apps.exchange.simple_exchange.handlers import base

    base._operation_ledgers.pop(db_path, None)
    return db_path
