"""Tests for aitbc.utils.time_utils"""

from datetime import UTC, datetime, timedelta

from aitbc.utils.time_utils import (
    add_duration,
    calculate_deadline,
    format_duration,
    format_duration_precise,
    format_iso8601,
    format_time_ago,
    get_deadline_remaining,
    get_time_since,
    get_time_until,
    get_timestamp_utc,
    get_utc_now,
    is_deadline_passed,
    iso_to_timestamp,
    parse_duration,
    parse_iso8601,
    subtract_duration,
    timestamp_to_iso,
)


class TestBasicTime:
    def test_get_utc_now(self):
        dt = get_utc_now()
        assert dt.tzinfo is UTC

    def test_get_timestamp_utc(self):
        ts = get_timestamp_utc()
        assert isinstance(ts, float)
        assert ts > 0


class TestIsoFormatting:
    def test_format_iso8601_none(self):
        result = format_iso8601()
        assert result.endswith("+00:00")

    def test_format_iso8601_naive(self):
        dt = datetime(2024, 1, 1, 12, 0, 0)
        result = format_iso8601(dt)
        assert "+00:00" in result

    def test_format_iso8601_aware(self):
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = format_iso8601(dt)
        assert "+00:00" in result

    def test_parse_iso8601(self):
        dt = parse_iso8601("2024-01-01T12:00:00+00:00")
        assert dt.year == 2024
        assert dt.tzinfo is UTC

    def test_parse_iso8601_naive(self):
        dt = parse_iso8601("2024-01-01T12:00:00")
        assert dt.tzinfo is UTC

    def test_timestamp_to_iso(self):
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC).timestamp()
        result = timestamp_to_iso(ts)
        assert "2024-01-01" in result

    def test_iso_to_timestamp(self):
        ts = iso_to_timestamp("2024-01-01T12:00:00+00:00")
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        assert ts == dt.timestamp()


class TestDurationFormatting:
    def test_format_duration_seconds(self):
        assert format_duration(45) == "45s"

    def test_format_duration_minutes(self):
        assert format_duration(120) == "2m"

    def test_format_duration_hours(self):
        assert format_duration(7200) == "2h"

    def test_format_duration_days(self):
        assert format_duration(172800) == "2d"

    def test_format_duration_precise_all(self):
        result = format_duration_precise(90061)
        assert "1d" in result
        assert "1h" in result
        assert "1m" in result
        assert "1s" in result

    def test_format_duration_precise_seconds_only(self):
        assert format_duration_precise(45) == "45s"

    def test_parse_duration_seconds(self):
        assert parse_duration("30s") == 30.0

    def test_parse_duration_minutes(self):
        assert parse_duration("5m") == 300.0

    def test_parse_duration_hours(self):
        assert parse_duration("2h") == 7200.0

    def test_parse_duration_days(self):
        assert parse_duration("1d") == 86400.0

    def test_parse_duration_raw(self):
        assert parse_duration("100") == 100.0


class TestDateTimeArithmetic:
    def test_add_duration_string(self):
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = add_duration(dt, "1h")
        assert result.hour == 13

    def test_add_duration_timedelta(self):
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = add_duration(dt, timedelta(hours=2))
        assert result.hour == 14

    def test_subtract_duration_string(self):
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = subtract_duration(dt, "1h")
        assert result.hour == 11

    def test_subtract_duration_timedelta(self):
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = subtract_duration(dt, timedelta(hours=2))
        assert result.hour == 10

    def test_get_time_until(self):
        future = datetime.now(UTC) + timedelta(hours=1)
        delta = get_time_until(future)
        assert delta.total_seconds() > 0

    def test_get_time_since(self):
        past = datetime.now(UTC) - timedelta(hours=1)
        delta = get_time_since(past)
        assert delta.total_seconds() > 0


class TestDeadline:
    def test_calculate_deadline_from_now(self):
        deadline = calculate_deadline("1h")
        assert deadline > datetime.now(UTC)

    def test_calculate_deadline_from_dt(self):
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        deadline = calculate_deadline("1h", from_dt=base)
        assert deadline.hour == 13

    def test_is_deadline_passed_future(self):
        future = datetime.now(UTC) + timedelta(days=1)
        assert is_deadline_passed(future) is False

    def test_is_deadline_passed_past(self):
        past = datetime.now(UTC) - timedelta(days=1)
        assert is_deadline_passed(past) is True

    def test_get_deadline_remaining(self):
        future = datetime.now(UTC) + timedelta(hours=1)
        remaining = get_deadline_remaining(future)
        assert remaining > 0

    def test_get_deadline_remaining_past(self):
        past = datetime.now(UTC) - timedelta(hours=1)
        remaining = get_deadline_remaining(past)
        assert remaining == 0.0


class TestFormatTimeAgo:
    def test_time_ago_seconds(self):
        dt = datetime.now(UTC) - timedelta(seconds=30)
        result = format_time_ago(dt)
        assert result == "just now"

    def test_time_ago_minutes(self):
        dt = datetime.now(UTC) - timedelta(minutes=5)
        result = format_time_ago(dt)
        assert "5 minutes ago" == result

    def test_time_ago_hours(self):
        dt = datetime.now(UTC) - timedelta(hours=3)
        result = format_time_ago(dt)
        assert "3 hours ago" == result

    def test_time_ago_days(self):
        dt = datetime.now(UTC) - timedelta(days=2)
        result = format_time_ago(dt)
        assert "2 days ago" == result
