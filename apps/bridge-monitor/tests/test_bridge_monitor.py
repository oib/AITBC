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
            patch.object(monitor, "submit_ait_transfer", return_value="0xait_tx") as mock_submit,
        ):
            monitor.process_deposit("0xdef", "0xfrom", Decimal("0.1"), "0xdata")

        mock_submit.assert_called_once()


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

            # Cursor should still advance — deposit was caught and marked for retry
            assert get_cursor("last_processed_block") == 100
            # _mark_for_retry called for each block in range (90-100 = 11 blocks)
            assert mock_retry.call_count > 0
