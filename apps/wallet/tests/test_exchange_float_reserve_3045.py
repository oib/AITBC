"""Pins for AUDIT-EXCHANGE-FLOAT-RESERVE-1 (#3045).

A funded BUY order's prepaid ETH sits in the shared bridge float, but
``_pending_eth_reserve`` only summed withdrawals + sell releases + open
``exchange_settlements`` rows — backing-at-rest was invisible spendable
float, so other lanes could drain it and strand a later match in
``queued_reserve``.

The fix adds ``exchange_prepaid_float_liability()`` — read ``mode=ro``
from exchange.db like the settlement monitor's other reads — as a fourth
reserve term: ``Σ prepaid_deposits − Σ prepaid_debits.committed_eth``.
Deposits only leave the float via trade settlements; committed tracks
matched-not-refunded cost (settled = gone, in-flight = already covered by
the settlement-rows term), so deposits−committed is exactly the
uncommitted prepaid still claimable by users.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from wallet_app.bridge import bridge_withdraw_monitor as wdm
from wallet_app.bridge import exchange_settlement_monitor as esm
from wallet_app.bridge.bridge_db import init_db, insert_withdrawal

NODE_A = "0x" + "aa" * 20
NODE_B = "0x" + "bb" * 20

_EXCHANGE_SCHEMA = """
CREATE TABLE prepaid_deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_address TEXT NOT NULL,
    amount_eth TEXT NOT NULL,
    eth_tx_hash TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE prepaid_debits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_address TEXT NOT NULL,
    order_id INTEGER UNIQUE NOT NULL,
    amount_eth TEXT NOT NULL,
    committed_eth TEXT NOT NULL DEFAULT '0',
    state TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP
);
"""


def _exchange_db(tmp_path: Path) -> Path:
    db = tmp_path / "exchange.db"
    conn = sqlite3.connect(db)
    conn.executescript(_EXCHANGE_SCHEMA)
    conn.commit()
    conn.close()
    return db


def _deposit(conn: sqlite3.Connection, node: str, amount: str, tx: str) -> None:
    conn.execute(
        "INSERT INTO prepaid_deposits (node_address, amount_eth, eth_tx_hash) VALUES (?, ?, ?)",
        (node, amount, tx),
    )


def _debit(conn: sqlite3.Connection, node: str, order_id: int, amount: str, committed: str, state: str = "open") -> None:
    conn.execute(
        "INSERT INTO prepaid_debits (node_address, order_id, amount_eth, committed_eth, state) VALUES (?, ?, ?, ?, ?)",
        (node, order_id, amount, committed, state),
    )


@pytest.fixture
def exchange_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A real exchange.db on tmp_path wired through EXCHANGE_DATABASE_URL."""
    db = _exchange_db(tmp_path)
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{db}")
    return db


class TestPrepaidFloatLiability:
    def test_deposits_minus_committed_is_the_liability(self, exchange_env):
        """1.0 deposited, 0.8 open debit with 0.3 committed (matched trades —
        some settled/gone, some in-flight and already covered by the
        settlement-rows term): liability is the uncommitted 0.7 — spendable
        0.2 + order-reserved 0.5, exactly _prepaid_spendable + reserved."""
        conn = sqlite3.connect(exchange_env)
        _deposit(conn, NODE_A, "1.0", "0xdep1")
        _debit(conn, NODE_A, 1, "0.8", "0.3")
        conn.commit()
        conn.close()
        assert esm.exchange_prepaid_float_liability() == Decimal("0.7")

    def test_settled_committed_stays_subtracted(self, exchange_env):
        """A 'consumed' (closed) debit keeps committed_eth — settled trades
        paid out and must not come back into the reserve."""
        conn = sqlite3.connect(exchange_env)
        _deposit(conn, NODE_A, "1.0", "0xdep1")
        _debit(conn, NODE_A, 1, "0.8", "0.5", state="consumed")
        conn.commit()
        conn.close()
        assert esm.exchange_prepaid_float_liability() == Decimal("0.5")

    def test_trade_refund_releases_committed_back(self, exchange_env):
        """A refunded trade decrements committed_eth — that ETH is claimable
        again, so the liability rises."""
        conn = sqlite3.connect(exchange_env)
        _deposit(conn, NODE_A, "1.0", "0xdep1")
        _debit(conn, NODE_A, 1, "0.8", "0.3")  # was 0.5 before the refund
        conn.commit()
        conn.close()
        assert esm.exchange_prepaid_float_liability() == Decimal("0.7")

    def test_sums_across_nodes_and_floors_at_zero(self, exchange_env, tmp_path, monkeypatch):
        conn = sqlite3.connect(exchange_env)
        _deposit(conn, NODE_A, "1.0", "0xdep1")
        _deposit(conn, NODE_B, "0.4", "0xdep2")
        _debit(conn, NODE_A, 1, "0.8", "0.3")
        _debit(conn, NODE_B, 2, "0.4", "0.4", state="consumed")
        conn.commit()
        conn.close()
        # (1.0 + 0.4) - (0.3 + 0.4) = 0.7
        assert esm.exchange_prepaid_float_liability() == Decimal("0.7")

        # Defensive floor: committed above deposits can never reserve negative.
        conn = sqlite3.connect(exchange_env)
        conn.execute("DELETE FROM prepaid_deposits")
        conn.execute("DELETE FROM prepaid_debits")
        _deposit(conn, NODE_A, "0.1", "0xdep3")
        _debit(conn, NODE_A, 3, "0.1", "0.5", state="consumed")
        conn.commit()
        conn.close()
        assert esm.exchange_prepaid_float_liability() == Decimal("0")

    def test_missing_database_is_zero_liability(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{tmp_path}/absent/exchange.db")
        assert esm.exchange_prepaid_float_liability() == Decimal("0")

    def test_unreadable_database_fails_open(self, tmp_path, monkeypatch):
        bad = tmp_path / "exchange.db"
        bad.write_bytes(b"not a sqlite database" * 100)
        monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{bad}")
        assert esm.exchange_prepaid_float_liability() == Decimal("0")


class TestReserveIntegration:
    def test_pending_eth_reserve_counts_prepaid_backing(self, tmp_path, monkeypatch, exchange_env):
        """The headline failure: a pending withdrawal plus open BUY backing
        must both come out of the same available float."""
        bridge_db = tmp_path / "bridge_deposits.db"
        monkeypatch.setattr("wallet_app.bridge.bridge_db.DB_PATH", str(bridge_db))
        init_db()
        insert_withdrawal(
            ait_tx_hash="0x" + "11" * 32,
            from_address="0x" + "22" * 20,
            eth_address="0x" + "33" * 20,
            amount_ait=Decimal("10"),
            fee_ait=Decimal("0.05"),
            net_ait=Decimal("9.95"),
            amount_eth=Decimal("0.2"),
        )
        conn = sqlite3.connect(exchange_env)
        _deposit(conn, NODE_A, "1.0", "0xdep1")
        _debit(conn, NODE_A, 1, "0.8", "0.3")
        conn.commit()
        conn.close()

        reserve = wdm._pending_eth_reserve()
        assert reserve == Decimal("0.2") + Decimal("0.7")

    def test_reserve_survives_missing_exchange_db(self, tmp_path, monkeypatch):
        """No exchange.db on this node -> the term is zero, withdrawals still reserve."""
        monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{tmp_path}/absent/exchange.db")
        bridge_db = tmp_path / "bridge_deposits.db"
        monkeypatch.setattr("wallet_app.bridge.bridge_db.DB_PATH", str(bridge_db))
        init_db()
        insert_withdrawal(
            ait_tx_hash="0x" + "44" * 32,
            from_address="0x" + "55" * 20,
            eth_address="0x" + "66" * 20,
            amount_ait=Decimal("10"),
            fee_ait=Decimal("0.05"),
            net_ait=Decimal("9.95"),
            amount_eth=Decimal("0.2"),
        )
        assert wdm._pending_eth_reserve() == Decimal("0.2")
