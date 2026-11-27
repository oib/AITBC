"""#3049 pins: a settle tx that sealed into a block but FAILED to apply
(``status='failed'`` + ``block_height``) moved no value — yet every lane
that checks ``block_height is not None`` treats it as proven-settled.

Agent-coordinator: ``_classify_probe`` must classify it ``failed_sealed``
and demote the terminal row back to LOCKED — the same re-drive path as
absent/rejected — never tombstone it as settled.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

import importlib.util
from pathlib import Path

from aitbc.crypto import EscrowStatus, PaymentEscrow  # noqa: E402

# The sibling harness lives in tests/test_terminal_settle_sweep_3026.py; a
# ``tests.`` package import only resolves under an app-dir pytest run,
# where the shared ``aitbc`` package would come from the stale installed
# copy instead of this worktree. Load it by path instead.
_spec = importlib.util.spec_from_file_location(
    "_settle_sweep_3026_harness",
    Path(__file__).with_name("test_terminal_settle_sweep_3026.py"),
)
_harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_harness)

ChainHandler = _harness._ChainHandler
_client = _harness._client
_refunded_entry = _harness._refunded_entry
_released_entry = _harness._released_entry
_sweeper = _harness._sweeper
RELEASE_TX = _harness.RELEASE_TX
REFUND_TX = _harness.REFUND_TX


def _failed_sealed_tx() -> tuple[int, dict]:
    """The sync_block_import shape: durable row, height set, apply reverted."""
    return 200, {
        "tx_hash": RELEASE_TX,
        "status": "failed",
        "block_height": 4321,
        "failure_reason": "escrow release apply reverted",
        "type": "ESCROW_RELEASE",
    }


class TestFailedSealedDemotes:
    def test_released_with_failed_sealed_settle_demotes_to_locked(self):
        """Headline: provider was never paid (apply reverted) but the row
        said RELEASED — the sweeper must demote, not keep the lie."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        sweeper = _sweeper(escrow, _client(ChainHandler({RELEASE_TX: _failed_sealed_tx()})))

        counts = sweeper.run_once()

        assert counts["demoted"] == 1
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.LOCKED
        assert refreshed.released_at is None
        assert refreshed.tx_hash_release == RELEASE_TX  # dead hash kept for audit
        assert refreshed.metadata["settle_demoted_reason"] == "settle_tx_failed_sealed_on_chain"

    def test_refunded_with_failed_sealed_settle_demotes_to_locked(self):
        escrow = PaymentEscrow()
        entry = _refunded_entry(escrow)
        failed_refund = (200, {"tx_hash": REFUND_TX, "status": "failed", "block_height": 77})
        sweeper = _sweeper(escrow, _client(ChainHandler({REFUND_TX: failed_refund})))

        counts = sweeper.run_once()

        assert counts["demoted"] == 1
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.LOCKED
        assert refreshed.metadata["settle_demoted_reason"] == "settle_tx_failed_sealed_on_chain"

    def test_demoted_row_can_re_release(self):
        """After demote the normal release path re-submits with a fresh hash."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        sweeper = _sweeper(escrow, _client(ChainHandler({RELEASE_TX: _failed_sealed_tx()})))
        assert sweeper.run_once()["demoted"] == 1

        new_tx = "0x" + "ee" * 32
        escrow.release(entry.escrow_id, submitter=lambda *_a: new_tx)
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.RELEASED
        assert refreshed.tx_hash_release == new_tx

    def test_confirmed_sealed_still_tombstones(self):
        """Control: the real seal standard still counts as settled."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        confirmed = (200, {"tx_hash": RELEASE_TX, "status": "confirmed", "block_height": 4321})
        sweeper = _sweeper(escrow, _client(ChainHandler({RELEASE_TX: confirmed})))

        counts = sweeper.run_once()

        assert counts.get("demoted", 0) == 0
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.RELEASED

    def test_bare_height_no_confirmed_status_does_not_seal(self):
        """A height without status='confirmed' is not proven-applied."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        odd = (200, {"tx_hash": RELEASE_TX, "block_height": 4321})
        sweeper = _sweeper(escrow, _client(ChainHandler({RELEASE_TX: odd})))

        counts = sweeper.run_once()

        # unknown verdict → skipped, row untouched (fail-closed, no demote
        # on ambiguous evidence)
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.RELEASED
        assert counts.get("demoted", 0) == 0
