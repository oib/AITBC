"""#1918 BRIDGE-WRITEPATH-CAS-1 pins — write-off CAS + sweep admin flock.

- ``admin.py write-off`` must not flip a row that moved to a terminal
  status between the command's read and its write (the denial check ran
  on a snapshot).
- ``process_submitted_deposits`` must not POST a rebroadcast while an
  admin mutation holds the ledger flock — the fresh-check → POST →
  count-write sequence is check-then-act and needs the same
  serialization the payout paths already take.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from bridge_monitor import admin  # noqa: E402
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


@pytest.fixture
def admin_db(tmp_path, monkeypatch):
    """Ledger DB pointed at tmp_path for admin.main() invocations."""
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "admin_deposits.db"))
    storage.init_db()
    return storage


def _run_admin(monkeypatch, tmp_path, *argv: str) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        ["bridge-admin", "--env-file", str(tmp_path / "missing.env"), *argv],
    )
    return admin.main()


class TestWriteOffCas:
    def test_write_off_applies_from_live_status(self, admin_db, tmp_path, monkeypatch):
        admin_db.create_deposit("0xwo1", "0xf", "1", "")
        rc = _run_admin(monkeypatch, tmp_path, "write-off", "0xwo1", "--reason", "keyless wallet")
        assert rc == 0
        assert admin_db.get_deposit("0xwo1")["status"] == BridgeDepositStatus.WRITTEN_OFF.value

    def test_write_off_loses_when_row_moved_terminal(self, admin_db, tmp_path, monkeypatch):
        """The denial check sees a stale PENDING snapshot while the ledger
        row already FAILED — the CAS must refuse, not resurrect it."""
        admin_db.create_deposit("0xwo2", "0xf", "1", "")
        admin_db.update_deposit("0xwo2", status=BridgeDepositStatus.FAILED, error_message="already failed")
        real_get = admin_db.get_deposit
        stale = {**real_get("0xwo2"), "status": BridgeDepositStatus.PENDING.value}
        monkeypatch.setattr(admin_db, "get_deposit", lambda h: stale if h == "0xwo2" else real_get(h))

        rc = _run_admin(monkeypatch, tmp_path, "write-off", "0xwo2", "--reason", "stale read")

        assert rc == 1
        row = real_get("0xwo2")
        assert row["status"] == BridgeDepositStatus.FAILED.value
        assert row["error_message"] == "already failed"

    def test_write_off_loses_when_row_completed_paid(self, admin_db, tmp_path, monkeypatch):
        """A payout sealing between read and write must win over the
        write-off — COMPLETED is outside the CAS source set."""
        admin_db.create_deposit("0xwo3", "0xf", "1", "")
        real_get = admin_db.get_deposit
        stale = {**real_get("0xwo3"), "status": BridgeDepositStatus.PENDING.value}
        monkeypatch.setattr(admin_db, "get_deposit", lambda h: stale if h == "0xwo3" else real_get(h))
        # The seal landed after the (stale) read.
        admin_db.update_deposit(
            "0xwo3",
            status=BridgeDepositStatus.COMPLETED,
            ait_tx_hash="0xpaid",
        )

        rc = _run_admin(monkeypatch, tmp_path, "write-off", "0xwo3", "--reason", "raced seal")

        assert rc == 1
        row = real_get("0xwo3")
        assert row["status"] == BridgeDepositStatus.COMPLETED.value
        assert row["ait_tx_hash"] == "0xpaid"


class TestSubmittedSweepAdminLock:
    def _submitted_row(self, monitor):
        envelope = {
            "type": "TRANSFER",
            "chain_id": "ait-test",
            "from": "0x" + "b" * 40,
            "to": "0x" + "d" * 40,
            "amount": 123,
            "nonce": 7,
            "fee": 360000,
            "payload": {"amount": 123},
            "signature": "0xdeadbeef",
        }
        payout_hash = monitor._envelope_tx_hash(envelope)
        storage.create_deposit("0xlocksub", "0xfrom", "1.0", "0x" + "d" * 40)
        storage.update_deposit(
            "0xlocksub",
            ait_amount="100",
            signed_tx=json.dumps(envelope),
            submitted_height=90,
            rebroadcast_count=0,
            ait_tx_hash=payout_hash,
            envelope_hash=payout_hash,
            status=BridgeDepositStatus.SUBMITTED,
        )
        return envelope

    def test_rebroadcast_defers_while_admin_lock_held(self, monitor):
        """try_admin_lock -> None: the sweep logs and skips — the POST is
        never attempted, so an admin write-off cannot be raced."""
        self._submitted_row(monitor)
        with (
            patch.object(monitor, "_head_height", return_value=100),
            patch.object(monitor, "_account_nonce", return_value=0),  # abandon refuses: nonce not passed
            patch.object(monitor, "_post_signed_tx") as mock_post,
            patch("bridge_monitor.main.try_admin_lock", return_value=None),
            patch("httpx.get") as mock_get,
        ):
            mock_get.return_value = MagicMock(status_code=404)  # tx gone from mempool
            monitor.process_submitted_deposits()

        mock_post.assert_not_called()
        row = storage.get_deposit("0xlocksub")
        assert row["status"] == BridgeDepositStatus.SUBMITTED.value
        assert row["rebroadcast_count"] == 0

    def test_rebroadcast_proceeds_when_lock_free(self, monitor):
        """Same row with the lock available: the identical envelope is
        rebroadcast and the count advances — the flock is not a stall."""
        envelope = self._submitted_row(monitor)
        lock_calls = []

        def _fake_lock():
            lock_calls.append(1)
            return os.open(os.devnull, os.O_RDONLY)  # any fd; os.close releases

        with (
            patch.object(monitor, "_head_height", return_value=100),
            patch.object(monitor, "_account_nonce", return_value=0),
            patch.object(monitor, "_post_signed_tx", return_value="0xsame") as mock_post,
            patch("bridge_monitor.main.try_admin_lock", side_effect=_fake_lock),
            patch("httpx.get") as mock_get,
        ):
            mock_get.return_value = MagicMock(status_code=404)
            monitor.process_submitted_deposits()

        mock_post.assert_called_once_with(envelope)
        assert lock_calls  # the lock was actually taken
        row = storage.get_deposit("0xlocksub")
        assert row["rebroadcast_count"] == 1
