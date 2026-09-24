"""Tests for the SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL production guard.

The kill-switch disables proposer-signature validation until a timestamp.
On production nodes a horizon beyond 48h is treated as an operator mistake
and fails closed instead of running indefinitely without validation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


def _settings(skip_until: str):
    from aitbc_chain.config import ChainSettings

    return ChainSettings(sync_validate_signatures_skip_until=skip_until)


def test_far_future_skip_refused_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    far = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    with pytest.raises(Exception, match="at most 48h"):
        _settings(far)


def test_short_skip_allowed_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    near = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    s = _settings(near)
    assert s.sync_validate_signatures is False


def test_far_future_skip_allowed_outside_production(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    far = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    s = _settings(far)
    assert s.sync_validate_signatures is False


def test_naive_timestamp_treated_as_utc(monkeypatch) -> None:
    """A naive ISO timestamp must not crash the validator (naive/aware TypeError)."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    naive = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None).isoformat()
    s = _settings(naive)
    assert s.sync_validate_signatures is False


def test_past_timestamp_leaves_validation_enabled() -> None:
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    s = _settings(past)
    assert s.sync_validate_signatures is True


def test_malformed_timestamp_leaves_validation_enabled() -> None:
    s = _settings("not-a-timestamp")
    assert s.sync_validate_signatures is True
