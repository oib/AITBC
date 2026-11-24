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

from aitbc.crypto.signature_recovery import canonical_address
from bridge_monitor.main import BridgeMonitor
from bridge_monitor.storage import BridgeDepositStatus


def _slot_row(envelope, tx_hash="0xslotother", **over):
    """A sealed chain tx row at the envelope's nonce that is NOT the
    envelope — the 'other' occupant that makes abandon safe (#1721)."""
    row = {
        "tx_hash": tx_hash,
        "nonce": envelope["nonce"],
        "block_height": 300,
        "status": "confirmed",
        "type": "TRANSFER",
        "sender": "0x" + "b" * 40,
        "recipient": "0x" + "e" * 40,  # different recipient → not ours
        "value": 999,
        "fee": 360000,
        "payload": {"amount": 999},
    }
    row.update(over)
    return row


def _ours_row(envelope, tx_hash="0x" + "9" * 64, **over):
    """A sealed chain tx row that IS the envelope — landed under the hash
    the chain assigned, which the ledger's stale ait_tx_hash never saw."""
    row = {
        "tx_hash": tx_hash,
        "nonce": envelope["nonce"],
        "block_height": 300,
        "status": "confirmed",
        "type": envelope.get("type", "TRANSFER"),
        "sender": envelope.get("from"),
        "recipient": envelope.get("to"),
        "value": envelope.get("amount"),
        "fee": envelope.get("fee"),
        "payload": envelope.get("payload") or {},
    }
    row.update(over)
    return row


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

    def test_held_cursor_rescan_does_not_burn_retry_budget(self, monitor, tmp_path):
        """#2821: a PENDING_RETRY row rescanned while the block cursor is held
        must not consume retry budget — _mark_for_retry's increment plus a
        pushed-out next_retry_at would FAILED a funds-owed deposit after
        ~5 polls without it ever being retried."""
        from datetime import UTC, datetime, timedelta

        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit

        next_retry = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        create_deposit("0xheld", "0xfrom", "1.0", "0x" + "a" * 40)
        update_deposit(
            "0xheld",
            status=BridgeDepositStatus.PENDING_RETRY,
            ait_amount="100",
            retry_count=4,
            next_retry_at=next_retry,
        )

        for _ in range(6):
            monitor.process_deposit("0xheld", "0xfrom", Decimal("1.0"), "0xdata")

        deposit = get_deposit("0xheld")
        assert deposit is not None
        assert deposit["status"] == BridgeDepositStatus.PENDING_RETRY.value
        assert deposit["retry_count"] == 4
        assert deposit["next_retry_at"] == next_retry

    def test_processing_rescan_preserves_retry_count(self, monitor, tmp_path):
        """#2821: crash-recovery requeue keeps the existing retry_count —
        scan recovery is not a retry attempt."""
        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit

        create_deposit("0xproc", "0xfrom", "1.0", "0x" + "b" * 40)
        update_deposit(
            "0xproc",
            status=BridgeDepositStatus.PROCESSING,
            ait_amount="100",
            retry_count=2,
        )

        monitor.process_deposit("0xproc", "0xfrom", Decimal("1.0"), "0xdata")

        deposit = get_deposit("0xproc")
        assert deposit is not None
        assert deposit["status"] == BridgeDepositStatus.PENDING_RETRY.value
        assert deposit["retry_count"] == 2


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

    def test_rebroadcast_adopts_rpc_hash(self, monitor, tmp_path):
        """#1721: a rebroadcast must correct ait_tx_hash to the hash the chain
        reported — the client-derived envelope hash never resolves on-chain,
        so leaving it stale breaks the seal probe and the abandon proof."""
        from bridge_monitor.storage import get_deposit

        self._submitted_row(monitor)
        server_hash = "0x" + "9" * 64
        with (
            patch.object(monitor, "_head_height", return_value=100),
            patch.object(monitor, "_account_nonce", return_value=7),  # nonce not passed → no abandon
            patch.object(monitor, "_post_signed_tx", return_value=server_hash),
            patch("httpx.get") as mock_get,
        ):
            mock_get.return_value = MagicMock(status_code=404)
            monitor.process_submitted_deposits()

        d = get_deposit("0xsub")
        assert d["status"] == BridgeDepositStatus.SUBMITTED.value
        assert d["ait_tx_hash"] == server_hash  # adopted the chain's hash
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

    def test_write_off_guard_live_envelope(self):
        """#1595: SUBMITTED + live signed_tx needs the --envelope-dead attestation."""
        from bridge_monitor.admin import write_off_denial_reason

        live = {"status": "submitted", "signed_tx": '{"nonce": 7}', "ait_recipient": ""}
        assert write_off_denial_reason(live, False) is not None  # may still seal → refused
        assert write_off_denial_reason(live, False, True) is None  # attested dead → allowed
        dead = {"status": "submitted", "signed_tx": "", "ait_recipient": ""}
        assert write_off_denial_reason(dead, False) is None  # no envelope → writable
        retry = {"status": "pending_retry", "signed_tx": '{"nonce": 7}', "ait_recipient": ""}
        assert write_off_denial_reason(retry, False) is None  # not SUBMITTED → writable

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
        envelope, _ = self._submitted_for_abandon(monitor)
        with (
            patch.object(monitor, "_account_nonce", return_value=9),  # nonce 9 > envelope nonce 7
            patch.object(monitor, "_tx_on_chain", return_value=False),
            patch.object(monitor, "_payout_account_txs", return_value=[_slot_row(envelope)]),
        ):
            ok, msg = monitor.abandon_payout("0xabn")
        assert ok
        from bridge_monitor.storage import get_deposit

        d = get_deposit("0xabn")
        assert d["status"] == BridgeDepositStatus.PENDING_RETRY.value
        # envelope fields cleared so no path hands the dead envelope back
        assert not d["signed_tx"] and not d["envelope_hash"] and not d["ait_tx_hash"]

    def test_abandon_refuses_when_envelope_landed_under_unknown_hash(self, monitor):
        """#1721 invariant: SUBMITTED row whose ait_tx_hash is the stale
        client-derived hash while the envelope sealed under the chain's own
        hash must NOT be abandonable — and the proof must heal the hash."""
        envelope, _ = self._submitted_for_abandon(monitor)
        landed = _ours_row(envelope)
        with (
            patch.object(monitor, "_account_nonce", return_value=9),  # nonce passed 7
            patch.object(monitor, "_tx_on_chain", return_value=False),  # stale hash 404s forever
            patch.object(monitor, "_payout_account_txs", return_value=[landed]),
        ):
            ok, msg = monitor.abandon_payout("0xabn")
        assert not ok
        assert "on chain" in msg
        from bridge_monitor.storage import get_deposit

        d = get_deposit("0xabn")
        assert d["status"] == BridgeDepositStatus.SUBMITTED.value  # NOT re-queued
        assert d["ait_tx_hash"] == landed["tx_hash"]  # adopted the real hash
        assert d["signed_tx"]  # envelope retained — the sweep owns it now

    def test_abandon_refuses_when_slot_occupant_unproven(self, monitor):
        """Nonce passed + hashes 404 but the account tx query is unavailable
        → fail closed: no proof the slot holds a different tx."""
        self._submitted_for_abandon(monitor)
        with (
            patch.object(monitor, "_account_nonce", return_value=9),
            patch.object(monitor, "_tx_on_chain", return_value=False),
            patch.object(monitor, "_payout_account_txs", return_value=None),
        ):
            ok, msg = monitor.abandon_payout("0xabn")
        assert not ok
        assert "nonce slot" in msg
        from bridge_monitor.storage import get_deposit

        assert get_deposit("0xabn")["status"] == BridgeDepositStatus.SUBMITTED.value

    def test_abandon_refuses_when_no_confirmed_slot_tx(self, monitor):
        """Nonce passed but no CONFIRMED tx sits at the envelope's nonce —
        the slot occupant is unproven (only a sealed-failed foreign row, or
        nothing at all) → fail closed."""
        envelope, _ = self._submitted_for_abandon(monitor)
        failed_only = _slot_row(envelope, status="failed")
        with (
            patch.object(monitor, "_account_nonce", return_value=9),
            patch.object(monitor, "_tx_on_chain", return_value=False),
            patch.object(monitor, "_payout_account_txs", return_value=[failed_only]),
        ):
            ok, _ = monitor.abandon_payout("0xabn")
        assert not ok
        from bridge_monitor.storage import get_deposit

        assert get_deposit("0xabn")["status"] == BridgeDepositStatus.SUBMITTED.value

    def test_abandon_allows_sealed_failed_envelope(self, monitor):
        """#2830: our envelope sealed-FAILED at its nonce slot — the apply
        verdict moved no value and the nonce is spent, so the row is dead
        by revert and safe to re-sign. Confirmed 'ours' still refuses."""
        envelope, _ = self._submitted_for_abandon(monitor)
        landed = _ours_row(envelope, status="failed")
        with (
            patch.object(monitor, "_account_nonce", return_value=9),
            patch.object(monitor, "_tx_on_chain", return_value=False),
            patch.object(monitor, "_payout_account_txs", return_value=[landed]),
        ):
            ok, msg = monitor.abandon_payout("0xabn")
        assert ok, msg
        from bridge_monitor.storage import get_deposit

        assert get_deposit("0xabn")["status"] == BridgeDepositStatus.PENDING_RETRY.value

    def test_abandon_refuses_sealed_failed_hash_when_verdict_unproven(self, monitor):
        """A held hash spelling sealed-failed but the nonce-slot occupant
        cannot be proven → still fails closed."""
        self._submitted_for_abandon(monitor)
        with (
            patch.object(monitor, "_account_nonce", return_value=9),
            patch.object(monitor, "_tx_on_chain", return_value=True),
            patch.object(monitor, "_probe_payout_status", return_value=(500, True)),
            patch.object(monitor, "_payout_account_txs", return_value=None),
        ):
            ok, msg = monitor.abandon_payout("0xabn")
        assert not ok
        assert "nonce slot" in msg

    def test_triage_falls_through_to_abandon_on_sealed_failed(self, monitor):
        """#2830: the sweep's sealed-failed early return used to skip the
        abandon proof entirely — the exact rows it exists for."""
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
        create_deposit("0xsf1", "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            "0xsf1",
            ait_amount="1",
            signed_tx=_json.dumps(envelope),
            envelope_hash="0xenv",
            ait_tx_hash="0xpayout",
            status=BridgeDepositStatus.SUBMITTED,
        )
        d = {"eth_tx_hash": "0xsf1", "ait_tx_hash": "0xpayout", "signed_tx": _json.dumps(envelope)}
        with (
            patch.object(monitor, "_probe_payout_status", return_value=(500, True)),
            patch.object(monitor, "abandon_payout", return_value=(True, "abandoned")) as abandon,
        ):
            assert monitor._triage_submitted_deposit(d, 600) is True
        abandon.assert_called_once_with("0xsf1")

    def test_triage_sealed_failed_unproven_stays_submitted(self, monitor):
        """Proof refuses → the row stays SUBMITTED+alerted, not rebroadcast."""
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
        create_deposit("0xsf2", "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            "0xsf2",
            ait_amount="1",
            signed_tx=_json.dumps(envelope),
            envelope_hash="0xenv",
            ait_tx_hash="0xpayout",
            status=BridgeDepositStatus.SUBMITTED,
        )
        d = {"eth_tx_hash": "0xsf2", "ait_tx_hash": "0xpayout", "signed_tx": _json.dumps(envelope)}
        with (
            patch.object(monitor, "_probe_payout_status", return_value=(500, True)),
            patch.object(monitor, "abandon_payout", return_value=(False, "cannot prove")),
        ):
            assert monitor._triage_submitted_deposit(d, 600) is True  # resolved: no rebroadcast churn


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
        # #1706: the persistent condition alerts once per throttle interval,
        # not once per failed poll — streaks 3 and 4 share one alert.
        assert len(alerts) == 1
        assert "3 consecutive" in alerts[0].message

    def test_poll_failure_alert_throttled_then_realerts_after_recovery(self, monitor, caplog):
        """#1706: a still-failing streak does not re-alert inside the
        interval; a recovered-then-failed-again streak alerts immediately."""
        import logging

        with (
            patch.object(monitor, "_check_float"),
            patch.object(monitor, "eth_rpc") as mock_rpc,
            caplog.at_level(logging.CRITICAL),
        ):
            mock_rpc._get_web3.side_effect = RuntimeError("endpoint down")
            for _ in range(3):
                monitor.poll_ethereum()
            first = [r for r in caplog.records if "ALERT" in r.message]
            assert len(first) == 1

            # Streak keeps growing inside the throttle window — no new ALERT.
            monitor.poll_ethereum()
            assert len([r for r in caplog.records if "ALERT" in r.message]) == 1

            # RPC recovers: streak resets and the throttle key clears.
            mock_rpc._get_web3.side_effect = None
            mock_rpc._get_web3.return_value.eth.block_number = 100
            mock_rpc._get_web3.return_value.eth.get_block.return_value = {"transactions": []}
            monitor.poll_ethereum()
            assert monitor._poll_fail_streak == 0

            # A fresh outage alerts again on the third failure.
            mock_rpc._get_web3.side_effect = RuntimeError("endpoint down again")
            caplog.clear()
            for _ in range(3):
                monitor.poll_ethereum()
            alerts = [r for r in caplog.records if "ALERT" in r.message]
            assert len(alerts) == 1
            assert "3 consecutive" in alerts[0].message

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
            patch.object(monitor, "_payout_account_txs", return_value=[_slot_row(envelope)]),
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
            patch.object(monitor, "_payout_account_txs", return_value=[_slot_row(envelope)]),
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
      *available* float — balance minus committed unsealed/queued payouts
      and one fee — over-cap fails permanently and alerts (#2828).
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
        assert "available float" in (dep["error_message"] or "")
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

    def test_committed_payouts_shrink_the_cap(self, monitor):
        """#2828: a 60-AIT SUBMITTED envelope commits most of a 100-AIT float;
        a 30-AIT deposit that fit the raw-balance cap (50) must fail against
        the available float (~40 minus fee → cap ~20)."""
        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit
        from aitbc.utils.units import ait_to_units

        create_deposit("0xcommitted1", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit(
            "0xcommitted1",
            ait_amount="60",
            status=BridgeDepositStatus.SUBMITTED,
        )
        with (
            patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("30")),
            patch.object(monitor, "_payout_wallet_balance", return_value=ait_to_units(100)),
            patch.object(monitor, "_build_signed_transfer") as build,
        ):
            monitor.process_deposit("0xcap8", "0xfrom", Decimal("0.01"), "0xdata")

        dep = get_deposit("0xcap8")
        assert dep["status"] == BridgeDepositStatus.FAILED.value
        assert "committed" in (dep["error_message"] or "")
        build.assert_not_called()

    def test_retry_cap_excludes_its_own_row(self, monitor):
        """#2828: the retried row is itself non-terminal — its amount_ait is
        already inside sum_committed_ait; excluding it keeps a 40-AIT retry
        under the ~50-AIT cap on a 100-AIT float instead of double-counting."""
        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit
        from aitbc.utils.units import ait_to_units

        create_deposit("0xselfcap", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit(
            "0xselfcap",
            ait_amount="40",
            status=BridgeDepositStatus.PENDING_RETRY,
        )
        with (
            patch.object(monitor, "_payout_in_flight", return_value=False),
            patch.object(monitor, "_head_height", return_value=100),
            patch.object(monitor, "_build_signed_transfer", return_value={"tx": 1}),
            patch.object(monitor, "_post_signed_tx", return_value="0xhash"),
            patch.object(monitor, "_envelope_tx_hash", return_value="0xhash"),
            patch.object(monitor, "_payout_wallet_balance", return_value=ait_to_units(100)),
        ):
            monitor.process_retry_queue()

        assert get_deposit("0xselfcap")["status"] == BridgeDepositStatus.SUBMITTED.value

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


class TestCommittedVocabulary2829:
    """#2829: sum_committed_ait counts only exposure to the payout account —
    the monitor pipeline (processing/pending_retry/submitted) always; the
    wallet-side 'pending'/'verified' mint vocabulary only when the wallet's
    GENESIS mint account IS the payout account (shared keys)."""

    @staticmethod
    def _set_status(tx_hash: str, status: str) -> None:
        """Direct-SQL status write — 'verified' is wallet vocabulary the
        monitor's update_deposit refuses by design."""
        import sqlite3

        from bridge_monitor.storage import DB_PATH

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("UPDATE eth_deposits SET status = ? WHERE tx_hash = ?", (status, tx_hash))

    def test_status_sets(self, monitor):
        from bridge_monitor.storage import create_deposit, sum_committed_ait, update_deposit

        create_deposit("0xwv1", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit("0xwv1", ait_amount="10")  # lingers 'pending' — wallet-side
        create_deposit("0xwv2", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit("0xwv2", ait_amount="20")
        self._set_status("0xwv2", "verified")
        create_deposit("0xwv3", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit("0xwv3", ait_amount="30", status=BridgeDepositStatus.SUBMITTED)
        create_deposit("0xwv4", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit("0xwv4", ait_amount="40", status=BridgeDepositStatus.PENDING_RETRY)
        # foreign-account deployment: only the monitor pipeline commits
        assert sum_committed_ait() == Decimal("70")
        # shared keys: wallet pending + verified-in-flight commit too
        assert sum_committed_ait(shared_mint_account=True) == Decimal("100")

    def test_foreign_pending_row_does_not_commit(self, monitor):
        """Payout account != wallet mint account: a 60-AIT wallet-side
        'pending' row is foreign exposure — a 30-AIT deposit still fits the
        ~50-AIT cap on a 100-AIT float and submits."""
        from bridge_monitor.storage import create_deposit, update_deposit
        from aitbc.utils.units import ait_to_units

        monitor.shared_mint_account = False
        create_deposit("0xwfp1", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit("0xwfp1", ait_amount="60")  # stays 'pending'
        with (
            patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("30")),
            patch.object(monitor, "_payout_wallet_balance", return_value=ait_to_units(100)),
            patch.object(monitor, "_payout_in_flight", return_value=False),
            patch.object(monitor, "_submit_payout", return_value=True) as submit,
        ):
            monitor.process_deposit("0xwnew1", "0xfrom", Decimal("0.01"), "0xdata")
        submit.assert_called_once()

    def test_shared_pending_and_verified_rows_commit(self, monitor):
        """Shared keys: wallet 'pending' + 'verified' rows debit the same
        float — 60 AIT committed on a 100-AIT float leaves a ~20-AIT cap, so
        the 30-AIT deposit fails permanently like any over-cap payout."""
        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit
        from aitbc.utils.units import ait_to_units

        monitor.shared_mint_account = True
        create_deposit("0xwsh1", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit("0xwsh1", ait_amount="40")  # 'pending'
        create_deposit("0xwsh2", "0xfrom", "0.01", "0x" + "d" * 40)
        update_deposit("0xwsh2", ait_amount="20")
        self._set_status("0xwsh2", "verified")
        with (
            patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("30")),
            patch.object(monitor, "_payout_wallet_balance", return_value=ait_to_units(100)),
            patch.object(monitor, "_build_signed_transfer") as build,
        ):
            monitor.process_deposit("0xwnew2", "0xfrom", Decimal("0.01"), "0xdata")
        assert get_deposit("0xwnew2")["status"] == BridgeDepositStatus.FAILED.value
        build.assert_not_called()

    def test_shared_mint_account_derives_from_env(self, tmp_path, monkeypatch):
        """shared = (wallet mint account == payout account): BRIDGE_PAYOUT_*
        unset falls back to GENESIS_WALLET_ADDRESS → shared; a distinct
        BRIDGE_PAYOUT_ADDRESS → foreign; case-insensitive compare."""
        from bridge_monitor.main import BridgeMonitor

        def make_monitor(**env):
            monkeypatch.setattr("bridge_monitor.storage.DATA_DIR", str(tmp_path))
            monkeypatch.setattr("bridge_monitor.storage.DB_PATH", str(tmp_path / "bridge_deposits.db"))
            monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "0x" + "a" * 40)
            monkeypatch.setenv("GENESIS_WALLET_ADDRESS", "0x" + "b" * 40)
            monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", "0x" + "c" * 64)
            for key, value in env.items():
                monkeypatch.setenv(key, value)
            with patch("bridge_monitor.main.EthereumRPCClient"), patch("bridge_monitor.main.get_price_oracle"):
                return BridgeMonitor()

        monkeypatch.delenv("BRIDGE_PAYOUT_ADDRESS", raising=False)
        assert make_monitor().shared_mint_account is True  # payout falls back to genesis
        monkeypatch.setenv("BRIDGE_PAYOUT_ADDRESS", "0x" + "d" * 40)
        assert make_monitor().shared_mint_account is False
        monkeypatch.setenv("BRIDGE_PAYOUT_ADDRESS", "0x" + "B" * 40)  # same, other case
        assert make_monitor().shared_mint_account is True


class TestPayoutAccountPublish2831:
    """#2831: init publishes the payout account into the shared
    bridge_monitor_state so the wallet-side auto-mint can detect a shared
    nonce space and refuse to race this service's envelopes."""

    def test_init_publishes_payout_account(self, monitor):
        from bridge_monitor.storage import get_monitor_state

        # Fixture: BRIDGE_PAYOUT_ADDRESS unset → payout falls back to
        # GENESIS_WALLET_ADDRESS = 0x + "b"*40.
        assert get_monitor_state("payout_account") == "0x" + "b" * 40

    def test_distinct_payout_address_published(self, tmp_path, monkeypatch):
        from bridge_monitor.main import BridgeMonitor
        from bridge_monitor.storage import get_monitor_state

        monkeypatch.setattr("bridge_monitor.storage.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("bridge_monitor.storage.DB_PATH", str(tmp_path / "bridge_deposits.db"))
        monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "0x" + "a" * 40)
        monkeypatch.setenv("GENESIS_WALLET_ADDRESS", "0x" + "b" * 40)
        monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", "0x" + "c" * 64)
        monkeypatch.setenv("BRIDGE_PAYOUT_ADDRESS", "0x" + "D" * 40)
        with patch("bridge_monitor.main.EthereumRPCClient"), patch("bridge_monitor.main.get_price_oracle"):
            BridgeMonitor()

        assert get_monitor_state("payout_account") == "0x" + "d" * 40


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


class TestExchangePrepay:
    """ETH-8 phase 3: an EXCHANGE_DEPOSIT:<addr> tag routes to the prepaid
    exchange ledger — never the AIT mint path — under
    EXCHANGE_SETTLEMENT_ENABLED only."""

    @staticmethod
    def _tagged_input(addr_text: str) -> str:
        return "0x" + f"EXCHANGE_DEPOSIT:{addr_text}".encode().hex()

    def test_tagged_deposit_records_prepay(self, monitor, monkeypatch):
        from bridge_monitor.storage import get_deposit

        monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "true")
        with patch.object(monitor, "submit_ait_transfer") as mock_submit:
            monitor.process_deposit("0xtag1", "0xfrom", Decimal("0.01"), self._tagged_input("0xN0DE"))
        dep = get_deposit("0xtag1")
        assert dep is not None
        assert dep["status"] == BridgeDepositStatus.EXCHANGE_PREPAY.value
        # The raw tag text stays on the row — the settlement monitor
        # canonicalizes and validates it.
        assert dep["ait_recipient"] == "EXCHANGE_DEPOSIT:0xN0DE"
        assert Decimal(str(dep["ait_amount"])) == Decimal("0")
        mock_submit.assert_not_called()

    def test_flag_off_tagged_deposit_fails_as_before(self, monitor, monkeypatch):
        from bridge_monitor.storage import get_deposit

        monkeypatch.delenv("EXCHANGE_SETTLEMENT_ENABLED", raising=False)
        monitor.process_deposit("0xtag2", "0xfrom", Decimal("0.01"), self._tagged_input("0xN0DE"))
        dep = get_deposit("0xtag2")
        assert dep["status"] == BridgeDepositStatus.FAILED.value
        assert "Invalid AIT recipient" in (dep["error_message"] or "")

    def test_reseen_prepay_row_is_terminal(self, monitor, monkeypatch):
        """A second sighting of the same tx must not take the retry path —
        the prepay row is terminal for the payout lane."""
        from bridge_monitor.storage import get_deposit

        monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "true")
        tx_data = self._tagged_input("0xN0DE")
        monitor.process_deposit("0xtag3", "0xfrom", Decimal("0.01"), tx_data)
        monitor.process_deposit("0xtag3", "0xfrom", Decimal("0.01"), tx_data)
        dep = get_deposit("0xtag3")
        assert dep["status"] == BridgeDepositStatus.EXCHANGE_PREPAY.value

    def test_tag_parser(self, monitor):
        parse = monitor._parse_exchange_deposit_tag
        assert parse(self._tagged_input("0xAbC")) == "0xAbC"
        assert parse(self._tagged_input("")) is None  # bare tag — no address
        assert parse("0x") is None
        assert parse(None) is None
        # An ordinary AIT-address data field is not a tag.
        assert parse("0x" + ("aa" * 20)) is None
        # A raw address as utf-8 text is not a tag either.
        assert parse("0x" + ("0x" + "aa" * 20).encode().hex()) is None


class TestOutboundLedger:
    """B13/BR-6: bridge_outbound table, record_outbound, scan-side writer."""

    BRIDGE = "0x" + "a" * 40
    DEPOSITOR = "0x" + "d" * 40
    FUNDING = "0x" + "f" * 40

    def _tx(self, tx_hash: str, to: str, value_wei: int):
        tx = MagicMock()
        tx.hash = MagicMock()
        tx.hash.hex.return_value = tx_hash
        tx.get = lambda k, d=None: {"to": to, "value": value_wei}.get(k, d)
        return tx

    def _w3(self, gas_used=21000, gas_price=10**9, status=1):
        w3 = MagicMock()
        receipt = MagicMock()
        receipt.__getitem__ = lambda self, k: {"gasUsed": gas_used, "effectiveGasPrice": gas_price}[k]
        receipt.get = lambda k, d=None: {"status": status}.get(k, d)
        receipt["gasUsed"] = gas_used
        receipt["effectiveGasPrice"] = gas_price
        receipt["status"] = status
        w3.eth.get_transaction_receipt.return_value = receipt
        return w3

    def _outbound_rows(self):
        import sqlite3
        from bridge_monitor import storage

        with sqlite3.connect(storage.DB_PATH) as con:
            return con.execute(
                "SELECT tx_hash, to_address, value_eth, gas_wei, kind, matched_deposit_tx, note "
                "FROM bridge_outbound ORDER BY tx_hash"
            ).fetchall()

    def test_table_created_by_init_db(self, monitor):
        from bridge_monitor.storage import outbound_totals_wei

        # Fixture already ran init_db; totals on the empty table must not raise.
        assert outbound_totals_wei() == {"refund": 0, "withdrawal": 0, "unidentified": 0, "gas_wei": 0}

    def test_record_outbound_dedupes_on_tx_hash(self, monitor):
        from bridge_monitor.storage import record_outbound

        assert record_outbound("0xout1", "0xdest", 10**18, 100, "unidentified", gas_wei=21000) is True
        assert record_outbound("0xout1", "0xdest", 10**18, 100, "unidentified") is False
        rows = self._outbound_rows()
        assert len(rows) == 1
        assert float(rows[0][2]) == 1.0 and rows[0][3] == 21000

    def test_refund_classifies_with_matched_deposit(self, monitor):
        from bridge_monitor.storage import create_deposit, record_outbound  # noqa: F401

        create_deposit("0xdep1", self.DEPOSITOR, "0.5", "0x" + "b" * 40, deposit_address=self.BRIDGE)
        monitor.funding_sources = set()
        monitor._record_outbound(self._w3(), self._tx("0xout_ref", self.DEPOSITOR, 10**17), 55)
        rows = self._outbound_rows()
        assert rows[0][4] == "refund" and rows[0][5] == "0xdep1"
        assert rows[0][3] == 21000 * 10**9

    def test_funding_return_and_release_leg_are_withdrawal(self, monitor, tmp_path):
        import sqlite3
        from bridge_monitor import storage

        monitor.funding_sources = {self.FUNDING.lower()}
        # A release-leg row in eth_withdrawals (wallet-side table, same file).
        with sqlite3.connect(storage.DB_PATH) as con:
            con.execute("CREATE TABLE IF NOT EXISTS eth_withdrawals (id TEXT PRIMARY KEY, eth_tx_hash TEXT)")
            con.execute("INSERT INTO eth_withdrawals VALUES ('w1', '0xout_rel')")
        monitor._record_outbound(self._w3(), self._tx("0xout_rel", "0x" + "e" * 40, 5 * 10**17), 56)
        monitor._record_outbound(self._w3(), self._tx("0xout_fund", self.FUNDING, 10**17), 57)
        rows = {r[0]: r for r in self._outbound_rows()}
        assert rows["0xout_rel"][4] == "withdrawal"
        assert rows["0xout_fund"][4] == "withdrawal"

    def test_self_send_and_unidentified(self, monitor):
        monitor.funding_sources = set()
        monitor._record_outbound(self._w3(), self._tx("0xout_self", self.BRIDGE, 10**18), 58)
        monitor._record_outbound(self._w3(), self._tx("0xout_unk", "0x" + "9" * 40, 10**17), 59)
        rows = {r[0]: r for r in self._outbound_rows()}
        assert rows["0xout_self"][4] == "self_send"
        assert rows["0xout_unk"][4] == "unidentified"

    def test_failed_send_records_gas_only_note(self, monitor):
        monitor.funding_sources = set()
        monitor._record_outbound(self._w3(status=0), self._tx("0xout_fail", "0x" + "9" * 40, 10**17), 60)
        row = self._outbound_rows()[0]
        assert row[4] == "unidentified" and "failed" in (row[6] or "")
        assert float(row[2]) == 0.0  # reverted send: gas only, no value moved
        assert row[3] == 21000 * 10**9

    def test_totals_exclude_self_send_value(self, monitor):
        from bridge_monitor.storage import outbound_totals_wei, record_outbound

        record_outbound("0xr1", "0xd1", 10**17, 1, "refund", gas_wei=1000)
        record_outbound("0xw1", "0xf1", 2 * 10**17, 2, "withdrawal", gas_wei=2000)
        record_outbound("0xs1", self.BRIDGE, 10**18, 3, "self_send", gas_wei=500)
        terms = outbound_totals_wei()
        assert terms["refund"] == 10**17
        assert terms["withdrawal"] == 2 * 10**17
        assert terms["self_send"] if "self_send" in terms else True
        assert terms["gas_wei"] == 3500

    def _create_release_table(self, name: str, hashes: list[str | None]) -> None:
        import sqlite3
        from bridge_monitor import storage

        with sqlite3.connect(storage.DB_PATH) as con:
            con.execute(f"CREATE TABLE IF NOT EXISTS {name} (id TEXT, eth_tx_hash TEXT)")
            for i, h in enumerate(hashes):
                con.execute(f"INSERT INTO {name} VALUES ('r{i}', ?)", (h,))

    def test_sell_lock_release_is_withdrawal_with_note(self, monitor):
        monitor.funding_sources = set()
        self._create_release_table("bridge_sell_locks", ["0xout_sell", None])
        monitor._record_outbound(self._w3(), self._tx("0xout_sell", "0x" + "e" * 40, 5 * 10**17), 61)
        row = self._outbound_rows()[0]
        assert row[4] == "withdrawal" and "bridge_sell_locks release" in (row[6] or "")

    def test_settlement_release_is_withdrawal_with_note(self, monitor):
        monitor.funding_sources = set()
        self._create_release_table("exchange_settlements", ["0xout_settle"])
        monitor._record_outbound(self._w3(), self._tx("0xout_settle", "0x" + "e" * 40, 5 * 10**17), 62)
        row = self._outbound_rows()[0]
        assert row[4] == "withdrawal" and "exchange_settlements release" in (row[6] or "")

    def test_withdrawal_from_eth_withdrawals_has_no_source_note(self, monitor):
        monitor.funding_sources = set()
        self._create_release_table("eth_withdrawals", ["0xout_w"])
        monitor._record_outbound(self._w3(), self._tx("0xout_w", "0x" + "e" * 40, 5 * 10**17), 63)
        row = self._outbound_rows()[0]
        assert row[4] == "withdrawal" and not row[6]

    def test_missing_release_tables_do_not_break_classification(self, monitor):
        # Fixture DB has none of the three tables — classification must still work.
        monitor.funding_sources = set()
        monitor._record_outbound(self._w3(), self._tx("0xout_x", "0x" + "9" * 40, 10**17), 64)
        assert self._outbound_rows()[0][4] == "unidentified"

    def test_failed_send_keeps_both_notes(self, monitor):
        monitor.funding_sources = set()
        self._create_release_table("exchange_settlements", ["0xout_fail2"])
        monitor._record_outbound(self._w3(status=0), self._tx("0xout_fail2", "0x" + "e" * 40, 5 * 10**17), 65)
        row = self._outbound_rows()[0]
        assert row[4] == "withdrawal"
        assert "failed" in row[6] and "exchange_settlements release" in row[6]
        assert float(row[2]) == 0.0


class TestPostedHashAdoption:
    """BRIDGE-MONITOR-1: the seal probe and the abandon proof key on
    ait_tx_hash. When the RPC reports a hash differing from the derived
    envelope hash, the retry path must adopt the chain-reported hash —
    otherwise the row polls a hash that can never seal and stays
    SUBMITTED forever (the C2/P8 status lag)."""

    def _due_retry_row(self, tx_hash="0xretry1"):
        from bridge_monitor.storage import create_deposit, update_deposit

        create_deposit(tx_hash, "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            tx_hash,
            ait_amount="100",
            status=BridgeDepositStatus.PENDING_RETRY,
            next_retry_at="2000-01-01T00:00:00+00:00",
        )

    def test_retry_adopts_chain_reported_hash(self, monitor):
        from bridge_monitor.storage import get_deposit

        self._due_retry_row()
        envelope = {"type": "TRANSFER", "nonce": 3, "to": "0x" + "d" * 40}
        with (
            patch.object(monitor, "_build_signed_transfer", return_value=envelope),
            patch.object(monitor, "_post_signed_tx", return_value="0xchain_hash"),
            patch.object(monitor, "_head_height", return_value=100),
        ):
            monitor.process_retry_queue()

        d = get_deposit("0xretry1")
        assert d["status"] == BridgeDepositStatus.SUBMITTED.value
        assert d["ait_tx_hash"] == "0xchain_hash"  # chain-reported, not derived
        assert d["envelope_hash"] == monitor._envelope_tx_hash(envelope)

    def test_retry_same_hash_left_unchanged(self, monitor):
        from bridge_monitor.storage import get_deposit

        self._due_retry_row()
        envelope = {"type": "TRANSFER", "nonce": 3, "to": "0x" + "d" * 40}
        derived = monitor._envelope_tx_hash(envelope)
        with (
            patch.object(monitor, "_build_signed_transfer", return_value=envelope),
            patch.object(monitor, "_post_signed_tx", return_value=derived),
            patch.object(monitor, "_head_height", return_value=100),
        ):
            monitor.process_retry_queue()

        assert get_deposit("0xretry1")["ait_tx_hash"] == derived

    def test_adopted_hash_is_what_the_seal_probe_uses(self, monitor):
        """End-to-end: adopted hash seals → the row completes."""
        from bridge_monitor.storage import get_deposit

        self._due_retry_row()
        envelope = {"type": "TRANSFER", "nonce": 3, "to": "0x" + "d" * 40}
        with (
            patch.object(monitor, "_build_signed_transfer", return_value=envelope),
            patch.object(monitor, "_post_signed_tx", return_value="0xchain_hash"),
            patch.object(monitor, "_head_height", return_value=100),
        ):
            monitor.process_retry_queue()

        resp = MagicMock(status_code=200)
        resp.json.return_value = {"block_height": 97, "status": "confirmed"}
        with (
            patch.object(monitor, "_head_height", return_value=100),
            patch("httpx.get", return_value=resp) as mock_get,
        ):
            monitor.process_submitted_deposits()

        # The seal probe must have queried the chain-reported hash, and the
        # row must have completed — the exact flip the old code missed.
        assert any("0xchain_hash" in str(c) for c in mock_get.call_args_list)
        assert get_deposit("0xretry1")["status"] == BridgeDepositStatus.COMPLETED.value


class TestPollWatchdog:
    """BRIDGE-MONITOR-1 idle-miss watchdogs: a frozen head and an
    over-running scan must be loud, not silent."""

    def test_stale_eth_head_alerts(self, monitor, caplog):
        import logging

        monitor.head_stall_seconds = 0  # alert on the first repeated head
        with (
            patch.object(monitor, "_check_float"),
            patch.object(monitor, "eth_rpc") as mock_rpc,
            caplog.at_level(logging.CRITICAL),
        ):
            mock_rpc._get_web3.return_value.eth.block_number = 100
            mock_rpc._get_web3.return_value.eth.get_block.return_value = {"transactions": []}
            monitor.poll_ethereum()  # first head observation
            monitor.poll_ethereum()  # same head again → stalled
        assert any("head stuck" in r.getMessage() for r in caplog.records if r.levelno >= logging.CRITICAL)

    def test_head_advance_clears_stall(self, monitor, caplog):
        import logging

        monitor.head_stall_seconds = 0
        with (
            patch.object(monitor, "_check_float"),
            patch.object(monitor, "eth_rpc") as mock_rpc,
            caplog.at_level(logging.CRITICAL),
        ):
            w3 = mock_rpc._get_web3.return_value
            w3.eth.get_block.return_value = {"transactions": []}
            w3.eth.block_number = 100
            monitor.poll_ethereum()
            w3.eth.block_number = 101  # head moved → stall resets
            monitor.poll_ethereum()
        assert not any("head stuck" in r.getMessage() for r in caplog.records)

    def test_scan_deadline_holds_cursor_and_alerts(self, monitor, caplog):
        import logging

        from bridge_monitor.storage import get_cursor, set_cursor

        monitor.cycle_timeout = -1.0  # deadline already passed
        set_cursor("last_processed_block", 96)
        with (
            patch.object(monitor, "_check_float"),
            patch.object(monitor, "eth_rpc") as mock_rpc,
            caplog.at_level(logging.CRITICAL),
        ):
            w3 = mock_rpc._get_web3.return_value
            w3.eth.block_number = 110
            monitor.poll_ethereum()
        w3.eth.get_block.assert_not_called()  # deadline checked before the fetch
        assert get_cursor("last_processed_block") == 96  # nothing skipped
        assert any("poll scan exceeded" in r.getMessage() for r in caplog.records)


class TestAdminMutationLock:
    """Mutating admin commands serialize on an flock next to the ledger DB.

    Two concurrent ``manual-payout`` runs would both pass the
    ``_payout_in_flight()`` check before either writes its SUBMITTED row,
    then sign envelopes on the same nonce — the mempool collision the
    one-envelope rule exists to prevent. Read commands stay lock-free.
    """

    def test_mutating_command_refused_while_lock_held(self, monitor, monkeypatch, capsys):
        import fcntl
        import sys as _sys

        import bridge_monitor.admin as admin
        import bridge_monitor.storage as storage
        from bridge_monitor.storage import create_deposit

        create_deposit("0xlock", "0xfrom", "1.0", "")
        fd = os.open(f"{storage.DB_PATH}.admin.lock", os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            monkeypatch.setattr(
                _sys,
                "argv",
                ["bridge_monitor.admin", "write-off", "0xlock", "--reason", "x", "--unpaid-with-recipient"],
            )
            assert admin.main() == 1
        finally:
            os.close(fd)
        assert "in progress" in capsys.readouterr().err

    def test_lock_released_after_command(self, monitor, monkeypatch, capsys):
        import sys as _sys

        import bridge_monitor.admin as admin
        from bridge_monitor.storage import create_deposit, get_deposit

        create_deposit("0xlock2", "0xfrom", "1.0", "")
        monkeypatch.setattr(
            _sys,
            "argv",
            ["bridge_monitor.admin", "write-off", "0xlock2", "--reason", "done", "--unpaid-with-recipient"],
        )
        assert admin.main() == 0
        assert get_deposit("0xlock2")["status"] == BridgeDepositStatus.WRITTEN_OFF.value
        # A second mutation is not blocked by the first run's stale lock —
        # write-off is idempotent on an already-terminal row, so assert on
        # the absence of the lock-refusal message instead of the rc.
        monkeypatch.setattr(
            _sys,
            "argv",
            ["bridge_monitor.admin", "write-off", "0xlock2", "--reason", "again", "--unpaid-with-recipient"],
        )
        admin.main()
        assert "in progress" not in capsys.readouterr().err


class TestSweepAdminLock:
    """The running sweep's payout check-then-act holds the same admin
    flock as mutating admin commands (issue #1632).

    ``manual-payout`` serializes on ``<ledger>.admin.lock``; before this
    fix the sweep's own in-flight probe → SUBMITTED row sequence ran
    unlocked, so a manual payout could interleave and sign a second
    envelope on the same nonce. Contention now defers the sweep's payout
    pass to the next cycle — it never stalls the loop and never signs.
    """

    @staticmethod
    def _hold_admin_lock():
        import fcntl

        import bridge_monitor.storage as storage

        fd = os.open(f"{storage.DB_PATH}.admin.lock", os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def test_first_sight_deposit_defers_while_admin_lock_held(self, monitor):
        from bridge_monitor.storage import get_deposit

        fd = self._hold_admin_lock()
        try:
            with (
                patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
                patch.object(monitor, "calculate_ait_amount", return_value=Decimal("100")),
                patch.object(monitor, "_build_signed_transfer") as mock_build,
                patch.object(monitor, "_post_signed_tx", return_value="0xpayout"),
            ):
                monitor.process_deposit("0xdep-lock", "0xfrom", Decimal("0.1"), "0xdata")
        finally:
            os.close(fd)

        mock_build.assert_not_called()  # no envelope signed under a held lock
        d = get_deposit("0xdep-lock")
        assert d["status"] == BridgeDepositStatus.PENDING_RETRY.value
        assert "admin mutation" in d["error_message"]
        assert not d["signed_tx"]
        assert Decimal(str(d["ait_amount"])) == 100  # priced amount kept for retry

    def test_first_sight_deposit_pays_once_lock_released(self, monitor):
        from bridge_monitor.storage import get_deposit

        fd = self._hold_admin_lock()
        os.close(fd)  # released before the sweep pass

        with (
            patch.object(monitor, "parse_ait_recipient", return_value="0x" + "d" * 40),
            patch.object(monitor, "calculate_ait_amount", return_value=Decimal("100")),
            patch.object(
                monitor,
                "_build_signed_transfer",
                return_value={"type": "TRANSFER", "nonce": 3, "to": "0x" + "d" * 40},
            ) as mock_build,
            patch.object(monitor, "_post_signed_tx", return_value="0xpayout"),
            patch.object(monitor, "_head_height", return_value=100),
        ):
            monitor.process_deposit("0xdep-free", "0xfrom", Decimal("0.1"), "0xdata")

        assert mock_build.call_count == 1
        assert get_deposit("0xdep-free")["status"] == BridgeDepositStatus.SUBMITTED.value

    def test_retry_queue_defers_while_admin_lock_held(self, monitor):
        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit

        create_deposit("0xret-lock", "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            "0xret-lock",
            ait_amount="100",
            status=BridgeDepositStatus.PENDING_RETRY,
            next_retry_at="2000-01-01T00:00:00+00:00",
        )
        fd = self._hold_admin_lock()
        try:
            with (
                patch.object(monitor, "_build_signed_transfer") as mock_build,
                patch.object(monitor, "_post_signed_tx", return_value="0xpayout"),
            ):
                monitor.process_retry_queue()
        finally:
            os.close(fd)

        mock_build.assert_not_called()
        d = get_deposit("0xret-lock")
        assert d["status"] == BridgeDepositStatus.PENDING_RETRY.value
        assert "admin mutation" in d["error_message"]
        assert not d["signed_tx"]

    def test_retry_queue_pays_once_lock_released(self, monitor):
        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit

        create_deposit("0xret-free", "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            "0xret-free",
            ait_amount="100",
            status=BridgeDepositStatus.PENDING_RETRY,
            next_retry_at="2000-01-01T00:00:00+00:00",
        )
        with (
            patch.object(
                monitor,
                "_build_signed_transfer",
                return_value={"type": "TRANSFER", "nonce": 4, "to": "0x" + "d" * 40},
            ) as mock_build,
            patch.object(monitor, "_post_signed_tx", return_value="0xpayout2"),
            patch.object(monitor, "_head_height", return_value=100),
        ):
            monitor.process_retry_queue()

        assert mock_build.call_count == 1
        assert get_deposit("0xret-free")["status"] == BridgeDepositStatus.SUBMITTED.value


class TestNullSubmittedHeight:
    """BRIDGE-MON-ALERT-1 (#1436): a NULL ``submitted_height`` — the
    sign-time ``/rpc/head`` fetch failed — is UNKNOWN age, not "now".
    Both consumers must read it as oldest: the stuck-payout alert (a
    missing height used to make the row look brand new and suppress the
    alert) and the rebroadcast seal window (same fallback kept the row
    inside the window forever, so it was never rebroadcast)."""

    @staticmethod
    def _null_height_row(monitor, tx_hash="0xnullh"):
        import json as _json

        from bridge_monitor.storage import create_deposit, update_deposit

        envelope = {
            "type": "TRANSFER",
            "chain_id": "ait-test",
            "from": "0x" + "b" * 40,
            "to": "0x" + "d" * 40,
            "amount": 100,
            "nonce": 7,
            "fee": 360000,
            "payload": {"amount": 100},
            "signature": "0xdeadbeef",
        }
        payout_hash = monitor._envelope_tx_hash(envelope)
        create_deposit(tx_hash, "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            tx_hash,
            ait_amount="100",
            signed_tx=_json.dumps(envelope),
            envelope_hash=payout_hash,
            ait_tx_hash=payout_hash,
            status=BridgeDepositStatus.SUBMITTED,
        )
        # submitted_height stays NULL — _head_height() returned None at sign
        return envelope, payout_hash

    def test_null_height_row_alerts_as_oldest(self, monitor, caplog):
        import logging

        self._null_height_row(monitor)
        with (
            patch.object(monitor, "_head_height", return_value=monitor.stuck_payout_blocks + 100),
            caplog.at_level(logging.CRITICAL),
        ):
            monitor._check_queue_health()

        alerts = [r for r in caplog.records if "payout slot blocked" in r.message]
        assert alerts and "0xnullh" in alerts[0].message

    def test_known_recent_height_does_not_alert(self, monitor, caplog):
        """Guard against the fix over-firing: a row with a real, recent
        submitted_height inside the window stays silent."""
        import logging

        from bridge_monitor.storage import create_deposit, update_deposit

        create_deposit("0xfreshh", "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            "0xfreshh",
            signed_tx='{"nonce": 1}',
            submitted_height=95,
            status=BridgeDepositStatus.SUBMITTED,
        )
        with (
            patch.object(monitor, "_head_height", return_value=100),
            caplog.at_level(logging.CRITICAL),
        ):
            monitor._check_queue_health()

        assert not any("payout slot blocked" in r.message for r in caplog.records)

    def test_null_height_row_is_rebroadcast_eligible(self, monitor):
        """Unknown age must not park the row inside the seal window: the
        sweep rebroadcasts the identical stored envelope and heals the
        height on success."""
        from bridge_monitor.storage import get_deposit

        envelope, _ = self._null_height_row(monitor)
        with (
            patch.object(monitor, "_head_height", return_value=100),
            patch.object(monitor, "_account_nonce", return_value=0),  # abandon refuses: nonce not passed
            patch.object(monitor, "_tx_on_chain", return_value=False),
            patch.object(monitor, "_post_signed_tx", return_value="0xsame") as mock_post,
            patch("httpx.get") as mock_get,
        ):
            mock_get.return_value = MagicMock(status_code=404)  # tx gone from mempool
            monitor.process_submitted_deposits()

        mock_post.assert_called_once_with(envelope)
        d = get_deposit("0xnullh")
        assert d["status"] == BridgeDepositStatus.SUBMITTED.value
        assert d["rebroadcast_count"] == 1
        assert d["submitted_height"] == 100  # real height written back


class TestOrphanedManualPending:
    """BRIDGE-MON-PAYOUT-1 residual (#1433): a crash between the admin
    ``create_deposit`` and the SUBMITTED write orphans a ``manual-*`` row
    in PENDING — the retry queue never selects PENDING and a manual row's
    zero ETH amount could never be priced. The sweep now fails stale
    manual rows; every other pending row belongs to the wallet side and
    must stay untouched (ledger state-machine invariant)."""

    @staticmethod
    def _manual_row(tx_hash="manual-20261108T120000.000001"):
        from bridge_monitor.storage import create_deposit

        create_deposit(tx_hash, "manual", "0", "0x" + "d" * 40)

    @staticmethod
    def _backdate(tx_hash, created_at="2000-01-01T00:00:00+00:00"):
        import sqlite3

        import bridge_monitor.storage as storage

        conn = sqlite3.connect(storage.DB_PATH)
        try:
            conn.execute("UPDATE eth_deposits SET created_at = ? WHERE tx_hash = ?", (created_at, tx_hash))
            conn.commit()
        finally:
            conn.close()

    def test_stale_manual_pending_row_fails(self, monitor):
        from bridge_monitor.storage import get_deposit

        self._manual_row()
        self._backdate("manual-20261108T120000.000001")
        monitor._fail_orphaned_manual_payouts()

        d = get_deposit("manual-20261108T120000.000001")
        assert d["status"] == BridgeDepositStatus.FAILED.value
        assert "orphaned" in (d["error_message"] or "")
        assert d["processed_at"]  # terminal rows carry the completion stamp

    def test_fresh_manual_pending_row_untouched(self, monitor):
        """A manual row mid-command (created seconds ago) is not an orphan."""
        from bridge_monitor.storage import get_deposit

        self._manual_row("manual-20261108T120001.000002")
        monitor._fail_orphaned_manual_payouts()

        assert get_deposit("manual-20261108T120001.000002")["status"] == BridgeDepositStatus.PENDING.value

    def test_non_manual_pending_row_never_touched(self, monitor):
        """Invariant: 'pending' is the wallet side's live vocabulary — the
        orphan sweep must not reach it even when the row is ancient."""
        from bridge_monitor.storage import create_deposit, get_deposit

        create_deposit("0xwalletpending", "0xfrom", "1.0", "0x" + "e" * 40)
        self._backdate("0xwalletpending")
        monitor._fail_orphaned_manual_payouts()

        assert get_deposit("0xwalletpending")["status"] == BridgeDepositStatus.PENDING.value

    def test_manual_submitted_row_untouched(self, monitor):
        """A manual row that reached SUBMITTED owns a live envelope — the
        confirmation sweep owns it, the orphan sweep must not fail it."""
        import json as _json

        from bridge_monitor.storage import create_deposit, get_deposit, update_deposit

        tx_hash = "manual-20261108T120002.000003"
        create_deposit(tx_hash, "manual", "0", "0x" + "d" * 40)
        update_deposit(
            tx_hash,
            ait_amount="100",
            signed_tx=_json.dumps({"type": "TRANSFER", "nonce": 3}),
            status=BridgeDepositStatus.SUBMITTED,
        )
        self._backdate(tx_hash)
        monitor._fail_orphaned_manual_payouts()

        d = get_deposit(tx_hash)
        assert d["status"] == BridgeDepositStatus.SUBMITTED.value
        assert d["signed_tx"]  # envelope preserved for the sweep


class TestRetryQueueContainment:
    """#2826: one poisoned retry row must not abort process_retry_queue —
    an uncaught exception used to propagate out of the poll cycle, starving
    every row behind it AND the SUBMITTED seal sweep, every cycle."""

    def _due_row(self, tx_hash, *, created_order=None):
        from bridge_monitor.storage import create_deposit, update_deposit

        create_deposit(tx_hash, "0xfrom", "1.0", "0x" + "d" * 40)
        update_deposit(
            tx_hash,
            ait_amount="100",
            status=BridgeDepositStatus.PENDING_RETRY,
            next_retry_at="2000-01-01T00:00:00+00:00",
        )

    def test_poisoned_row_does_not_starve_queue_tail(self, monitor):
        from bridge_monitor.storage import get_deposit

        self._due_row("0xpoison")
        self._due_row("0xhealthy")
        envelope = {"type": "TRANSFER", "nonce": 3, "to": "0x" + "d" * 40}

        real_submit = monitor._submit_retry_payout

        def _boom(d, tx_hash, ait_recipient, ait_amount):
            if tx_hash == "0xpoison":
                raise RuntimeError("poisoned row")
            return real_submit(d, tx_hash, ait_recipient, ait_amount)

        with (
            patch.object(monitor, "_submit_retry_payout", side_effect=_boom),
            patch.object(monitor, "_build_signed_transfer", return_value=envelope),
            patch.object(monitor, "_post_signed_tx", return_value="0xpaid"),
            patch.object(monitor, "_head_height", return_value=100),
        ):
            monitor.process_retry_queue()

        # The healthy row behind the poison was still attempted.
        assert get_deposit("0xhealthy")["status"] == BridgeDepositStatus.SUBMITTED.value
        # The poison row was re-queued for another attempt, not lost.
        poison = get_deposit("0xpoison")
        assert poison["status"] == BridgeDepositStatus.PENDING_RETRY.value

    def test_unpayable_stored_amount_requeues_not_crashes(self, monitor):
        from bridge_monitor.storage import get_deposit

        self._due_row("0xbadamt")
        self._due_row("0xafter")
        envelope = {"type": "TRANSFER", "nonce": 3, "to": "0x" + "d" * 40}
        with (
            patch.object(
                monitor,
                "_reprice_retry_if_needed",
                side_effect=lambda d, tx_hash: "sNaN" if tx_hash == "0xbadamt" else "100",
            ),
            patch.object(monitor, "_build_signed_transfer", return_value=envelope),
            patch.object(monitor, "_post_signed_tx", return_value="0xpaid"),
            patch.object(monitor, "_head_height", return_value=100),
        ):
            monitor.process_retry_queue()

        bad = get_deposit("0xbadamt")
        assert bad["status"] == BridgeDepositStatus.PENDING_RETRY.value
        assert "not payable" in (bad["error_message"] or "")
        assert get_deposit("0xafter")["status"] == BridgeDepositStatus.SUBMITTED.value


class TestNonFinitePayoutCaps2822:
    """#2822: non-finite BRIDGE_MAX_PAYOUT_* env values must not crash the
    constructor or overflow the per-deposit cap check."""

    def _make_monitor(self, tmp_path, monkeypatch, **env):
        from bridge_monitor.main import BridgeMonitor

        db_path = str(tmp_path / "bridge_deposits.db")
        monkeypatch.setattr("bridge_monitor.storage.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("bridge_monitor.storage.DB_PATH", db_path)
        monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "0x" + "a" * 40)
        monkeypatch.setenv("GENESIS_WALLET_ADDRESS", "0x" + "b" * 40)
        monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", "0x" + "c" * 64)
        monkeypatch.setenv("BRIDGE_MIN_DEPOSIT_AIT", "1")
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        with patch("bridge_monitor.main.EthereumRPCClient"), patch("bridge_monitor.main.get_price_oracle"):
            return BridgeMonitor()

    def test_infinite_absolute_cap_is_ignored(self, tmp_path, monkeypatch):
        """BRIDGE_MAX_PAYOUT_AIT=Infinity passed `> 0`, then overflowed
        ait_to_units() inside _exceeds_payout_cap on every deposit."""
        m = self._make_monitor(tmp_path, monkeypatch, BRIDGE_MAX_PAYOUT_AIT="Infinity")
        assert m.max_payout_ait is None

    def test_nan_fraction_falls_back_instead_of_crashing(self, tmp_path, monkeypatch):
        """BRIDGE_MAX_PAYOUT_FRACTION=NaN made `0 < NaN <= 1` raise
        InvalidOperation outside the try — the constructor died."""
        m = self._make_monitor(tmp_path, monkeypatch, BRIDGE_MAX_PAYOUT_FRACTION="NaN")
        assert m.max_payout_fraction == Decimal("0.5")

    def test_snan_fraction_falls_back(self, tmp_path, monkeypatch):
        m = self._make_monitor(tmp_path, monkeypatch, BRIDGE_MAX_PAYOUT_FRACTION="sNaN")
        assert m.max_payout_fraction == Decimal("0.5")

    def test_nan_absolute_cap_still_ignored(self, tmp_path, monkeypatch):
        m = self._make_monitor(tmp_path, monkeypatch, BRIDGE_MAX_PAYOUT_AIT="NaN")
        assert m.max_payout_ait is None

    def test_programmatic_infinite_cap_does_not_overflow(self, tmp_path, monkeypatch):
        """Defense in depth: a non-finite cap set after construction must not
        reach ait_to_units either."""
        from aitbc.utils.units import ait_to_units

        m = self._make_monitor(tmp_path, monkeypatch)
        m.max_payout_ait = Decimal("Infinity")
        # Balance unreadable: the absolute cap is skipped (non-finite), the
        # fraction check fails open — the point is no OverflowError escapes.
        with patch.object(m, "_payout_wallet_balance", return_value=None):
            exceeded, _ = m._exceeds_payout_cap(Decimal("1"))
        assert exceeded is False
        with patch.object(m, "_payout_wallet_balance", return_value=ait_to_units(1000)):
            exceeded, _ = m._exceeds_payout_cap(Decimal("1"))
        assert exceeded is False


class TestTxHashCaseDedupe2823:
    """#2823: UNIQUE(tx_hash) is case-sensitive — a legacy mixed-case row
    plus a canonical insert of the same deposit must not both land."""

    def _insert_raw_row(self, monitor, row_id: str, tx_hash: str, created_at: str) -> None:
        """Write a row exactly as pre-#668 code did — no canonicalization."""
        from bridge_monitor.storage import _connect_db

        with _connect_db() as conn:
            conn.execute(
                """
                INSERT INTO eth_deposits
                (id, tx_hash, from_address, recipient, amount_eth, amount_ait, status, created_at)
                VALUES (?, ?, ?, ?, ?, '0', 'pending', ?)
                """,
                (
                    row_id,
                    tx_hash,
                    "0xfrom",
                    "0x" + "d" * 40,
                    "1.0",
                    created_at,
                ),
            )
            conn.commit()

    def test_canonical_insert_dedupes_against_mixed_case_legacy(self, monitor):
        from bridge_monitor.storage import create_deposit, get_deposit

        mixed = "0xAbCdEf" + "0" * 58
        self._insert_raw_row(monitor, "deposit_legacy001", mixed, "2026-01-01T00:00:00+00:00")
        # Same deposit, canonical spelling — must be treated as a duplicate.
        assert create_deposit(mixed.lower(), "0xfrom", "1.0", "0x" + "d" * 40) is None
        dep = get_deposit(mixed)
        assert dep is not None
        assert dep["id"] == "deposit_legacy001"

    def test_get_deposit_prefers_earliest_row_when_dups_exist(self, monitor):
        """If case-variant duplicates already exist in the DB, the lookup
        must return a deterministic row — the earliest record."""
        from bridge_monitor.storage import get_deposit

        canon = "0x" + "a1" * 32
        mixed = "0xA1" + "a1" * 31
        # Force the duplicate state directly (pre-fix DBs can hold it).
        # Insert the canonical row FIRST so bare fetchone (rowid order)
        # returns it — only the ORDER BY picks the earlier-created legacy row.
        self._insert_raw_row(monitor, "deposit_canonical1", canon, "2026-06-01T00:00:00+00:00")
        self._insert_raw_row(monitor, "deposit_legacy001", mixed, "2026-01-01T00:00:00+00:00")
        dep = get_deposit(canon)
        assert dep is not None
        assert dep["id"] == "deposit_legacy001"  # earliest created_at wins


class TestRecipientParseParity2824:
    """#2824: parse_ait_recipient must accept everything the wallet side's
    parser accepts — strip + EIP-55 canonicalization — and must not flip a
    pre-existing (wallet-owned) pending row to FAILED."""

    @staticmethod
    def _utf8_hex(text: str) -> str:
        return "0x" + text.encode("utf-8").hex()

    def test_whitespace_padded_address_parses(self, monitor):
        addr = "0x" + "d" * 40
        padded = "  " + addr + " \n"
        result = monitor.parse_ait_recipient(self._utf8_hex(padded))
        assert result is not None
        # Canonical EIP-55 — same spelling the wallet side stores.
        assert result == canonical_address(addr)

    def test_plain_address_returns_eip55(self, monitor):
        addr = "0x" + "ab" * 20
        result = monitor.parse_ait_recipient(self._utf8_hex(addr))
        assert result == canonical_address(addr)

    def test_raw_20_byte_input_parses(self, monitor):
        raw = bytes(range(20))
        result = monitor.parse_ait_recipient("0x" + raw.hex())
        assert result == "0x" + raw.hex()

    def test_garbage_still_rejected(self, monitor):
        assert monitor.parse_ait_recipient("0x" + "zz" * 20) is None
        assert monitor.parse_ait_recipient("0x") is None
        assert monitor.parse_ait_recipient("") is None

    def test_unparseable_does_not_flip_preexisting_pending_row(self, monitor):
        """A wallet-side 'pending' row for the same tx must survive: the
        monitor only fails rows it created itself."""
        from bridge_monitor.storage import create_deposit, get_deposit

        tx_hash = "0x" + "b" * 64
        # Simulate the wallet side's row winning the insert race: it lands
        # after the monitor's existence check but before its FAILED write.
        assert create_deposit(tx_hash, "0xfrom", "1.0", "0x" + "e" * 40) is not None

        real_get = __import__("bridge_monitor.storage", fromlist=["get_deposit"]).get_deposit
        calls = {"n": 0}

        def get_then_none(h):
            calls["n"] += 1
            return None if calls["n"] == 1 else real_get(h)

        with patch("bridge_monitor.main.get_deposit", side_effect=get_then_none):
            monitor.process_deposit(tx_hash, "0xfrom", Decimal("0.01"), "0x68656c6c6f")

        dep = get_deposit(tx_hash)
        assert dep["status"] == "pending"  # untouched — not flipped FAILED

    def test_unparseable_fails_row_it_created(self, monitor):
        from bridge_monitor.storage import get_deposit

        tx_hash = "0x" + "c" * 64
        monitor.process_deposit(tx_hash, "0xfrom", Decimal("0.01"), "0x68656c6c6f")

        dep = get_deposit(tx_hash)
        assert dep["status"] == "failed"
        assert "recipient" in (dep["error_message"] or "").lower()


class TestOraclePriceValidation2825:
    """#2825: non-finite or non-positive oracle prices must defer the payout
    to PENDING_RETRY — never reach the below-minimum FAILED gate."""

    def _seed_pending(self, monitor, tx_hash: str) -> None:
        from bridge_monitor.storage import create_deposit

        assert create_deposit(tx_hash, "0xfrom", "0.01", "0x" + "d" * 40) is not None

    @pytest.mark.parametrize(
        "eth_usd,ait_usd",
        [
            ("-1", "0.5"),  # negative ETH price → negative ait_amount
            ("0.5", "-2"),  # negative AIT price → negative ait_amount
            ("NaN", "0.5"),
            ("0.5", "Infinity"),
            ("sNaN", "0.5"),
            ("0", "0.5"),  # zero price — was already guarded, keep pinned
        ],
    )
    def test_bad_prices_return_none(self, monitor, eth_usd, ait_usd):
        assert monitor.calculate_ait_amount(Decimal("1"), eth_usd=eth_usd, ait_usd=ait_usd) is None

    def test_negative_price_keeps_deposit_retryable(self, monitor):
        """End-to-end: a transiently negative quote must not permanently
        FAIL a deposit whose funds were received."""
        from bridge_monitor.storage import count_pending_retry, get_deposit

        tx_hash = "0x" + "e" * 64
        self._seed_pending(monitor, tx_hash)

        class _P:
            def __init__(self, price):
                self.price = price

        with patch.object(monitor.price_oracle, "get_price", side_effect=[_P("-1"), _P("0.5")]):
            ait_amount, _, _ = monitor._compute_amount_and_gate(tx_hash, "0xfrom", Decimal("0.01"), "0x" + "d" * 40)
        assert ait_amount is None
        dep = get_deposit(tx_hash)
        assert dep["status"] == "pending_retry"
        assert count_pending_retry() == 1

    def test_nan_price_does_not_raise(self, monitor):
        class _P:
            def __init__(self, price):
                self.price = price

        with patch.object(monitor.price_oracle, "get_price", side_effect=[_P("NaN"), _P("0.5")]):
            ait_amount, _, _ = monitor._compute_amount_and_gate("0x" + "f" * 64, "0xfrom", Decimal("0.01"), "0x" + "d" * 40)
        assert ait_amount is None
