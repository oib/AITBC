"""#1918 BRIDGE-WRITEPATH-CAS-1 pins — expected_statuses CAS on the
status writers that lacked it.

update_withdrawal_status / update_sell_lock_status /
update_exchange_settlement used to run unconditional
``UPDATE ... WHERE key=?``: a stale monitor pass or admin command could
flip a row another writer had already moved. Each writer now takes
``expected_statuses`` (same shape as #1796's update_deposit_status): the
UPDATE only lands while the row still sits in one of those statuses, and
a lost CAS returns False leaving the row untouched. These pins FAIL on
the unfixed code (the wrong-status write lands).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest


@pytest.fixture
def bridge_db(tmp_path: Path, monkeypatch):
    """A fresh bridge DB in a temporary directory."""
    from wallet_app.bridge import bridge_db as db

    db_path = tmp_path / "bridge.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()
    return db


class TestWithdrawalStatusCas:
    def test_cas_loss_returns_false_and_keeps_row(self, bridge_db):
        bridge_db.insert_withdrawal(
            ait_tx_hash="0xw1",
            from_address="0xfrom",
            eth_address="0x" + "e" * 40,
            amount_ait=Decimal("10"),
            fee_ait=Decimal("0.1"),
            net_ait=Decimal("9.9"),
            amount_eth=Decimal("0.5"),
            status="releasing",
        )
        # Row sits at 'releasing' — a 'completed' write predicated on
        # 'pending' must lose and leave the row untouched.
        assert bridge_db.update_withdrawal_status("0xw1", "completed", expected_statuses={"pending"}) is False
        row = bridge_db.get_withdrawal_by_ait_tx_hash("0xw1")
        assert row["status"] == "releasing"
        assert row["completed_at"] is None
        # The observed status wins — timestamped 'completed' variant.
        assert bridge_db.update_withdrawal_status("0xw1", "completed", expected_statuses={"releasing"}) is True
        row = bridge_db.get_withdrawal_by_ait_tx_hash("0xw1")
        assert row["status"] == "completed"
        assert row["completed_at"] is not None

    def test_cas_loss_on_plain_status_variant(self, bridge_db):
        bridge_db.insert_withdrawal(
            ait_tx_hash="0xw2",
            from_address="0xfrom",
            eth_address="0x" + "e" * 40,
            amount_ait=Decimal("10"),
            fee_ait=Decimal("0.1"),
            net_ait=Decimal("9.9"),
            amount_eth=Decimal("0.5"),
            status="pending",
        )
        assert bridge_db.update_withdrawal_status("0xw2", "failed", error="x", expected_statuses={"completed"}) is False
        assert bridge_db.get_withdrawal_by_ait_tx_hash("0xw2")["status"] == "pending"
        assert bridge_db.update_withdrawal_status("0xw2", "failed", error="x", expected_statuses={"pending"}) is True
        assert bridge_db.get_withdrawal_by_ait_tx_hash("0xw2")["status"] == "failed"


class TestSellLockStatusCas:
    def _lock(self, bridge_db, tx: str, status: str) -> None:
        bridge_db.insert_sell_lock(
            ait_tx_hash=tx,
            shop_ait_address="0x" + "a" * 40,
            amount_ait=Decimal("5"),
            status=status,
        )

    def test_timestamp_variant_cas(self, bridge_db):
        self._lock(bridge_db, "0xs1", "releasing")
        # 'released' is the timestamp_field variant — CAS must guard it too.
        assert bridge_db.update_sell_lock_status("0xs1", "released", expected_statuses={"settling"}) is False
        row = bridge_db.get_sell_lock_by_ait_tx_hash("0xs1")
        assert row["status"] == "releasing"
        assert bridge_db.update_sell_lock_status("0xs1", "released", expected_statuses={"releasing"}) is True
        assert bridge_db.get_sell_lock_by_ait_tx_hash("0xs1")["status"] == "released"

    def test_plain_variant_cas(self, bridge_db):
        self._lock(bridge_db, "0xs2", "locked")
        assert (
            bridge_db.update_sell_lock_status("0xs2", "queued_reserve", error="cap", expected_statuses={"orphaned"}) is False
        )
        assert bridge_db.get_sell_lock_by_ait_tx_hash("0xs2")["status"] == "locked"
        assert bridge_db.update_sell_lock_status("0xs2", "queued_reserve", error="cap", expected_statuses={"locked"}) is True
        assert bridge_db.get_sell_lock_by_ait_tx_hash("0xs2")["status"] == "queued_reserve"


class TestExchangeSettlementStatusCas:
    def _settlement(self, bridge_db, ref_id: int) -> str:
        sid = bridge_db.insert_exchange_settlement("trade", ref_id, amount_ait=Decimal("5"))
        assert sid is not None
        return sid

    def test_timestamp_variant_cas(self, bridge_db):
        sid = self._settlement(bridge_db, 1)
        # 'released' is the timestamp_field variant.
        assert bridge_db.update_exchange_settlement(sid, "released", expected_statuses={"settled"}) is False
        row = bridge_db.get_exchange_settlement("trade", 1)
        assert row["status"] == "locked"
        assert bridge_db.update_exchange_settlement(sid, "released", expected_statuses={"locked"}) is True
        assert bridge_db.get_exchange_settlement("trade", 1)["status"] == "released"

    def test_plain_variant_cas(self, bridge_db):
        sid = self._settlement(bridge_db, 2)
        assert bridge_db.update_exchange_settlement(sid, "needs_review", error="x", expected_statuses={"refunded"}) is False
        assert bridge_db.get_exchange_settlement("trade", 2)["status"] == "locked"
        assert bridge_db.update_exchange_settlement(sid, "needs_review", error="x", expected_statuses={"locked"}) is True
        assert bridge_db.get_exchange_settlement("trade", 2)["status"] == "needs_review"
