"""Tests for wallet bridge database helpers.

Covers:
- init_db creates the required tables (eth_deposits, price_history, eth_withdrawals)
- insert_withdrawal and round-trip lookup
- get_pending_withdrawals status filtering
- get_all_withdrawals pagination
- update_withdrawal_status for completed, refunded and failed flows
- deposit helpers remain usable on the shared bridge DB
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from wallet_app.bridge.bridge_db import (
    init_db,
    insert_deposit,
    insert_withdrawal,
    get_pending_withdrawals,
    get_all_withdrawals,
    get_withdrawal_by_ait_tx_hash,
    update_withdrawal_status,
    get_deposit_by_id,
    update_deposit_status,
)


@pytest.fixture
def bridge_db(tmp_path: Path):
    """A fresh bridge DB in a temporary directory."""
    db_path = tmp_path / "bridge.db"
    with patch("wallet_app.bridge.bridge_db.DB_PATH", str(db_path)):
        init_db()
        yield str(db_path)


class TestBridgeWithdrawalDb:
    """Round-trip tests for eth_withdrawals helpers."""

    def test_init_db_creates_withdrawal_table(self, bridge_db):
        """init_db must create eth_withdrawals with the expected columns."""
        import sqlite3

        conn = sqlite3.connect(bridge_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(eth_withdrawals)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        expected = {
            "id",
            "ait_tx_hash",
            "from_address",
            "eth_address",
            "amount_ait",
            "fee_ait",
            "net_ait",
            "amount_eth",
            "status",
            "eth_tx_hash",
            "refund_tx_hash",
            "error",
            "created_at",
            "released_at",
            "completed_at",
            "refunded_at",
        }
        assert expected.issubset(columns)

    def test_insert_and_lookup_withdrawal(self, bridge_db):
        withdrawal_id = insert_withdrawal(
            ait_tx_hash="0xa" * 64,
            from_address="0x1111111111111111111111111111111111111111",
            eth_address="0x2222222222222222222222222222222222222222",
            amount_ait=Decimal("1.0"),
            fee_ait=Decimal("0.005"),
            net_ait=Decimal("0.995"),
            amount_eth=Decimal("0.0001"),
        )

        assert withdrawal_id.startswith("withdrawal_")

        record = get_withdrawal_by_ait_tx_hash("0xa" * 64)
        assert record is not None
        assert record["from_address"] == "0x1111111111111111111111111111111111111111"
        assert record["eth_address"] == "0x2222222222222222222222222222222222222222"
        assert record["status"] == "pending"
        assert Decimal(str(record["amount_ait"])) == Decimal("1.0")

    def test_get_pending_withdrawals_filters_status(self, bridge_db):
        insert_withdrawal(
            ait_tx_hash="0xa" * 64,
            from_address="0x1111111111111111111111111111111111111111",
            eth_address="0x2222222222222222222222222222222222222222",
            amount_ait=Decimal("1.0"),
            fee_ait=Decimal("0.005"),
            net_ait=Decimal("0.995"),
            amount_eth=Decimal("0.0001"),
        )
        insert_withdrawal(
            ait_tx_hash="0xb" * 64,
            from_address="0x3333333333333333333333333333333333333333",
            eth_address="0x4444444444444444444444444444444444444444",
            amount_ait=Decimal("2.0"),
            fee_ait=Decimal("0.01"),
            net_ait=Decimal("1.99"),
            amount_eth=Decimal("0.0002"),
            status="completed",
        )
        insert_withdrawal(
            ait_tx_hash="0xc" * 64,
            from_address="0x5555555555555555555555555555555555555555",
            eth_address="0x6666666666666666666666666666666666666666",
            amount_ait=Decimal("3.0"),
            fee_ait=Decimal("0.015"),
            net_ait=Decimal("2.985"),
            amount_eth=Decimal("0.0003"),
            status="insufficient_reserve",
        )

        pending = get_pending_withdrawals()
        ait_hashes = {w["ait_tx_hash"] for w in pending}
        assert "0xa" * 64 in ait_hashes
        assert "0xc" * 64 in ait_hashes
        assert "0xb" * 64 not in ait_hashes

    def test_get_all_withdrawals_pagination(self, bridge_db):
        for i in range(3):
            insert_withdrawal(
                ait_tx_hash=f"0x{i:02d}" + "0" * 62,
                from_address="0x1111111111111111111111111111111111111111",
                eth_address="0x2222222222222222222222222222222222222222",
                amount_ait=Decimal("1.0"),
                fee_ait=Decimal("0.005"),
                net_ait=Decimal("0.995"),
                amount_eth=Decimal("0.0001"),
            )

        all_records = get_all_withdrawals(limit=2, offset=0)
        assert len(all_records) == 2

    def test_update_withdrawal_status_to_completed(self, bridge_db):
        insert_withdrawal(
            ait_tx_hash="0xa" * 64,
            from_address="0x1111111111111111111111111111111111111111",
            eth_address="0x2222222222222222222222222222222222222222",
            amount_ait=Decimal("1.0"),
            fee_ait=Decimal("0.005"),
            net_ait=Decimal("0.995"),
            amount_eth=Decimal("0.0001"),
        )

        ok = update_withdrawal_status(
            ait_tx_hash="0xa" * 64,
            status="completed",
            eth_tx_hash="0xeth" * 11,
        )
        assert ok

        record = get_withdrawal_by_ait_tx_hash("0xa" * 64)
        assert record["status"] == "completed"
        assert record["eth_tx_hash"] == "0xeth" * 11
        assert record["completed_at"] is not None

    def test_update_withdrawal_status_to_refunded(self, bridge_db):
        insert_withdrawal(
            ait_tx_hash="0xa" * 64,
            from_address="0x1111111111111111111111111111111111111111",
            eth_address="0x2222222222222222222222222222222222222222",
            amount_ait=Decimal("1.0"),
            fee_ait=Decimal("0.005"),
            net_ait=Decimal("0.995"),
            amount_eth=Decimal("0.0001"),
        )

        ok = update_withdrawal_status(
            ait_tx_hash="0xa" * 64,
            status="refunded",
            refund_tx_hash="0xrefund" * 9,
            error="release timed out",
        )
        assert ok

        record = get_withdrawal_by_ait_tx_hash("0xa" * 64)
        assert record["status"] == "refunded"
        assert record["refund_tx_hash"] == "0xrefund" * 9
        assert record["error"] == "release timed out"

    def test_update_withdrawal_status_failed(self, bridge_db):
        insert_withdrawal(
            ait_tx_hash="0xa" * 64,
            from_address="0x1111111111111111111111111111111111111111",
            eth_address="0x2222222222222222222222222222222222222222",
            amount_ait=Decimal("1.0"),
            fee_ait=Decimal("0.005"),
            net_ait=Decimal("0.995"),
            amount_eth=Decimal("0.0001"),
        )

        ok = update_withdrawal_status(
            ait_tx_hash="0xa" * 64,
            status="failed",
            error="insufficient reserve",
        )
        assert ok

        record = get_withdrawal_by_ait_tx_hash("0xa" * 64)
        assert record["status"] == "failed"
        assert record["error"] == "insufficient reserve"


class TestBridgeDepositDb:
    """Smoke tests for deposit helpers to ensure DB round-trip works."""

    def test_deposit_insert_and_status_update(self, bridge_db):
        deposit_id = insert_deposit(
            tx_hash="0xdeposit" * 5,
            from_address="0x9999999999999999999999999999999999999999",
            amount_eth=Decimal("0.01"),
            amount_ait=Decimal("100"),
            recipient="0x1111111111111111111111111111111111111111",
        )

        record = get_deposit_by_id(deposit_id)
        assert record is not None
        assert record["status"] == "pending"

        ok = update_deposit_status(deposit_id, "completed")
        assert ok

        record = get_deposit_by_id(deposit_id)
        assert record["status"] == "completed"
