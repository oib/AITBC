"""#1839 BRIDGE-RESURRECTION-1 pins — CAS predicates on deposit flips.

Unconditional ``update_deposit`` writes let a stale reader resurrect a row
another writer already moved terminal (operator write-off → SUBMITTED →
paid), and ``_submit_payout``/the retry path posted envelopes after losing
the race. Each pin FAILS on the unfixed code.
"""

import os
import sys
from decimal import Decimal
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from bridge_monitor import main as bm  # noqa: E402
from bridge_monitor.main import BridgeMonitor  # noqa: E402
from bridge_monitor.storage import (  # noqa: E402
    BridgeDepositStatus,
    create_deposit,
    get_deposit,
    init_db,
    update_deposit,
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr("bridge_monitor.storage.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("bridge_monitor.storage.DB_PATH", str(tmp_path / "deposits.db"))
    init_db()
    from bridge_monitor import storage

    return storage


@pytest.fixture
def monitor(tmp_path, monkeypatch):
    db_path = str(tmp_path / "bridge_deposits.db")
    monkeypatch.setattr("bridge_monitor.storage.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("bridge_monitor.storage.DB_PATH", db_path)
    monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "0x" + "a" * 40)
    monkeypatch.setenv("GENESIS_WALLET_ADDRESS", "0x" + "b" * 40)
    monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", "0x" + "c" * 64)
    monkeypatch.setenv("BRIDGE_MIN_DEPOSIT_AIT", "1")

    with patch("bridge_monitor.main.EthereumRPCClient"), patch("bridge_monitor.main.get_price_oracle"):
        return BridgeMonitor()


RECIPIENT = "0x" + "d" * 40


def _submitted_row(tx_hash: str = "0xsub") -> None:
    create_deposit(tx_hash, "0xf", "1", RECIPIENT)
    update_deposit(
        tx_hash,
        status=BridgeDepositStatus.SUBMITTED,
        signed_tx="{}",
        envelope_hash="0xenv",
        ait_tx_hash="0xenv",
    )


class TestStorageCas:
    def test_expected_statuses_wins_and_loses(self, db):
        create_deposit("0xcas", "0xf", "1", RECIPIENT)
        assert update_deposit(
            "0xcas",
            status=BridgeDepositStatus.PENDING_RETRY,
            expected_statuses={BridgeDepositStatus.PENDING},
        )
        # Row is now pending_retry — a PENDING-predicated write must lose.
        assert not update_deposit(
            "0xcas",
            status=BridgeDepositStatus.SUBMITTED,
            expected_statuses={BridgeDepositStatus.PENDING},
        )
        assert get_deposit("0xcas")["status"] == BridgeDepositStatus.PENDING_RETRY.value
        # String spellings of the enum are accepted too.
        assert update_deposit(
            "0xcas",
            status=BridgeDepositStatus.SUBMITTED,
            expected_statuses={"pending_retry"},
        )
        assert get_deposit("0xcas")["status"] == BridgeDepositStatus.SUBMITTED.value


class TestRetryQueueResurrection:
    def test_signed_tx_flip_cannot_resurrect_written_off(self, monitor):
        """Write-off lands between the retry snapshot and the SUBMITTED flip."""
        create_deposit("0xdead", "0xf", "1", RECIPIENT)
        update_deposit(
            "0xdead",
            status=BridgeDepositStatus.PENDING_RETRY,
            signed_tx="{}",
            next_retry_at="2000-01-01T00:00:00+00:00",
        )
        # Stale snapshot as process_retry_queue saw it before the write-off.
        stale = [
            {
                "eth_tx_hash": "0xdead",
                "ait_recipient": RECIPIENT,
                "ait_amount": "100",
                "eth_amount": "1",
                "signed_tx": "{}",
                "retry_count": 0,
            }
        ]
        update_deposit("0xdead", status=BridgeDepositStatus.WRITTEN_OFF, error_message="operator write-off")
        with patch.object(bm, "get_deposits_for_retry", return_value=stale):
            monitor.process_retry_queue()
        assert get_deposit("0xdead")["status"] == BridgeDepositStatus.WRITTEN_OFF.value

    def test_retry_submit_write_cas_loses_before_post(self, monitor):
        """Row moves terminal after the snapshot — the retry path must not
        write SUBMITTED nor POST the freshly built envelope."""
        create_deposit("0xrace", "0xf", "1", RECIPIENT)
        update_deposit("0xrace", status=BridgeDepositStatus.PENDING_RETRY, next_retry_at="2000-01-01T00:00:00+00:00")
        stale = [
            {
                "eth_tx_hash": "0xrace",
                "ait_recipient": RECIPIENT,
                "ait_amount": "100",
                "eth_amount": "1",
                "signed_tx": None,
                "retry_count": 0,
            }
        ]
        update_deposit("0xrace", status=BridgeDepositStatus.WRITTEN_OFF, error_message="operator write-off")
        envelope = {"type": "TRANSFER", "nonce": 0, "from": "0x" + "b" * 40, "to": RECIPIENT, "amount": 1}
        with (
            patch.object(bm, "get_deposits_for_retry", return_value=stale),
            patch.object(monitor, "_exceeds_payout_cap", return_value=(False, "")),
            patch.object(monitor, "_build_signed_transfer", return_value=envelope),
            patch.object(monitor, "_post_signed_tx") as mock_post,
            patch.object(monitor, "_head_height", return_value=1),
        ):
            monitor.process_retry_queue()
        mock_post.assert_not_called()
        assert get_deposit("0xrace")["status"] == BridgeDepositStatus.WRITTEN_OFF.value


class TestSubmitPayoutCas:
    def test_submit_payout_aborts_when_row_moved(self, monitor):
        """A row already COMPLETED (wallet-side paid it) must not be flipped
        back to SUBMITTED and paid a second time."""
        create_deposit("0xpayout", "0xf", "1", RECIPIENT)
        update_deposit("0xpayout", status=BridgeDepositStatus.COMPLETED, ait_tx_hash="0xaitpaid")
        envelope = {"type": "TRANSFER", "nonce": 0}
        with (
            patch.object(monitor, "_build_signed_transfer", return_value=envelope),
            patch.object(monitor, "_post_signed_tx") as mock_post,
            patch.object(monitor, "_head_height", return_value=1),
        ):
            ok = monitor._submit_payout("0xpayout", RECIPIENT, Decimal("100"))
        assert ok is False
        mock_post.assert_not_called()
        row = get_deposit("0xpayout")
        assert row["status"] == BridgeDepositStatus.COMPLETED.value
        assert row["ait_tx_hash"] == "0xaitpaid"


class TestMarkForRetryCas:
    def test_mark_for_retry_cannot_clobber_submitted(self, monitor):
        """_mark_for_retry on a SUBMITTED row would orphan a live payout
        envelope — the retry write must lose the CAS."""
        _submitted_row("0xheld")
        monitor._mark_for_retry("0xheld", "transient error")
        row = get_deposit("0xheld")
        assert row["status"] == BridgeDepositStatus.SUBMITTED.value
        assert row["signed_tx"] == "{}"
