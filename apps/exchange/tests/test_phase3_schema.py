"""ETH-8 phase 3 schema coverage (commit C1) — prepaid ledger tables,
orders backing/payout columns, trades settlement mirror columns,
node_registry payout address, payout_address_audit.

All tests use throwaway DBs via EXCHANGE_DATABASE_URL; nothing touches a
real database and EXCHANGE_SETTLEMENT_ENABLED is never read here — schema
is inert either way.
"""

import sqlite3

import pytest

from apps.exchange.simple_exchange import db as exchange_db


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Point init_db at a throwaway path and return it."""
    db_path = str(tmp_path / "exchange.db")
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite://{db_path}")
    exchange_db.init_db()
    return db_path


def _cols(db_path, table):
    conn = sqlite3.connect(db_path)
    names = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    conn.close()
    return names


def test_fresh_init_creates_phase3_tables(fresh_db):
    conn = sqlite3.connect(fresh_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"prepaid_deposits", "prepaid_debits", "payout_address_audit"} <= tables


def test_fresh_orders_have_phase3_columns(fresh_db):
    cols = _cols(fresh_db, "orders")
    assert {"backing_tx_hash", "locked_ticks", "seller_eth_address", "funded_at"} <= cols


def test_fresh_trades_have_settlement_columns(fresh_db):
    cols = _cols(fresh_db, "trades")
    assert {
        "buy_order_id",
        "sell_order_id",
        "settlement_state",
        "settlement_eth_tx_hash",
        "settlement_ait_tx_hash",
        "settlement_fee_tx_hash",
    } <= cols


def test_fresh_registry_has_payout_columns(fresh_db):
    cols = _cols(fresh_db, "node_registry")
    assert {"eth_address", "eth_address_set_at"} <= cols


def _make_phase2_db(tmp_path, monkeypatch):
    """A DB shaped like phase 2 (no phase-3 columns/tables), with rows."""
    db_path = str(tmp_path / "exchange.db")
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite://{db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_type TEXT NOT NULL,
            amount TEXT NOT NULL, price TEXT NOT NULL, total TEXT NOT NULL,
            filled TEXT DEFAULT '0', remaining TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_address TEXT, tx_hash TEXT,
            amount_ticks INTEGER, price_ticks INTEGER,
            filled_ticks INTEGER DEFAULT 0, remaining_ticks INTEGER,
            signature TEXT, envelope_hash TEXT, account_nonce INTEGER,
            expiry_height INTEGER, funded_state TEXT DEFAULT 'unfunded',
            cancelled_at TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount TEXT NOT NULL, price TEXT NOT NULL, total TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            buyer_address TEXT, seller_address TEXT, fee_ait TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE node_registry (
            address TEXT PRIMARY KEY, label TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'seeded', registered_tx TEXT, registered_at TIMESTAMP
        )"""
    )
    conn.execute(
        "INSERT INTO orders (order_type, amount, price, total, remaining, user_address) "
        "VALUES ('BUY', '1', '0.0001', '0.0001', '1', '0xabc')"
    )
    conn.execute(
        "INSERT INTO trades (amount, price, total, buyer_address, seller_address) "
        "VALUES ('1', '0.0001', '0.0001', '0xaaa', '0xbbb')"
    )
    conn.execute("INSERT INTO node_registry (address, label, status) VALUES ('0xabc', 'node2', 'registered')")
    conn.commit()
    conn.close()
    return db_path


def test_migration_adds_columns_and_preserves_rows(tmp_path, monkeypatch):
    db_path = _make_phase2_db(tmp_path, monkeypatch)
    exchange_db.init_db()
    conn = sqlite3.connect(db_path)
    order = conn.execute(
        "SELECT user_address, funded_state, backing_tx_hash, locked_ticks, seller_eth_address FROM orders WHERE id = 1"
    ).fetchone()
    trade = conn.execute(
        "SELECT buyer_address, settlement_state, settlement_eth_tx_hash, buy_order_id FROM trades WHERE id = 1"
    ).fetchone()
    reg = conn.execute("SELECT address, eth_address FROM node_registry WHERE address = '0xabc'").fetchone()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    # Row data preserved; new columns default NULL / 'unfunded'.
    assert order[0] == "0xabc" and order[1] == "unfunded"
    assert order[2] is None and order[3] is None and order[4] is None
    assert trade[0] == "0xaaa" and trade[1] is None and trade[2] is None and trade[3] is None
    assert reg == ("0xabc", None)
    assert {"prepaid_deposits", "prepaid_debits", "payout_address_audit"} <= tables


def test_init_is_idempotent(fresh_db):
    exchange_db.init_db()
    exchange_db.init_db()  # second run must not raise or duplicate columns


def test_settlement_state_check_rejects_unknown(fresh_db):
    conn = sqlite3.connect(fresh_db)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO trades (amount, price, total, settlement_state) VALUES ('1', '1', '1', 'bogus')")
    conn.close()


def test_settlement_state_accepts_vocabulary(fresh_db):
    conn = sqlite3.connect(fresh_db)
    for state in ("locked", "releasing", "released", "settled", "refunded", "needs_review_sweep"):
        conn.execute("INSERT INTO trades (amount, price, total, settlement_state) VALUES ('1', '1', '1', ?)", (state,))
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    conn.close()
    assert count == 6


def test_prepaid_deposit_tx_hash_is_unique(fresh_db):
    conn = sqlite3.connect(fresh_db)
    conn.execute("INSERT INTO prepaid_deposits (node_address, amount_eth, eth_tx_hash) VALUES ('0xaaa', '0.5', '0xhash')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO prepaid_deposits (node_address, amount_eth, eth_tx_hash) VALUES ('0xbbb', '0.1', '0xhash')")
    conn.close()


def test_prepaid_debit_one_per_order(fresh_db):
    conn = sqlite3.connect(fresh_db)
    conn.execute("INSERT INTO prepaid_debits (node_address, order_id, amount_eth) VALUES ('0xaaa', 7, '0.2')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO prepaid_debits (node_address, order_id, amount_eth) VALUES ('0xaaa', 7, '0.2')")
    conn.close()


def test_prepaid_debit_state_check(fresh_db):
    conn = sqlite3.connect(fresh_db)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO prepaid_debits (node_address, order_id, amount_eth, state) VALUES ('0xaaa', 7, '0.2', 'lost')"
        )
    conn.close()


def test_locked_ticks_check(fresh_db):
    conn = sqlite3.connect(fresh_db)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO orders (order_type, amount, price, total, remaining, locked_ticks) "
            "VALUES ('SELL', '1', '1', '1', '1', -5)"
        )
    conn.close()


def test_payout_audit_writable(fresh_db):
    conn = sqlite3.connect(fresh_db)
    conn.execute(
        "INSERT INTO payout_address_audit (address, old_eth_address, new_eth_address, envelope_hash) "
        "VALUES ('0xabc', NULL, '0x1111111111111111111111111111111111111111', '0xenv')"
    )
    conn.execute(
        "INSERT INTO payout_address_audit (address, old_eth_address, new_eth_address, envelope_hash) "
        "VALUES ('0xabc', '0x1111111111111111111111111111111111111111', '0x2222222222222222222222222222222222222222', '0xenv2')"
    )
    conn.commit()
    rows = conn.execute("SELECT old_eth_address, new_eth_address FROM payout_address_audit ORDER BY id").fetchall()
    conn.close()
    assert rows[0] == (None, "0x1111111111111111111111111111111111111111")
    assert rows[1][0] == "0x1111111111111111111111111111111111111111"
