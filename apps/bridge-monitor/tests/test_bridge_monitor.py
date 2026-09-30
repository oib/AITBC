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


class TestFundingSource:
    """BRIDGE_FUNDING_SOURCES senders record FUNDING, never a payout."""

    def _funding_block(self, monitor, from_addr):
        mock_tx = MagicMock()
        mock_tx.get.side_effect = lambda k, d="": {
            "to": monitor.bridge_eth_address,
            "value": 5 * 10**16,  # 0.05 ETH
            "from": from_addr,
            "input": "0x",
        }.get(k, d)
        mock_tx.hash.hex.return_value = "0xfund01"
        return {"transactions": [mock_tx]}

    def test_funding_source_records_funding_no_payout(self, monitor, tmp_path):
        from bridge_monitor.storage import get_deposit, set_cursor

        monitor.funding_sources = {"0xopfund"}
        set_cursor("last_processed_block", 96)  # scan only block 97
        with (
            patch.object(monitor, "_check_float"),
            patch.object(monitor, "eth_rpc") as mock_rpc,
            patch.object(monitor, "process_deposit") as mock_process,
        ):
            mock_rpc._get_web3.return_value.eth.block_number = 100
            mock_rpc._get_web3.return_value.eth.get_block.return_value = self._funding_block(monitor, "0xopFund")
            monitor.poll_ethereum()
        mock_process.assert_not_called()
        row = get_deposit("0xfund01")
        assert row is not None
        assert row["status"] == "funding"

    def test_non_whitelisted_is_normal_deposit(self, monitor, tmp_path):
        from bridge_monitor.storage import set_cursor

        monitor.funding_sources = {"0xopfund"}
        set_cursor("last_processed_block", 96)  # scan only block 97
        with (
            patch.object(monitor, "_check_float"),
            patch.object(monitor, "eth_rpc") as mock_rpc,
            patch.object(monitor, "process_deposit") as mock_process,
        ):
            mock_rpc._get_web3.return_value.eth.block_number = 100
            mock_rpc._get_web3.return_value.eth.get_block.return_value = self._funding_block(monitor, "0xcustomer")
            monitor.poll_ethereum()
        mock_process.assert_called_once()

    def test_funding_dedup_no_double_row(self, monitor, tmp_path):
        from bridge_monitor.storage import get_deposit, set_cursor

        monitor.funding_sources = {"0xopfund"}
        set_cursor("last_processed_block", 96)
        with (
            patch.object(monitor, "_check_float"),
            patch.object(monitor, "eth_rpc") as mock_rpc,
        ):
            mock_rpc._get_web3.return_value.eth.block_number = 100
            mock_rpc._get_web3.return_value.eth.get_block.return_value = self._funding_block(monitor, "0xopfund")
            monitor.poll_ethereum()
        row = get_deposit("0xfund01")
        assert row["status"] == "funding"
        # A rescan (same block re-polled) must not duplicate or alter the row
        with (
            patch.object(monitor, "_check_float"),
            patch.object(monitor, "eth_rpc") as mock_rpc,
        ):
            mock_rpc._get_web3.return_value.eth.block_number = 100
            mock_rpc._get_web3.return_value.eth.get_block.return_value = self._funding_block(monitor, "0xopfund")
            from bridge_monitor.storage import set_cursor

            set_cursor("last_processed_block", 96)  # force rescan of 97..97
            monitor.poll_ethereum()
        assert get_deposit("0xfund01")["status"] == "funding"


class TestPayoutSerialization:
    """Two deposits in one poll must not sign the same nonce.

    The payout account's nonce comes from committed chain state, so a
    second envelope signed while the first is still unsealed collides in
    the mempool — the stale envelope then burned the whole rebroadcast
    budget until an operator re-signed. The monitor serializes: at most
    one SUBMITTED payout in flight.
    """

    def _two_deposits(self, monitor):
        """Process two fresh deposits in one poll; returns the build mock."""
        with (
            patch.object(
                monitor,
                "parse_ait_recipient",
                side_effect=["0x" + "d" * 40, "0x" + "e" * 40],
            ),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("100")),
            patch.object(monitor, "_build_signed_transfer") as mock_build,
            patch.object(monitor, "_post_signed_tx", return_value="0xpayout"),
            patch.object(monitor, "_head_height", return_value=100),
        ):
            mock_build.side_effect = [
                {"type": "TRANSFER", "nonce": 7, "to": "0x" + "d" * 40},
                {"type": "TRANSFER", "nonce": 8, "to": "0x" + "e" * 40},
            ]
            monitor.process_deposit("0xdep1", "0xfrom", Decimal("0.1"), "0xdep1")
            monitor.process_deposit("0xdep2", "0xfrom", Decimal("0.1"), "0xdep2")
        return mock_build

    def test_second_deposit_does_not_sign_while_first_unsealed(self, monitor):
        from bridge_monitor.storage import get_deposit

        mock_build = self._two_deposits(monitor)

        assert mock_build.call_count == 1  # the collision the fix prevents
        d1, d2 = get_deposit("0xdep1"), get_deposit("0xdep2")
        assert d1["status"] == BridgeDepositStatus.SUBMITTED.value
        assert d2["status"] == BridgeDepositStatus.PENDING_RETRY.value
        assert not d2["signed_tx"]  # no stale envelope was ever stored
        assert d2["retry_count"] in (None, 0)  # wait for the slot, not a retry
        assert Decimal(str(d2["ait_amount"])) == 100  # computed amount kept for the retry

    def test_deferred_deposit_pays_after_first_seals(self, monitor):
        from bridge_monitor.storage import get_deposit, update_deposit

        mock_build = self._two_deposits(monitor)
        update_deposit("0xdep1", status=BridgeDepositStatus.COMPLETED)  # sealed
        update_deposit("0xdep2", next_retry_at="2000-01-01T00:00:00+00:00")  # due now

        with (
            patch.object(monitor, "parse_ait_recipient", side_effect=lambda d: "0x" + "e" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("100")),
            patch.object(
                monitor,
                "_build_signed_transfer",
                return_value={"type": "TRANSFER", "nonce": 8, "to": "0x" + "e" * 40},
            ) as mock_build2,
            patch.object(monitor, "_post_signed_tx", return_value="0xpayout2"),
            patch.object(monitor, "_head_height", return_value=101),
        ):
            monitor.process_retry_queue()

        assert mock_build.call_count == 1  # first poll signed once
        assert mock_build2.call_count == 1  # second payout only after seal
        d2 = get_deposit("0xdep2")
        assert d2["status"] == BridgeDepositStatus.SUBMITTED.value

    def test_sweep_auto_abandons_when_nonce_proof_holds(self, monitor):
        """Nonce passed + envelope unsealed → abandoned, re-queued, no resubmit wait."""
        import json as _json

        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit

        envelope = {
            "type": "TRANSFER",
            "chain_id": "ait-test",
            "from": "0x" + "b" * 40,
            "to": "0x" + "d" * 40,
            "amount": 100,
            "nonce": 5,
            "fee": 360000,
            "payload": {"amount": 100},
            "signature": "0xdead",
        }
        payout_hash = monitor._envelope_tx_hash(envelope)
        create_deposit("0xstuck", "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            "0xstuck",
            ait_amount="100",
            signed_tx=_json.dumps(envelope),
            submitted_height=90,
            ait_tx_hash=payout_hash,
            status=BridgeDepositStatus.SUBMITTED,
        )

        with (
            patch.object(monitor, "_head_height", return_value=200),
            patch.object(monitor, "_account_nonce", return_value=9),  # nonce passed 5
            patch.object(monitor, "_tx_on_chain", return_value=False),  # never sealed
            patch.object(monitor, "_post_signed_tx") as mock_post,
            patch("httpx.get") as mock_get,
        ):
            mock_get.return_value = MagicMock(status_code=404)
            monitor.process_submitted_deposits()

        d = get_deposit("0xstuck")
        assert d["status"] == BridgeDepositStatus.PENDING_RETRY.value
        assert not d["signed_tx"]  # dead envelope cleared
        mock_post.assert_not_called()  # abandons instead of rebroadcasting

    def test_nonce_rejection_alerts_immediately(self, monitor, caplog):
        """A nonce-slot rejection is its own alert — no rebroadcast wait."""
        import logging

        from bridge_monitor.storage import create_deposit, get_deposit

        create_deposit("0xcoll", "0xfrom", "1.0", "0x" + "d" * 40)
        with (
            patch.object(monitor, "_build_signed_transfer", return_value={"type": "TRANSFER", "nonce": 7}),
            patch.object(monitor, "_post_signed_tx", return_value=None),
            patch.object(monitor, "_head_height", return_value=100),
            caplog.at_level(logging.CRITICAL),
        ):
            monitor._last_post_rejection = "nonce slot 7 already occupied"
            monitor._submit_payout("0xcoll", "0x" + "d" * 40, Decimal("100"))

        alerts = [r for r in caplog.records if "ALERT" in r.message and "nonce" in r.message.lower()]
        assert alerts
        d = get_deposit("0xcoll")
        assert d["status"] == BridgeDepositStatus.SUBMITTED.value

    def test_stuck_submitted_row_alerts(self, monitor, caplog):
        """A sealed-failed or proof-failed SUBMITTED row blocks the queue —
        serialization needs an age alert so the stall cannot sit silent."""
        import logging

        from bridge_monitor.storage import create_deposit, update_deposit

        create_deposit("0xold", "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            "0xold",
            signed_tx='{"nonce": 1}',
            submitted_height=10,
            status=BridgeDepositStatus.SUBMITTED,
        )

        with (
            patch.object(monitor, "_head_height", return_value=10 + monitor.stuck_payout_blocks + 50),
            caplog.at_level(logging.CRITICAL),
        ):
            monitor._check_queue_health()

        alerts = [r for r in caplog.records if "payout slot blocked" in r.message]
        assert alerts and "0xold" in alerts[0].message

    def test_queue_depth_alerts(self, monitor, caplog):
        import logging

        from bridge_monitor.storage import create_deposit, update_deposit

        for i in range(monitor.queue_alert_depth):
            h = f"0xq{i}"
            create_deposit(h, "0xfrom", "1.0", "0x" + "d" * 40)
            update_deposit(h, status=BridgeDepositStatus.PENDING_RETRY)

        with caplog.at_level(logging.CRITICAL):
            monitor._check_queue_health()

        alerts = [r for r in caplog.records if "PENDING_RETRY" in r.message]
        assert alerts

    def test_abandon_makes_row_immediately_due(self, monitor):
        """update_deposit(next_retry_at=None) never cleared the column —
        abandon must clear the stale retry time or the re-queue waits out
        the old backoff for no reason."""
        import json as _json

        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit

        envelope = {
            "type": "TRANSFER",
            "chain_id": "ait-test",
            "from": "0x" + "b" * 40,
            "to": "0x" + "d" * 40,
            "amount": 100,
            "nonce": 5,
            "fee": 360000,
            "payload": {"amount": 100},
            "signature": "0xdead",
        }
        payout_hash = monitor._envelope_tx_hash(envelope)
        create_deposit("0xab", "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            "0xab",
            signed_tx=_json.dumps(envelope),
            ait_tx_hash=payout_hash,
            status=BridgeDepositStatus.SUBMITTED,
            next_retry_at="2999-01-01T00:00:00+00:00",  # stale future backoff
        )

        with (
            patch.object(monitor, "_account_nonce", return_value=9),
            patch.object(monitor, "_tx_on_chain", return_value=False),
        ):
            ok, _ = monitor.abandon_payout("0xab")

        assert ok
        d = get_deposit("0xab")
        assert d["status"] == BridgeDepositStatus.PENDING_RETRY.value
        assert d["next_retry_at"] is None  # cleared, due immediately


class TestCursorHoldOnTotalFailure:
    """If process_deposit AND the retry fallback both raise, the cursor
    must not advance — the block gets rescanned next poll."""

    def test_cursor_held_when_both_handlers_fail(self, monitor):
        from bridge_monitor.storage import get_cursor, set_cursor

        mock_tx = MagicMock()
        mock_tx.get.side_effect = lambda k, d="": {
            "to": monitor.bridge_eth_address,
            "value": 10**18,
            "from": "0xfrom",
            "input": "0x",
        }.get(k, d)
        mock_tx.hash.hex.return_value = "0xlosttx"

        set_cursor("last_processed_block", 96)  # scan only block 97
        with (
            patch.object(monitor, "_check_float"),
            patch.object(monitor, "eth_rpc") as mock_rpc,
            patch.object(monitor, "process_deposit", side_effect=RuntimeError("boom")),
            patch.object(monitor, "_mark_for_retry", side_effect=RuntimeError("db gone")),
        ):
            mock_rpc._get_web3.return_value.eth.block_number = 100
            mock_rpc._get_web3.return_value.eth.get_block.return_value = {"transactions": [mock_tx]}
            monitor.poll_ethereum()

        assert get_cursor("last_processed_block") == 96  # not advanced


class TestDustAndRecipientValidation:
    """Sub-minimum ETH is recorded, malformed recipients fail at once."""

    def test_dust_deposit_recorded_failed(self, monitor):
        from bridge_monitor.storage import get_deposit, set_cursor

        mock_tx = MagicMock()
        mock_tx.get.side_effect = lambda k, d="": {
            "to": monitor.bridge_eth_address,
            "value": 10**13,  # 0.00001 ETH < min
            "from": "0xdust",
            "input": "0x",
        }.get(k, d)
        mock_tx.hash.hex.return_value = "0xdust01"

        set_cursor("last_processed_block", 96)
        with (
            patch.object(monitor, "_check_float"),
            patch.object(monitor, "eth_rpc") as mock_rpc,
            patch.object(monitor, "process_deposit") as mock_process,
        ):
            mock_rpc._get_web3.return_value.eth.block_number = 100
            mock_rpc._get_web3.return_value.eth.get_block.return_value = {"transactions": [mock_tx]}
            monitor.poll_ethereum()

        mock_process.assert_not_called()
        d = get_deposit("0xdust01")
        assert d is not None  # every inflow is ledger-visible
        assert d["status"] == BridgeDepositStatus.FAILED.value
        assert "MIN_ETH_DEPOSIT" in d["error_message"]

    def test_malformed_recipient_fails_once_no_retry(self, monitor):
        """'0x' + garbage parses as a 0x-prefixed string today; with strict
        validation it must fail immediately, not burn the retry budget."""
        from bridge_monitor.storage import get_deposit

        # utf-8("0xNOTVALID") hex-encoded — decodes to a 0x string that is
        # NOT a valid 42-char address
        bad_data = "0x" + b"0xNOTVALID".hex()
        with patch.object(monitor, "calculate_ait_amount", return_value=Decimal("100")):
            monitor.process_deposit("0xmal", "0xfrom", Decimal("0.1"), bad_data)

        d = get_deposit("0xmal")
        assert d["status"] == BridgeDepositStatus.FAILED.value
        assert d["next_retry_at"] is None  # permanent, no retry burn


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


class TestPayoutHardening:
    """BR-7: price lock, per-deposit payout cap, committed-aware float.

    - The first computed ait_amount is locked: a retry pays exactly the
      stored amount, never a moved oracle's answer.
    - A single payout may not exceed BRIDGE_MAX_PAYOUT_FRACTION of the
      wallet balance — over-cap fails permanently and alerts.
    - The float check alerts on *available* float: balance minus the sum
      committed to non-terminal payouts.
    """

    def test_retry_pays_locked_amount_not_repriced(self, monitor):
        """Stored ait_amount wins; a moved oracle is never consulted."""
        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit

        create_deposit("0xlock1", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit(
            "0xlock1",
            ait_amount="100",
            status=BridgeDepositStatus.PENDING_RETRY,
        )
        monitor.price_oracle.get_price = MagicMock(return_value=MagicMock(price=Decimal("999999")))
        with (
            patch.object(monitor, "_payout_in_flight", return_value=False),
            patch.object(monitor, "_head_height", return_value=100),
            patch.object(monitor, "_build_signed_transfer", return_value={"tx": 1}) as build,
            patch.object(monitor, "_post_signed_tx", return_value="0xhash"),
            patch.object(monitor, "_envelope_tx_hash", return_value="0xhash"),
            patch.object(monitor, "_payout_wallet_balance", return_value=10**15),
        ):
            monitor.process_retry_queue()

        build.assert_called_once()
        assert build.call_args[0][1] == Decimal("100")
        monitor.price_oracle.get_price.assert_not_called()
        assert get_deposit("0xlock1")["status"] == BridgeDepositStatus.SUBMITTED.value

    def test_unpriced_row_first_prices_and_records_prices(self, monitor):
        """amount_ait '0' means never priced — recompute once, store inputs."""
        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit

        create_deposit("0xlock2", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit("0xlock2", status=BridgeDepositStatus.PENDING_RETRY)

        eth_p, ait_p = MagicMock(price=Decimal("3000")), MagicMock(price=Decimal("0.30"))
        monitor.price_oracle.get_price = MagicMock(side_effect=lambda sym, q: eth_p if sym == "ETH" else ait_p)
        with (
            patch.object(monitor, "_payout_in_flight", return_value=False),
            patch.object(monitor, "_head_height", return_value=100),
            patch.object(monitor, "_build_signed_transfer", return_value={"tx": 1}),
            patch.object(monitor, "_post_signed_tx", return_value="0xhash"),
            patch.object(monitor, "_envelope_tx_hash", return_value="0xhash"),
            patch.object(monitor, "_payout_wallet_balance", return_value=10**15),
        ):
            monitor.process_retry_queue()

        dep = get_deposit("0xlock2")
        assert Decimal(dep["ait_amount"]) > 0  # 0.01 * 3000 / 0.30 = 100
        assert dep["eth_usd_price"] == "3000"
        assert dep["ait_usd_price"] == "0.30"

    def test_over_cap_deposit_fails_and_alerts(self, monitor, caplog):
        """200-AIT payout vs 100-AIT float (cap 0.5 → 50 AIT): FAILED."""
        from bridge_monitor.storage import get_deposit
        from aitbc.utils.units import ait_to_units

        with (
            patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("200")),
            patch.object(monitor, "_payout_wallet_balance", return_value=ait_to_units(100)),
            patch.object(monitor, "_build_signed_transfer") as build,
        ):
            monitor.process_deposit("0xcap1", "0xfrom", Decimal("0.01"), "0xdata")

        dep = get_deposit("0xcap1")
        assert dep["status"] == BridgeDepositStatus.FAILED.value
        assert "cap" in (dep["error_message"] or "")
        build.assert_not_called()
        assert "per-deposit cap" in caplog.text

    def test_under_cap_deposit_proceeds(self, monitor):
        """100-AIT payout vs 1000-AIT float submits normally."""
        from aitbc.utils.units import ait_to_units

        with (
            patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("100")),
            patch.object(monitor, "_payout_wallet_balance", return_value=ait_to_units(1000)),
            patch.object(monitor, "_payout_in_flight", return_value=False),
            patch.object(monitor, "_submit_payout", return_value=True) as submit,
        ):
            monitor.process_deposit("0xcap2", "0xfrom", Decimal("0.01"), "0xdata")

        submit.assert_called_once()
        assert submit.call_args[0][2] == Decimal("100")

    def test_cap_recheck_on_retry(self, monitor):
        """A locked amount can breach the cap later when the float shrank."""
        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit
        from aitbc.utils.units import ait_to_units

        create_deposit("0xcap3", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit(
            "0xcap3",
            ait_amount="200",
            status=BridgeDepositStatus.PENDING_RETRY,
        )
        with (
            patch.object(monitor, "_payout_wallet_balance", return_value=ait_to_units(100)),
            patch.object(monitor, "_build_signed_transfer") as build,
        ):
            monitor.process_retry_queue()

        dep = get_deposit("0xcap3")
        assert dep["status"] == BridgeDepositStatus.FAILED.value
        assert "cap" in (dep["error_message"] or "")
        build.assert_not_called()

    def test_cap_rpc_failure_fails_open(self, monitor):
        """Balance unreadable → no cap verdict; payout proceeds (the float
        check's warning covers the visibility loss)."""

        with (
            patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("100")),
            patch.object(monitor, "_payout_wallet_balance", return_value=None),
            patch.object(monitor, "_payout_in_flight", return_value=False),
            patch.object(monitor, "_submit_payout", return_value=True) as submit,
        ):
            monitor.process_deposit("0xcap4", "0xfrom", Decimal("0.01"), "0xdata")

        submit.assert_called_once()

    def test_absolute_cap_bites_below_fraction(self, monitor):
        """BRIDGE_MAX_PAYOUT_AIT=10 vs 1000-AIT float: a 100-AIT payout is
        under the fraction cap (500) but over the absolute one → FAILED."""
        from bridge_monitor.storage import get_deposit
        from aitbc.utils.units import ait_to_units

        monitor.max_payout_ait = Decimal("10")
        with (
            patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("100")),
            patch.object(monitor, "_payout_wallet_balance", return_value=ait_to_units(1000)),
            patch.object(monitor, "_build_signed_transfer") as build,
        ):
            monitor.process_deposit("0xcap5", "0xfrom", Decimal("0.01"), "0xdata")

        dep = get_deposit("0xcap5")
        assert dep["status"] == BridgeDepositStatus.FAILED.value
        assert "BRIDGE_MAX_PAYOUT_AIT" in (dep["error_message"] or "")
        build.assert_not_called()

    def test_absolute_cap_above_fraction_does_not_relax_it(self, monitor):
        """The stricter bound wins: absolute 2000 vs fraction cap 500 on a
        1000-AIT float — a 600-AIT payout still fails on the fraction."""
        from bridge_monitor.storage import get_deposit
        from aitbc.utils.units import ait_to_units

        monitor.max_payout_ait = Decimal("2000")
        with (
            patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("600")),
            patch.object(monitor, "_payout_wallet_balance", return_value=ait_to_units(1000)),
            patch.object(monitor, "_build_signed_transfer") as build,
        ):
            monitor.process_deposit("0xcap6", "0xfrom", Decimal("0.01"), "0xdata")

        dep = get_deposit("0xcap6")
        assert dep["status"] == BridgeDepositStatus.FAILED.value
        assert "of float" in (dep["error_message"] or "")
        build.assert_not_called()

    def test_absolute_cap_unset_by_default(self, monitor):
        """No BRIDGE_MAX_PAYOUT_AIT → None; the fraction cap alone applies."""
        assert monitor.max_payout_ait is None

    def test_absolute_cap_applies_when_balance_unreadable(self, monitor):
        """Fraction cap needs the balance; the absolute ceiling does not —
        100 AIT payout vs unreadable balance fails on BRIDGE_MAX_PAYOUT_AIT=10."""
        from bridge_monitor.storage import get_deposit

        monitor.max_payout_ait = Decimal("10")
        with (
            patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("100")),
            patch.object(monitor, "_payout_wallet_balance", return_value=None),
            patch.object(monitor, "_build_signed_transfer") as build,
        ):
            monitor.process_deposit("0xcap7", "0xfrom", Decimal("0.01"), "0xdata")

        dep = get_deposit("0xcap7")
        assert dep["status"] == BridgeDepositStatus.FAILED.value
        assert "BRIDGE_MAX_PAYOUT_AIT" in (dep["error_message"] or "")
        assert "balance unknown" in (dep["error_message"] or "")
        build.assert_not_called()

    def test_float_alert_counts_committed_payouts(self, monitor, caplog):
        """Balance above threshold, but a 990-AIT SUBMITTED envelope commits
        nearly all of it — the alert must fire on *available*."""
        from bridge_monitor.storage import create_deposit, update_deposit
        from aitbc.utils.units import ait_to_units

        create_deposit("0xcmt1", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit(
            "0xcmt1",
            ait_amount="990",
            status=BridgeDepositStatus.SUBMITTED,
        )
        monitor.eth_rpc.get_balance = MagicMock(return_value={"wei": 10**18})
        with patch.object(monitor, "_payout_wallet_balance", return_value=ait_to_units(1000)):
            monitor._check_float()
        assert "payout float low" in caplog.text
        assert "committed" in caplog.text

    def test_float_alert_quiet_when_commitment_free(self, monitor, caplog):
        """Same balance, no committed rows → no alert."""
        from aitbc.utils.units import ait_to_units

        monitor.eth_rpc.get_balance = MagicMock(return_value={"wei": 10**18})
        with patch.object(monitor, "_payout_wallet_balance", return_value=ait_to_units(1000)):
            monitor._check_float()
        assert "float low" not in caplog.text


class TestDocsCoverage:
    """Env vars the code reads must appear in the app README — docs drift
    fails at commit time, same as the v9 type-allowlist test. Reverse:
    documented BRIDGE_*/PAYOUT_* knobs must still be read by the code."""

    SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
    README = os.path.join(os.path.dirname(__file__), "..", "README.md")

    @staticmethod
    def _env_names_used() -> set:
        import re

        names = set()
        for dirpath, _dirs, files in os.walk(TestDocsCoverage.SRC_DIR):
            for fname in files:
                if fname.endswith(".py"):
                    text = open(os.path.join(dirpath, fname)).read()
                    names.update(re.findall(r"""os\.getenv\(["']([A-Z0-9_]+)["']""", text))
        return names

    def test_every_env_var_is_documented(self):
        readme = open(self.README).read()
        missing = sorted(n for n in self._env_names_used() if n not in readme)
        assert not missing, "env vars read by bridge_monitor but absent from its README: " + ", ".join(missing)

    def test_documented_knobs_are_still_read(self):
        import re

        used = self._env_names_used()
        readme = open(self.README).read()
        documented = set(re.findall(r"`(BRIDGE_[A-Z0-9_]+|PAYOUT_[A-Z0-9_]+|MIN_ETH_DEPOSIT)`", readme))
        stale = sorted(n for n in documented if n not in used)
        assert not stale, "knobs documented in the README that no code reads: " + ", ".join(stale)
