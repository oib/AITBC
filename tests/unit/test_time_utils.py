"""Unit tests for aitbc.utils.time_utils additional functions."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from aitbc.utils.time_utils import (
    Timer,
    format_time_in,
    get_end_of_day,
    get_end_of_month,
    get_end_of_week,
    get_start_of_day,
    get_start_of_month,
    get_start_of_week,
    get_timezone_offset,
    is_business_hours,
    retry_until_deadline,
    sleep_until,
    to_timezone,
)


class TestTimer:
    def test_timer_elapsed_is_non_negative(self):
        with Timer() as timer:
            pass
        assert timer.elapsed is not None
        assert timer.elapsed >= 0.0

    def test_timer_get_elapsed_returns_value(self):
        with Timer() as timer:
            pass
        assert timer.get_elapsed() == timer.elapsed

    def test_timer_get_elapsed_when_running(self):
        timer = Timer()
        with timer:
            assert timer.get_elapsed() is not None
        assert timer.elapsed is not None


class TestRetryUntilDeadline:
    def test_returns_true_when_succeeds_immediately(self):
        deadline = datetime.now(UTC) + timedelta(seconds=1)
        assert retry_until_deadline(lambda: True, deadline, interval=0.01) is True

    def test_returns_true_after_failures(self):
        deadline = datetime.now(UTC) + timedelta(seconds=1)
        calls = [False, False, True]

        def func():
            return calls.pop(0)

        assert retry_until_deadline(func, deadline, interval=0.01) is True

    def test_returns_false_when_deadline_passes(self):
        deadline = datetime.now(UTC) + timedelta(seconds=0.05)
        assert retry_until_deadline(lambda: False, deadline, interval=0.01) is False

    def test_swallows_exceptions_and_retries(self):
        deadline = datetime.now(UTC) + timedelta(seconds=0.1)
        calls = [0]

        def func():
            calls[0] += 1
            if calls[0] < 2:
                raise RuntimeError("transient")
            return True

        assert retry_until_deadline(func, deadline, interval=0.01) is True


class TestSleepUntil:
    def test_sleeps_until_future_time(self):
        future = datetime.now(UTC) + timedelta(seconds=0.1)

        with patch("time.sleep") as mock_sleep:
            sleep_until(future)
            assert mock_sleep.called

    def test_does_not_sleep_for_past_time(self):
        past = datetime.now(UTC) - timedelta(seconds=1)

        with patch("time.sleep") as mock_sleep:
            sleep_until(past)
            mock_sleep.assert_not_called()


class TestTimeFormatting:
    def test_format_time_in_future(self):
        future = datetime.now(UTC) + timedelta(seconds=45)
        assert "in" in format_time_in(future)

    def test_format_time_in_past(self):
        past = datetime.now(UTC) - timedelta(seconds=45)
        assert format_time_in(past).startswith("in") is False


class TestDayAndWeekHelpers:
    def test_get_start_of_day(self):
        dt = datetime(2024, 6, 15, 12, 30, 45, 123456, tzinfo=UTC)
        start = get_start_of_day(dt)
        assert start.hour == 0
        assert start.minute == 0
        assert start.second == 0
        assert start.microsecond == 0

    def test_get_end_of_day(self):
        dt = datetime(2024, 6, 15, 12, 30, 45, tzinfo=UTC)
        end = get_end_of_day(dt)
        assert end.hour == 23
        assert end.minute == 59
        assert end.second == 59

    def test_get_start_of_week(self):
        dt = datetime(2024, 6, 12, tzinfo=UTC)  # Wednesday
        start = get_start_of_week(dt)
        assert start.weekday() == 0  # Monday

    def test_get_end_of_week(self):
        dt = datetime(2024, 6, 12, tzinfo=UTC)  # Wednesday
        end = get_end_of_week(dt)
        assert end.weekday() == 6  # Sunday

    def test_get_start_of_month(self):
        dt = datetime(2024, 6, 15, tzinfo=UTC)
        start = get_start_of_month(dt)
        assert start.day == 1

    def test_get_end_of_month(self):
        dt = datetime(2024, 2, 15, tzinfo=UTC)
        end = get_end_of_month(dt)
        assert end.day == 29


class TestTimezoneHelpers:
    def test_to_timezone_utc(self):
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        tz_dt = to_timezone(dt, "UTC")
        assert tz_dt.utcoffset() == timedelta(0)

    def test_to_timezone_naive_uses_utc(self):
        dt = datetime(2024, 6, 15, 12, 0, 0)
        tz_dt = to_timezone(dt, "UTC")
        assert tz_dt.utcoffset() == timedelta(0)

    def test_to_timezone_invalid_raises(self):
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        with pytest.raises(ValueError):
            to_timezone(dt, "invalid/timezone")

    def test_get_timezone_offset(self):
        offset = get_timezone_offset("UTC")
        assert offset == timedelta(0)

    def test_is_business_hours_default(self):
        dt = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        assert is_business_hours(dt, start_hour=9, end_hour=17, timezone="UTC") is True

    def test_is_business_hours_outside_hours(self):
        dt = datetime(2024, 6, 15, 20, 0, 0, tzinfo=UTC)
        assert is_business_hours(dt, start_hour=9, end_hour=17, timezone="UTC") is False
