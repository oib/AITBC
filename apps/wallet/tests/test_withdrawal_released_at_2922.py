"""#2922 pins: update_withdrawal_status must stamp released_at only on
release-intent transitions.

released_at is the release-age grace clock (_release_intent_age_seconds)
and the committed-since window anchor — every non-terminal bookkeeping
write ('failed', 'needs_review', 'awaiting_depth', 'orphaned', 'pending')
used to refresh it, resetting the grace clock and dragging rows into the
committed window at the wrong time. The sell-lock lane already stamps only
on ('releasing', 'released'); withdrawals now match.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest


@pytest.fixture
def bridge_db(tmp_path: Path, monkeypatch):
    """A fresh bridge DB in a temporary directory with a settable clock."""
    from wallet_app.bridge import bridge_db as db
    from wallet_app.bridge import bridge_db_withdrawals as wdb

    db_path = tmp_path / "bridge.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    clock = {"now": "2026-01-01T00:00:00+00:00"}
    monkeypatch.setattr(wdb, "utc_now_iso", lambda: clock["now"])
    db.init_db()
    db._clock = clock  # type: ignore[attr-defined]
    return db


def _insert(bridge_db, tx: str, status: str = "pending") -> None:
    bridge_db.insert_withdrawal(
        ait_tx_hash=tx,
        from_address="0xfrom",
        eth_address="0x" + "e" * 40,
        amount_ait=Decimal("10"),
        fee_ait=Decimal("0.1"),
        net_ait=Decimal("9.9"),
        amount_eth=Decimal("0.5"),
        status=status,
    )


def _released_at(bridge_db, tx: str):
    return bridge_db.get_withdrawal_by_ait_tx_hash(tx)["released_at"]


class TestReleasedAtOnlyOnReleaseIntent:
    def test_failed_write_does_not_stamp_released_at(self, bridge_db):
        """A 'failed' verdict is not a release — the column must stay NULL
        so the row never enters the committed-since window."""
        _insert(bridge_db, "0xw-fail")
        assert bridge_db.update_withdrawal_status("0xw-fail", "failed", error="boom") is True
        assert _released_at(bridge_db, "0xw-fail") is None

    def test_bookkeeping_writes_do_not_refresh_released_at(self, bridge_db):
        """releasing stamps the intent time once; later non-terminal writes
        ('needs_review', 'awaiting_depth', 'orphaned', 'pending') must not
        move the grace clock."""
        _insert(bridge_db, "0xw-intent")
        bridge_db._clock["now"] = "2026-01-01T00:00:00+00:00"  # type: ignore[attr-defined]
        assert bridge_db.update_withdrawal_status("0xw-intent", "releasing", release_nonce=7) is True
        intent_at = _released_at(bridge_db, "0xw-intent")
        assert intent_at == "2026-01-01T00:00:00+00:00"

        for status in ("needs_review", "awaiting_depth", "orphaned", "pending"):
            bridge_db._clock["now"] = "2026-01-02T00:00:00+00:00"  # type: ignore[attr-defined]
            assert bridge_db.update_withdrawal_status("0xw-intent", status, error="") is True
            assert _released_at(bridge_db, "0xw-intent") == intent_at, status

    def test_releasing_retry_restamps_intent(self, bridge_db):
        """A fresh release intent is a NEW broadcast — released_at moves to
        the retry's persist time."""
        _insert(bridge_db, "0xw-retry")
        assert bridge_db.update_withdrawal_status("0xw-retry", "releasing") is True
        first = _released_at(bridge_db, "0xw-retry")
        assert first == "2026-01-01T00:00:00+00:00"
        bridge_db._clock["now"] = "2026-01-03T00:00:00+00:00"  # type: ignore[attr-defined]
        assert bridge_db.update_withdrawal_status("0xw-retry", "releasing_retry") is True
        assert _released_at(bridge_db, "0xw-retry") == "2026-01-03T00:00:00+00:00"

    def test_completed_and_refunded_keep_own_timestamps(self, bridge_db):
        """Terminal writes still stamp completed_at/refunded_at and never
        touch released_at."""
        _insert(bridge_db, "0xw-done")
        assert bridge_db.update_withdrawal_status("0xw-done", "completed") is True
        row = bridge_db.get_withdrawal_by_ait_tx_hash("0xw-done")
        assert row["completed_at"] is not None
        assert row["released_at"] is None

        _insert(bridge_db, "0xw-ref")
        assert bridge_db.update_withdrawal_status("0xw-ref", "refunded", refund_tx_hash="0xrf") is True
        row = bridge_db.get_withdrawal_by_ait_tx_hash("0xw-ref")
        assert row["refunded_at"] is not None
        assert row["released_at"] is None
