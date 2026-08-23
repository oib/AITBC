"""The coordinator records when the provider was paid, not when it noticed."""

from datetime import UTC, datetime

from coordinator_api.contexts.payments.services.payments import _parse_settled_at


def test_naive_timestamps_are_treated_as_utc():
    assert _parse_settled_at("2026-08-23T09:20:00") == datetime(2026, 8, 23, 9, 20, tzinfo=UTC)


def test_aware_timestamps_keep_their_offset():
    parsed = _parse_settled_at("2026-08-23T09:20:00+00:00")
    assert parsed == datetime(2026, 8, 23, 9, 20, tzinfo=UTC)
    assert parsed.tzinfo is not None


def test_missing_or_unusable_values_fall_back_to_the_caller():
    """None means "no usable time reported"; the caller then stamps the clock."""
    assert _parse_settled_at(None) is None
    assert _parse_settled_at("") is None
    assert _parse_settled_at("not-a-timestamp") is None
    assert _parse_settled_at(1755940800) is None
