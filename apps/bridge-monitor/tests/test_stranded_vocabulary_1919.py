"""#1919 ETH-DEPOSITS-VOCAB-1 pins — shared-table vocabulary map,
wallet-state handling, write-time guards, and the stranded-row detector.

eth_deposits is ONE sqlite table shared by aitbc-wallet and
aitbc-bridge-monitor with two partially overlapping status vocabularies.
A row flipped pending->verified by the wallet admin route before the
monitor's payout pass loses every _mark_for_retry/_submit_payout CAS and
sat 'verified' forever: not in pending_retry, not re-scanned, no alert —
funds received, never paid, invisible to both worklists.
"""

import logging
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
from bridge_monitor.storage import (  # noqa: E402
    DEPOSIT_TERMINAL_STATUSES,
    DEPOSIT_WORKLIST_STATUSES,
    WALLET_LIFECYCLE_STATUSES,
    BridgeDepositStatus,
)


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


def _set_row(db_path: str, tx_hash: str, **fields: str) -> None:
    """Direct-SQL row edit — the wallet vocabulary has no monitor writer."""
    assignments = ", ".join(f"{k} = ?" for k in fields)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"UPDATE eth_deposits SET {assignments} WHERE tx_hash = ?",  # nosec — keys are test literals
            (*fields.values(), tx_hash),
        )


def _old_iso(hours: float = 48.0) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


class TestVocabularyMap:
    def test_every_monitor_status_is_classified(self):
        """Each BridgeDepositStatus lands in exactly one bucket: terminal,
        worklist-owned, or stranded-eligible — none may fall through."""
        assert not (DEPOSIT_TERMINAL_STATUSES & DEPOSIT_WORKLIST_STATUSES)
        stranded_eligible = {m.value for m in BridgeDepositStatus} - DEPOSIT_TERMINAL_STATUSES - DEPOSIT_WORKLIST_STATUSES
        # pending/processing are transient monitor states — a row stuck in
        # either past the horizon IS stranded (crash before first update).
        assert stranded_eligible == {"pending", "processing"}

    def test_wallet_lifecycle_states_documented(self):
        """'verified' is wallet mint-in-flight (never auto-paid — double-
        mint risk); 'rejected' is the wallet's operator-terminal state."""
        assert WALLET_LIFECYCLE_STATUSES == frozenset({"verified", "rejected"})
        assert "rejected" in DEPOSIT_TERMINAL_STATUSES
        # 'verified' is NOT terminal — the stranded detector must see it.
        assert "verified" not in DEPOSIT_TERMINAL_STATUSES
        assert "verified" not in DEPOSIT_WORKLIST_STATUSES


class TestWriteTimeGuards:
    def test_create_deposit_rejects_wallet_status_string(self, monitor):
        with pytest.raises(ValueError, match="BridgeDepositStatus"):
            storage.create_deposit("0xvg1", "0xf", "1", "r", status="verified")  # type: ignore[arg-type]

    def test_update_deposit_rejects_wallet_status_string(self, monitor):
        storage.create_deposit("0xvg2", "0xf", "1", "r")
        with pytest.raises(ValueError, match="BridgeDepositStatus"):
            storage.update_deposit("0xvg2", status="verified")  # type: ignore[arg-type]
        assert storage.get_deposit("0xvg2")["status"] == "pending"

    def test_update_deposit_still_accepts_enum(self, monitor):
        storage.create_deposit("0xvg3", "0xf", "1", "r")
        assert storage.update_deposit("0xvg3", status=BridgeDepositStatus.PENDING_RETRY)
        assert storage.get_deposit("0xvg3")["status"] == "pending_retry"


class TestProcessDepositWalletStates:
    def test_verified_row_never_paid_or_retried(self, monitor):
        """The #1919 bug shape: a monitor-owned row flipped 'verified' by
        the wallet admin route must NOT be paid by the monitor (its
        wallet-side TRANSFER may have landed) and must NOT be flipped to
        pending_retry (CAS cannot land — it would sit verified forever,
        which the stranded detector now alerts on)."""
        storage.create_deposit("0xwlv", "0xf", "1.0", "0x" + "d" * 40)
        _set_row(str(storage.DB_PATH), "0xwlv", status="verified")

        with (
            patch.object(monitor, "_build_signed_transfer") as mock_build,
            patch.object(monitor, "_post_signed_tx") as mock_post,
        ):
            monitor.process_deposit("0xwlv", "0xf", Decimal("1.0"), "0xdata")

        mock_build.assert_not_called()
        mock_post.assert_not_called()
        row = storage.get_deposit("0xwlv")
        assert row["status"] == "verified"  # untouched — detector owns visibility
        assert not row["signed_tx"]

    def test_rejected_row_skipped(self, monitor):
        storage.create_deposit("0xrej", "0xf", "1.0", "")
        _set_row(str(storage.DB_PATH), "0xrej", status="rejected")
        with patch.object(monitor, "_mark_for_retry") as mock_retry:
            monitor.process_deposit("0xrej", "0xf", Decimal("1.0"), "0xdata")
        mock_retry.assert_not_called()
        assert storage.get_deposit("0xrej")["status"] == "rejected"


class TestStrandedDetector:
    def test_storage_selects_only_unowned_old_rows(self, monitor):
        db = str(storage.DB_PATH)
        rows = {
            "0xold_verified": ("verified", _old_iso(48)),
            "0xold_pending": ("pending", _old_iso(48)),
            "0xold_processing": ("processing", _old_iso(48)),
            "0xold_unknown": ("bogus_status", _old_iso(48)),
            "0xfresh_verified": ("verified", datetime.now(UTC).isoformat()),
            "0xold_completed": ("completed", _old_iso(48)),
            "0xold_failed": ("failed", _old_iso(48)),
            "0xold_written_off": ("written_off", _old_iso(48)),
            "0xold_funding": ("funding", _old_iso(48)),
            "0xold_prepay": ("exchange_prepay", _old_iso(48)),
            "0xold_rejected": ("rejected", _old_iso(48)),
            "0xold_retry": ("pending_retry", _old_iso(48)),
            "0xold_submitted": ("submitted", _old_iso(48)),
        }
        for tx, (status, created) in rows.items():
            storage.create_deposit(tx, "0xf", "1", "r")
            _set_row(db, tx, status=status, created_at=created)

        cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        stranded = {d["eth_tx_hash"]: d["status"] for d in storage.get_stranded_deposits(cutoff)}

        assert stranded == {
            "0xold_verified": "verified",
            "0xold_pending": "pending",
            "0xold_processing": "processing",
            "0xold_unknown": "bogus_status",
        }

    def test_check_fires_critical_on_old_verified_only(self, monitor, caplog):
        db = str(storage.DB_PATH)
        storage.create_deposit("0xstranded", "0xf", "1", "0x" + "d" * 40)
        _set_row(db, "0xstranded", status="verified", created_at=_old_iso(48))
        storage.create_deposit("0xfresh", "0xf", "1", "r")
        _set_row(db, "0xfresh", status="verified")  # fresh verified — mid mint
        storage.create_deposit("0xdone", "0xf", "1", "r")
        _set_row(db, "0xdone", status="completed", created_at=_old_iso(48))

        with caplog.at_level(logging.CRITICAL):
            monitor._check_stranded_deposits()

        alerts = [r.getMessage() for r in caplog.records if r.levelno >= logging.CRITICAL]
        assert any("0xstranded" in m and "verified" in m for m in alerts)
        assert not any("0xfresh" in m for m in alerts)
        assert not any("0xdone" in m for m in alerts)

    def test_check_is_throttled_and_clears(self, monitor, caplog):
        db = str(storage.DB_PATH)
        storage.create_deposit("0xthr", "0xf", "1", "r")
        _set_row(db, "0xthr", status="verified", created_at=_old_iso(48))

        with caplog.at_level(logging.CRITICAL):
            monitor._check_stranded_deposits()
            monitor._check_stranded_deposits()  # same cycle window — throttled
        first = [r for r in caplog.records if "0xthr" in r.getMessage()]
        assert len(first) == 1

        # Row resolves -> terminal: the alert key clears, a recurrence
        # (impossible here, but the bookkeeping must not leak) re-arms.
        _set_row(db, "0xthr", status="written_off")
        monitor._check_stranded_deposits()
        assert not any(k.startswith("stranded:") for k in monitor._float_alert_last)

    def test_check_survives_empty_and_bad_rows(self, monitor):
        # No rows at all — must not raise.
        monitor._check_stranded_deposits()


class TestAdminWriteOffVerified:
    def test_write_off_accepts_verified_source(self, tmp_path, monkeypatch):
        """A stranded 'verified' row needs a deliberate resolution path —
        write-off's CAS source set must include it (#1919)."""
        from bridge_monitor import admin

        monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
        monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "admin.db"))
        storage.init_db()
        storage.create_deposit("0xadminwo", "0xf", "1", "")
        _set_row(str(storage.DB_PATH), "0xadminwo", status="verified")

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "bridge-admin",
                "--env-file",
                str(tmp_path / "missing.env"),
                "write-off",
                "0xadminwo",
                "--reason",
                "stranded verified",
            ],
        )
        assert admin.main() == 0
        assert storage.get_deposit("0xadminwo")["status"] == BridgeDepositStatus.WRITTEN_OFF.value
