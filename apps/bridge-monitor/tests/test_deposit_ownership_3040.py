"""#3040 AUDIT-BRIDGE-DEPOSIT-DOUBLE-PAY-1 pins — provable deposit-row ownership.

``eth_deposits`` is ONE sqlite table shared by aitbc-bridge-monitor and the
wallet service's embedded deposit watcher; both scan the same Ethereum
address for the same bridge wallet. 'pending' is the wallet watcher's own
insert state, so the monitor may adopt a pending row into its payout
pipeline ONLY when ``owner='monitor'`` proves the row is its own crash
remnant. These pins FAIL on the unfixed code: a wallet-written
(``owner='wallet'``) or ambiguous legacy (``owner`` NULL) 'pending' row
must never reach ``_submit_payout``.
"""

import os
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from bridge_monitor import storage  # noqa: E402
from bridge_monitor.main import BridgeMonitor  # noqa: E402
from bridge_monitor.storage import BridgeDepositStatus  # noqa: E402


@pytest.fixture
def monitor(tmp_path, monkeypatch):
    """BridgeMonitor with temp DB and stubbed external deps."""
    db_path = str(tmp_path / "bridge_deposits.db")
    monkeypatch.setattr("bridge_monitor.storage.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("bridge_monitor.storage.DB_PATH", db_path)
    monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "0x" + "a" * 40)
    monkeypatch.setenv("GENESIS_WALLET_ADDRESS", "0x" + "b" * 40)
    monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", "0x" + "c" * 64)
    monkeypatch.setenv("BRIDGE_MIN_DEPOSIT_AIT", "1")

    with patch("bridge_monitor.main.EthereumRPCClient"), patch("bridge_monitor.main.get_price_oracle"):
        return BridgeMonitor()


def _seed_foreign_row(
    tx_hash: str,
    status: str = "pending",
    owner: str | None = "wallet",
    created_at: str | None = None,
) -> None:
    """Insert a row exactly as the wallet side's ``insert_deposit`` writes
    it — same columns, ``owner='wallet'`` — bypassing the monitor's
    ``create_deposit`` so the scan sees a genuinely foreign row."""
    with sqlite3.connect(str(storage.DB_PATH)) as conn:
        conn.execute(
            """
            INSERT INTO eth_deposits
            (id, tx_hash, from_address, recipient, amount_eth, amount_ait, status, created_at, owner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"deposit_foreign_{tx_hash[-6:]}",
                tx_hash,
                "0xfrom",
                "0x" + "d" * 40,
                "1.0",
                "100",
                status,
                created_at or datetime.now(UTC).isoformat(),
                owner,
            ),
        )


def _backdate(tx_hash: str, hours: float = 48.0) -> None:
    """Age a row past the stranded-detector horizon."""
    old = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    with sqlite3.connect(str(storage.DB_PATH)) as conn:
        conn.execute("UPDATE eth_deposits SET created_at = ? WHERE tx_hash = ?", (old, tx_hash))


class TestOwnershipStamp:
    def test_create_deposit_stamps_monitor_owner(self, monitor):
        assert storage.create_deposit("0xown1", "0xf", "1", "r") is not None
        row = storage.get_deposit("0xown1")
        assert row is not None
        assert row["owner"] == "monitor"

    def test_owner_column_exists_after_init(self, monitor):
        with sqlite3.connect(str(storage.DB_PATH)) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(eth_deposits)")}
        assert "owner" in columns


class TestPendingAdoptionGate:
    """The scan-side adoption in ``_handle_existing_deposit``."""

    def test_wallet_pending_row_never_adopted(self, monitor):
        """The core defect: a wallet-created 'pending' row (mid-mint or
        parked by the #2831 shared-account refusal) must NOT enter the
        monitor payout pipeline."""
        _seed_foreign_row("0xwpay", status="pending", owner="wallet")

        with (
            patch.object(monitor, "_submit_payout") as mock_submit,
            patch.object(monitor, "_build_signed_transfer") as mock_build,
            patch.object(monitor, "_post_signed_tx") as mock_post,
        ):
            monitor.process_deposit("0xwpay", "0xfrom", Decimal("1.0"), "0xdata")

        mock_submit.assert_not_called()
        mock_build.assert_not_called()
        mock_post.assert_not_called()
        row = storage.get_deposit("0xwpay")
        assert row is not None
        assert row["status"] == "pending"
        assert row["owner"] == "wallet"

    def test_legacy_null_pending_row_never_adopted(self, monitor):
        """Pre-column rows have owner NULL — 'pending' is ambiguous (either
        service could have written it), so the monitor must not guess."""
        _seed_foreign_row("0xlegp", status="pending", owner=None)

        with (
            patch.object(monitor, "_submit_payout") as mock_submit,
            patch.object(monitor, "_build_signed_transfer") as mock_build,
        ):
            monitor.process_deposit("0xlegp", "0xfrom", Decimal("1.0"), "0xdata")

        mock_submit.assert_not_called()
        mock_build.assert_not_called()
        assert storage.get_deposit("0xlegp")["status"] == "pending"

    def test_wallet_owned_monitor_only_status_still_refused(self, monitor):
        """Defense in depth: even a status only the monitor vocabulary
        produces is refused when the owner mark says 'wallet'."""
        _seed_foreign_row("0xwpm", status="processing", owner="wallet")

        with patch.object(monitor, "_submit_payout") as mock_submit:
            monitor.process_deposit("0xwpm", "0xfrom", Decimal("1.0"), "0xdata")

        mock_submit.assert_not_called()
        assert storage.get_deposit("0xwpm")["status"] == "processing"

    def test_monitor_pending_crash_remnant_still_adopted(self, monitor):
        """Recovery must keep working for rows THIS service created: a
        monitor-owned 'pending' row (crash between insert and SUBMITTED)
        still requeues into the retry sweep."""
        assert storage.create_deposit("0xmrem", "0xf", "1.0", "0x" + "e" * 40) is not None

        with patch.object(monitor, "_submit_payout") as mock_submit:
            monitor.process_deposit("0xmrem", "0xf", Decimal("1.0"), "0xdata")

        mock_submit.assert_not_called()  # adoption requeues; the sweep pays later
        row = storage.get_deposit("0xmrem")
        assert row["status"] == BridgeDepositStatus.PENDING_RETRY.value

    def test_null_processing_row_still_adopted(self, monitor):
        """'processing'/'pending_retry' are monitor-only vocabulary — the
        wallet side cannot produce them, so a NULL-owner row in one is
        unambiguously a legacy monitor crash remnant."""
        _seed_foreign_row("0xnullp", status="processing", owner=None)

        with patch.object(monitor, "_submit_payout") as mock_submit:
            monitor.process_deposit("0xnullp", "0xfrom", Decimal("1.0"), "0xdata")

        mock_submit.assert_not_called()
        assert storage.get_deposit("0xnullp")["status"] == BridgeDepositStatus.PENDING_RETRY.value

    def test_null_pending_retry_row_requeued_normally(self, monitor):
        """A NULL-owner pending_retry row (legacy monitor worklist state)
        still gets the scan-recovery normalization."""
        _seed_foreign_row("0xnullr", status="pending_retry", owner=None)

        with patch.object(monitor, "_submit_payout") as mock_submit:
            monitor.process_deposit("0xnullr", "0xfrom", Decimal("1.0"), "0xdata")

        mock_submit.assert_not_called()
        row = storage.get_deposit("0xnullr")
        assert row["status"] == BridgeDepositStatus.PENDING_RETRY.value


class TestDoublePaySequence:
    """The deterministic #3040 sequence, end to end at the monitor boundary."""

    def test_wallet_mint_then_postsubmit_failure_never_double_pays(self, monitor):
        """wallet inserts pending → monitor scan must refuse → wallet's
        post-submit CAS failure parks the row 'failed' → the monitor's
        next scan sees a terminal row and still pays nothing."""
        _seed_foreign_row("0xdpay", status="pending", owner="wallet")

        with (
            patch.object(monitor, "_submit_payout") as mock_submit,
            patch.object(monitor, "_post_signed_tx") as mock_post,
        ):
            # Pass 1: wallet mint in flight — monitor must not adopt.
            monitor.process_deposit("0xdpay", "0xfrom", Decimal("1.0"), "0xdata")
            assert storage.get_deposit("0xdpay")["status"] == "pending"

            # The wallet's fixed post-submit path parks the row 'failed'
            # (its TRANSFER already broadcast — re-pending is what fed
            # the double pay). Simulate that terminal write.
            assert storage.update_deposit(
                "0xdpay",
                status=BridgeDepositStatus.FAILED,
                error_message="post-submit CAS failure — parked for reconcile",
                expected_statuses={"pending"},
            )

            # Pass 2: monitor rescans — 'failed' is terminal for it too.
            monitor.process_deposit("0xdpay", "0xfrom", Decimal("1.0"), "0xdata")

        mock_submit.assert_not_called()
        mock_post.assert_not_called()
        row = storage.get_deposit("0xdpay")
        assert row["status"] == "failed"

    def test_stranded_detector_still_sees_unadopted_pending(self, monitor):
        """A refused wallet/legacy 'pending' row is not silently dropped —
        past the horizon the stranded detector owns its visibility."""
        _seed_foreign_row("0xvis", status="pending", owner="wallet")
        _backdate("0xvis")

        cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        stranded = {d["eth_tx_hash"]: d["status"] for d in storage.get_stranded_deposits(cutoff)}
        assert stranded.get("0xvis") == "pending"
