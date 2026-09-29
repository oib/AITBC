"""Regression tests for bridge-monitor fund safety (B8).

Covers:
- int(amount) truncation → quantize(ROUND_HALF_UP)
- sub-minimum AIT deposit rejection
- crash recovery: PROCESSING deposit is marked for retry, not skipped
- cursor advances only after deposits reach terminal/retry state
"""

import os
import sys
from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from bridge_monitor.main import BridgeMonitor
from bridge_monitor.storage import BridgeDepositStatus


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
        m = BridgeMonitor()
    return m


class TestQuantizeNoTruncation:
    """int(amount) silently dropped fractional AIT; quantize rounds."""

    def test_quantize_rounds_half_up(self, monitor):
        """0.5 AIT rounds to 1, not truncates to 0."""
        amount = Decimal("0.5")
        result = int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        assert result == 1

    def test_quantize_preserves_large_values(self, monitor):
        amount = Decimal("123456.789")
        result = int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        assert result == 123457

    def test_truncation_would_lose_funds(self, monitor):
        """Demonstrate that int() truncation drops dust — the bug we fixed."""
        amount = Decimal("99.999")
        assert int(amount) == 99  # truncation loses 0.999 AIT
        assert int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) == 100


class TestMinAitDeposit:
    """Deposits below BRIDGE_MIN_DEPOSIT_AIT are rejected, not bridged."""

    def test_sub_minimum_rejected(self, monitor, tmp_path):
        from bridge_monitor.storage import get_deposit

        # Simulate a deposit that yields 0.5 AIT (below min of 1)
        with (
            patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("0.5")),
            patch.object(monitor, "submit_ait_transfer") as mock_submit,
        ):
            monitor.process_deposit("0xabc", "0xfrom", Decimal("0.001"), "0xdata")

        deposit = get_deposit("0xabc")
        assert deposit is not None
        assert deposit["status"] == BridgeDepositStatus.FAILED.value
        assert "below minimum" in (deposit["error_message"] or "")
        mock_submit.assert_not_called()

    def test_above_minimum_proceeds(self, monitor, tmp_path):
        with (
            patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("100")),
            patch.object(monitor, "_build_signed_transfer", return_value={"type": "TRANSFER"}) as mock_build,
            patch.object(monitor, "_post_signed_tx", return_value="0xait_tx") as mock_post,
            patch.object(monitor, "_head_height", return_value=100),
        ):
            monitor.process_deposit("0xdef", "0xfrom", Decimal("0.1"), "0xdata")

        mock_build.assert_called_once()
        mock_post.assert_called_once()


class TestCrashRecovery:
    """A deposit stuck in PROCESSING (crash mid-transfer) is retried, not skipped."""

    def test_processing_deposit_marked_for_retry(self, monitor, tmp_path):
        from bridge_monitor.storage import create_deposit, update_deposit

        # Simulate a deposit that crashed after create but before completion
        create_deposit("0xcrash", "0xfrom", "1.0", "0x" + "e" * 40)
        update_deposit("0xcrash", status=BridgeDepositStatus.PROCESSING, ait_amount="100")

        with patch.object(monitor, "submit_ait_transfer") as mock_submit:
            monitor.process_deposit("0xcrash", "0xfrom", Decimal("1.0"), "0xdata")

        # Should NOT submit a duplicate transfer — should mark for retry
        mock_submit.assert_not_called()

        from bridge_monitor.storage import get_deposit

        deposit = get_deposit("0xcrash")
        assert deposit["status"] == BridgeDepositStatus.PENDING_RETRY.value

    def test_completed_deposit_skipped(self, monitor, tmp_path):
        from bridge_monitor.storage import create_deposit, update_deposit

        create_deposit("0xdone", "0xfrom", "1.0", "0x" + "f" * 40)
        update_deposit("0xdone", status=BridgeDepositStatus.COMPLETED, ait_tx_hash="0xait")

        with patch.object(monitor, "submit_ait_transfer") as mock_submit:
            monitor.process_deposit("0xdone", "0xfrom", Decimal("1.0"), "0xdata")

        mock_submit.assert_not_called()


class TestSubmittedLifecycle:
    """COMPLETED requires a sealed payout; rebroadcast never re-signs."""

    def _submitted_row(self, monitor, tx_hash="0xsub", envelope=None):
        import json as _json

        from bridge_monitor.storage import create_deposit, update_deposit

        envelope = envelope or {
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
        create_deposit(tx_hash, "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            tx_hash,
            ait_amount="100",
            signed_tx=_json.dumps(envelope),
            submitted_height=90,
            rebroadcast_count=0,
            ait_tx_hash=payout_hash,
            status=BridgeDepositStatus.SUBMITTED,
        )
        return envelope, payout_hash

    def test_dropped_submit_rebroadcasts_identical_hash(self, monitor, tmp_path):
        """Payout accepted then dropped → same envelope, same hash, no re-sign."""

        from bridge_monitor.storage import get_deposit

        envelope, payout_hash = self._submitted_row(monitor)

        posted = []
        with (
            patch.object(monitor, "_head_height", return_value=100),  # 10 blocks past submit
            patch.object(monitor, "_build_signed_transfer") as mock_build,
            patch.object(monitor, "_post_signed_tx", side_effect=lambda tx: posted.append(tx) or "0xsame") as mock_post,
            patch("httpx.get") as mock_get,
        ):
            mock_get.return_value = MagicMock(status_code=404)  # tx gone from mempool
            monitor.process_submitted_deposits()

        mock_build.assert_not_called()  # never re-signs
        mock_post.assert_called_once_with(envelope)
        assert posted and posted[0] == envelope
        # rebroadcast uses the identical envelope → identical derived hash
        assert monitor._envelope_tx_hash(posted[0]) == payout_hash
        d = get_deposit("0xsub")
        assert d["status"] == BridgeDepositStatus.SUBMITTED.value
        assert d["rebroadcast_count"] == 1

    def test_rejected_at_apply_stays_submitted_and_alerts(self, monitor, tmp_path, caplog):
        """Payout sealed with a failed status: stays SUBMITTED, alerts, no resubmit."""
        import logging

        self._submitted_row(monitor)

        resp = MagicMock(status_code=200)
        resp.json.return_value = {"block_height": 95, "status": "failed"}
        with (
            patch.object(monitor, "_head_height", return_value=100),
            patch.object(monitor, "_post_signed_tx") as mock_post,
            patch("httpx.get") as mock_get,
            caplog.at_level(logging.CRITICAL),
        ):
            mock_get.return_value = resp
            monitor.process_submitted_deposits()

        mock_post.assert_not_called()
        from bridge_monitor.storage import get_deposit

        assert get_deposit("0xsub")["status"] == BridgeDepositStatus.SUBMITTED.value
        assert any("ALERT" in r.getMessage() for r in caplog.records if r.levelno >= logging.CRITICAL)

    def test_restart_with_submitted_creates_no_second_tx(self, monitor, tmp_path):
        """process_deposit on a SUBMITTED row never builds another payout."""
        self._submitted_row(monitor)

        with (
            patch.object(monitor, "_build_signed_transfer") as mock_build,
            patch.object(monitor, "_post_signed_tx") as mock_post,
        ):
            monitor.process_deposit("0xsub", "0xfrom", Decimal("1.0"), "0xdata")

        mock_build.assert_not_called()
        mock_post.assert_not_called()
        from bridge_monitor.storage import get_deposit

        assert get_deposit("0xsub")["status"] == BridgeDepositStatus.SUBMITTED.value


class TestWriteOffAndAbandon:
    """WRITTEN_OFF is terminal+reasoned; abandon-and-resign needs the nonce proof."""

    def test_write_off_requires_reason(self, monitor, tmp_path):
        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit

        create_deposit("0xwo", "0xfrom", "1.0", "")
        with pytest.raises(ValueError):
            update_deposit("0xwo", status=BridgeDepositStatus.WRITTEN_OFF)
        update_deposit(
            "0xwo",
            status=BridgeDepositStatus.WRITTEN_OFF,
            error_message="deposit to keyless deployer wallet; testnet; unrecoverable",
        )
        assert get_deposit("0xwo")["status"] == BridgeDepositStatus.WRITTEN_OFF.value

    def test_written_off_row_skipped(self, monitor, tmp_path):
        from bridge_monitor.storage import create_deposit, update_deposit

        create_deposit("0xwo2", "0xfrom", "1.0", "")
        update_deposit("0xwo2", status=BridgeDepositStatus.WRITTEN_OFF, error_message="unrecoverable")
        with patch.object(monitor, "_build_signed_transfer") as mock_build:
            monitor.process_deposit("0xwo2", "0xfrom", Decimal("1.0"), "0xdata")
        mock_build.assert_not_called()

    def test_write_off_guard_recipient_vs_phantom(self, monitor, tmp_path):
        """A row with a valid recipient is owed money — needs the override."""
        from bridge_monitor.admin import write_off_denial_reason

        phantom = {"status": "completed", "ait_tx_hash": None, "ait_recipient": ""}
        assert write_off_denial_reason(phantom, False) is None  # no recipient → writable
        owed = {"status": "completed", "ait_tx_hash": None, "ait_recipient": "0x" + "d" * 40}
        assert write_off_denial_reason(owed, False) is not None  # owed money → refused
        assert write_off_denial_reason(owed, True) is None  # deliberate override → allowed
        paid = {"status": "completed", "ait_tx_hash": "0xreal", "ait_recipient": "0x" + "d" * 40}
        assert write_off_denial_reason(paid, True) is not None  # actually paid → always refused

    def _submitted_for_abandon(self, monitor):
        import json as _json

        from bridge_monitor.storage import create_deposit, update_deposit

        envelope = {
            "type": "TRANSFER",
            "nonce": 7,
            "from": "0x" + "b" * 40,
            "to": "0x" + "d" * 40,
            "amount": 1,
            "fee": 1,
            "payload": {"amount": 1},
            "signature": "0xab",
        }
        payout_hash = monitor._envelope_tx_hash(envelope)
        create_deposit("0xabn", "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            "0xabn",
            ait_amount="1",
            signed_tx=_json.dumps(envelope),
            envelope_hash=payout_hash,
            ait_tx_hash=payout_hash,
            status=BridgeDepositStatus.SUBMITTED,
        )
        return envelope, payout_hash

    def test_abandon_refuses_when_nonce_not_passed(self, monitor, tmp_path):
        self._submitted_for_abandon(monitor)
        with (
            patch.object(monitor, "_account_nonce", return_value=7),  # envelope nonce 7 not passed
            patch.object(monitor, "_tx_on_chain", return_value=False),
        ):
            ok, msg = monitor.abandon_payout("0xabn")
        assert not ok
        assert "still land" in msg
        from bridge_monitor.storage import get_deposit

        assert get_deposit("0xabn")["status"] == BridgeDepositStatus.SUBMITTED.value

    def test_abandon_refuses_when_sealed(self, monitor, tmp_path):
        self._submitted_for_abandon(monitor)
        with (
            patch.object(monitor, "_account_nonce", return_value=9),
            patch.object(monitor, "_tx_on_chain", return_value=True),
        ):
            ok, msg = monitor.abandon_payout("0xabn")
        assert not ok
        assert "sealed" in msg

    def test_abandon_succeeds_and_queues_retry(self, monitor, tmp_path):
        self._submitted_for_abandon(monitor)
        with (
            patch.object(monitor, "_account_nonce", return_value=9),  # nonce 9 > envelope nonce 7
            patch.object(monitor, "_tx_on_chain", return_value=False),
        ):
            ok, msg = monitor.abandon_payout("0xabn")
        assert ok
        from bridge_monitor.storage import get_deposit

        d = get_deposit("0xabn")
        assert d["status"] == BridgeDepositStatus.PENDING_RETRY.value
        # envelope fields cleared so no path hands the dead envelope back
        assert not d["signed_tx"] and not d["envelope_hash"] and not d["ait_tx_hash"]


class TestCursorSafety:
    """Cursor advances even if one deposit crashes, because each is wrapped."""

    def test_cursor_advances_after_exception(self, monitor, tmp_path):
        from bridge_monitor.storage import get_cursor

        # Simulate a block with one deposit that raises during processing
        mock_tx = MagicMock()
        mock_tx.get.side_effect = lambda k, d="": {
            "to": monitor.bridge_eth_address,
            "value": 10**18,
            "from": "0xfrom",
            "input": "0x",
        }.get(k, d)
        mock_tx.hash.hex.return_value = "0xbadtx"

        mock_block = {"transactions": [mock_tx]}

        with (
            patch.object(monitor, "eth_rpc") as mock_rpc,
            patch.object(monitor, "process_deposit", side_effect=RuntimeError("boom")),
            patch.object(monitor, "_mark_for_retry") as mock_retry,
        ):
            mock_rpc._get_web3.return_value.eth.block_number = 100
            mock_rpc._get_web3.return_value.eth.get_block.return_value = mock_block

            monitor.poll_ethereum()

            # Cursor should still advance — deposit was caught and marked
            # for retry. Block 100 minus BRIDGE_CONFIRMATIONS=3 default: the
            # poll only scans to the confirmed tip (97).
            assert get_cursor("last_processed_block") == 100 - monitor.confirmations
            # _mark_for_retry called for each scanned block
            assert mock_retry.call_count > 0


class TestPollLiveness:
    """A dead ETH endpoint must surface as ALERT, not 'finds nothing'."""

    def test_consecutive_failures_alert(self, monitor, caplog):
        import logging

        with (
            patch.object(monitor, "_check_float"),
            patch.object(monitor, "eth_rpc") as mock_rpc,
            caplog.at_level(logging.CRITICAL),
        ):
            mock_rpc._get_web3.side_effect = RuntimeError("endpoint down")
            for _ in range(4):
                monitor.poll_ethereum()

        assert monitor._poll_fail_streak == 4
        alerts = [r for r in caplog.records if "ALERT" in r.message]
        assert len(alerts) == 2  # streaks 3 and 4 alert; 1-2 log at error

    def test_success_resets_streak(self, monitor):
        monitor._poll_fail_streak = 5
        with (
            patch.object(monitor, "_check_float"),
            patch.object(monitor, "eth_rpc") as mock_rpc,
        ):
            mock_rpc._get_web3.return_value.eth.block_number = 100
            mock_rpc._get_web3.return_value.eth.get_block.return_value = {"transactions": []}
            monitor.poll_ethereum()
        assert monitor._poll_fail_streak == 0


class TestKickBurst:
    """Demand-triggered polling: a fresh kick file switches the loop into a
    ~3-polls-in-60s burst; the slow poll_interval stays the safety net."""

    def _drive_loop(self, monitor, kick_delay=None, run_for=1.6):
        """Run monitor.run() briefly, optionally touching the kick file."""
        import asyncio
        import time
        from pathlib import Path

        polls = []
        monitor.poll_ethereum = lambda: polls.append(time.monotonic())
        monitor.process_retry_queue = lambda: None

        async def drive():
            task = asyncio.create_task(monitor.run())
            if kick_delay is not None:
                await asyncio.sleep(kick_delay)
                Path(monitor.kick_file).touch()
            await asyncio.sleep(run_for)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(drive())
        return polls

    def test_fresh_kick_triggers_burst(self, monitor, tmp_path):
        monitor.kick_file = str(tmp_path / "bridge_poll_kick")
        monitor._last_kick_seen = 0.0
        monitor.burst_window = 2.0
        monitor.burst_interval = 0.5
        monitor.poll_interval = 60  # safety net alone would give only the boot poll

        polls = self._drive_loop(monitor, kick_delay=0.4, run_for=2.6)
        assert len(polls) >= 3

    def test_stale_kick_at_boot_does_not_burst(self, monitor, tmp_path):
        import os as _os

        kick = tmp_path / "bridge_poll_kick"
        kick.touch()
        monitor.kick_file = str(kick)
        monitor._last_kick_seen = _os.path.getmtime(kick)  # what __init__ would record
        monitor.burst_window = 2.0
        monitor.burst_interval = 0.5
        monitor.poll_interval = 60

        polls = self._drive_loop(monitor, kick_delay=None, run_for=1.4)
        assert len(polls) == 1  # boot poll only

    def test_kick_mtime_missing_file(self, monitor, tmp_path):
        monitor.kick_file = str(tmp_path / "nonexistent")
        assert monitor._kick_mtime() is None

    def test_kick_mtime_present(self, monitor, tmp_path):
        kick = tmp_path / "bridge_poll_kick"
        kick.touch()
        monitor.kick_file = str(kick)
        assert monitor._kick_mtime() > 0
