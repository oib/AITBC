"""Regression tests for #1575 — wallet persistence stamps must be UTC.

Pre-fix the bridge/chain modules stamped ``datetime.now()`` (host-local,
naive) while ``aitbc-bridge-monitor`` writes aware UTC into the same
``eth_deposits`` table — a naive/aware split-brain on shared ledger rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from wallet_app.utc_time import parse_stored, utc_now, utc_now_iso


class TestUtcTimeHelpers:
    def test_utc_now_is_aware_utc(self):
        now = utc_now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)

    def test_utc_now_iso_carries_offset(self):
        iso = utc_now_iso()
        assert iso.endswith("+00:00")
        parsed = parse_stored(iso)
        assert parsed.tzinfo is not None

    def test_parse_stored_naive_assumes_host_local(self):
        """Legacy naive stamps were written with ``datetime.now()`` —
        host-local wall time — so they must be read back as local, not UTC,
        or every pre-#1575 row skews by the host's UTC offset."""
        naive = "2026-01-02T03:04:05"
        parsed = parse_stored(naive)
        assert parsed.tzinfo is not None
        expected = datetime(2026, 1, 2, 3, 4, 5).astimezone()
        assert parsed == expected

    def test_parse_stored_aware_converts_to_utc(self):
        parsed = parse_stored("2026-01-02T04:04:05+01:00")
        assert parsed.utcoffset() == timedelta(0)
        assert parsed.replace(tzinfo=None) == datetime(2026, 1, 2, 3, 4, 5)

    def test_parse_stored_accepts_datetime(self):
        dt = datetime(2026, 1, 2, 3, 4, 5)
        assert parse_stored(dt).tzinfo is not None


class TestBridgeDbUtcStamps:
    """bridge_db writes must produce aware-UTC ISO stamps matching
    bridge-monitor's format on the shared eth_deposits table."""

    def test_insert_deposit_stamps_utc(self, tmp_path):
        from decimal import Decimal
        from unittest.mock import patch

        from wallet_app.bridge import bridge_db

        db_path = tmp_path / "bridge.db"
        with patch.object(bridge_db, "DB_PATH", str(db_path)):
            bridge_db.init_db()
            deposit_id = bridge_db.insert_deposit(
                tx_hash="0xabc123",
                from_address="0xfrom",
                amount_eth=Decimal("1.5"),
                amount_ait=Decimal("100"),
                recipient="0xto",
                deposit_address="0xdep",
            )
            row = bridge_db.get_deposit_by_id(deposit_id)

        assert row is not None
        created_at = str(row["created_at"])
        # Aware UTC stamp — same shape bridge-monitor writes.
        assert created_at.endswith("+00:00")
        parsed = parse_stored(created_at)
        assert parsed.tzinfo is not None
        # And it is recent (within the last minute).
        assert abs((utc_now() - parsed).total_seconds()) < 60

    def test_committed_since_window_includes_utc_stamps(self, tmp_path):
        from unittest.mock import patch

        from wallet_app.bridge import bridge_db

        db_path = tmp_path / "bridge.db"
        with patch.object(bridge_db, "DB_PATH", str(db_path)):
            bridge_db.init_db()
            since = (utc_now() - timedelta(hours=1)).isoformat()
            # No rows yet — must not raise on the lexical compare.
            assert bridge_db.get_withdrawal_eth_committed_since(since) == 0
