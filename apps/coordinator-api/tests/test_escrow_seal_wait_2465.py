"""Tests for #2465: escrow lock seal wait must cover at least one block slot.

The flat 30 s default was shorter than the fleet's 60 s block time, so a
fresh deploy failed roughly half of all purchases whose lock sealed moments
after the deadline. The default is now ``max(3 x BLOCK_TIME_SECONDS, 120)``
and an explicit ``ESCROW_LOCK_SEAL_WAIT_SECONDS`` still overrides; a wait
below the block time logs a warning.
"""

from __future__ import annotations

import pytest

from coordinator_api.contexts.payments.services.payments_escrow import _lock_seal_wait_seconds


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ESCROW_LOCK_SEAL_WAIT_SECONDS", raising=False)
    monkeypatch.delenv("BLOCK_TIME_SECONDS", raising=False)


def test_default_covers_fleet_block_time():
    # BLOCK_TIME_SECONDS unset → fleet default 60 s → max(180, 120) = 180.
    assert _lock_seal_wait_seconds() == 180.0


def test_default_scales_with_block_time(monkeypatch):
    monkeypatch.setenv("BLOCK_TIME_SECONDS", "10")
    assert _lock_seal_wait_seconds() == 120.0  # floor wins
    monkeypatch.setenv("BLOCK_TIME_SECONDS", "120")
    assert _lock_seal_wait_seconds() == 360.0


def test_explicit_wait_wins(monkeypatch):
    monkeypatch.setenv("ESCROW_LOCK_SEAL_WAIT_SECONDS", "45")
    assert _lock_seal_wait_seconds() == 45.0


def test_wait_below_block_time_warns(monkeypatch, caplog):
    monkeypatch.setenv("BLOCK_TIME_SECONDS", "60")
    monkeypatch.setenv("ESCROW_LOCK_SEAL_WAIT_SECONDS", "30")
    with caplog.at_level("WARNING"):
        assert _lock_seal_wait_seconds() == 30.0
    assert any("below the chain block time" in r.message for r in caplog.records)
