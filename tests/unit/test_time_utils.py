"""Unit tests for aitbc.utils.time_utils additional functions."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from aitbc.utils.time_utils import (
    Timer,
    format_time_ago,
    format_time_in,
    get_deadline_remaining,
    get_end_of_day,
    get_end_of_month,
    get_end_of_week,
    get_start_of_day,
    get_start_of_month,
    get_start_of_week,
    get_time_since,
    get_time_until,
    get_timezone_offset,
    is_business_hours,
    is_deadline_passed,
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

    def test_get_start_of_week_normalizes_to_day_boundary(self):
        # SHARED-TIME-NAIVE-1 (#1438): week helpers must match the day/month
        # siblings' contract — Monday 00:00:00, not Monday at time-of-day.
        dt = datetime(2024, 6, 12, 15, 30, 45, 123456, tzinfo=UTC)  # Wednesday
        start = get_start_of_week(dt)
        assert start == datetime(2024, 6, 10, 0, 0, 0, 0, tzinfo=UTC)

    def test_get_end_of_week_normalizes_to_day_boundary(self):
        dt = datetime(2024, 6, 12, 15, 30, 45, tzinfo=UTC)  # Wednesday
        end = get_end_of_week(dt)
        assert end == datetime(2024, 6, 16, 23, 59, 59, 999999, tzinfo=UTC)

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


class TestNaiveDatetimeTolerance:
    """SHARED-TIME-NAIVE-1 (#1438): comparison helpers treat naive datetimes
    as UTC (the module convention) instead of raising TypeError."""

    def test_get_time_until_naive(self):
        future = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
        delta = get_time_until(future)
        assert timedelta(minutes=59) < delta <= timedelta(hours=1)

    def test_get_time_since_naive(self):
        past = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        delta = get_time_since(past)
        assert timedelta(hours=1) <= delta < timedelta(hours=1, minutes=1)

    def test_is_deadline_passed_naive(self):
        assert is_deadline_passed(datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)) is True
        assert is_deadline_passed(datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)) is False

    def test_get_deadline_remaining_naive(self):
        deadline = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=30)
        remaining = get_deadline_remaining(deadline)
        assert 0 < remaining <= 30

    def test_format_time_ago_naive(self):
        past = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
        assert format_time_ago(past) == "2 hours ago"

    def test_format_time_in_naive(self):
        future = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2)
        assert format_time_in(future).startswith("in ")
        assert "hour" in format_time_in(future)

    def test_sleep_until_naive_past_returns_immediately(self):
        # A naive past datetime must not raise; it simply does not sleep.
        sleep_until(datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1))

    def test_retry_until_deadline_naive(self):
        calls = []

        def always_false():
            calls.append(1)
            return False

        deadline = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        assert retry_until_deadline(always_false, deadline, interval=0) is False
        assert calls == []


class TestExponentialBackoff:
    """AUDIT-RETRY (#1576): shared backoff helper used by daemon reconnect loops."""

    def test_delay_grows_exponentially(self):
        from aitbc.utils.time_utils import ExponentialBackoff

        backoff = ExponentialBackoff(base_delay=1.0, max_delay=100.0, jitter=0.0)
        delays = [backoff.next_delay() for _ in range(5)]
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]
        assert backoff.attempts == 5

    def test_delay_capped_at_max(self):
        from aitbc.utils.time_utils import ExponentialBackoff

        backoff = ExponentialBackoff(base_delay=1.0, max_delay=10.0, jitter=0.0)
        delays = [backoff.next_delay() for _ in range(10)]
        assert all(d <= 10.0 for d in delays)
        assert delays[-1] == 10.0

    def test_jitter_stays_within_bounds(self):
        from aitbc.utils.time_utils import ExponentialBackoff

        backoff = ExponentialBackoff(base_delay=10.0, max_delay=100.0, jitter=0.5)
        for attempt in range(50):
            expected = min(10.0 * (2.0**attempt), 100.0)
            delay = backoff.next_delay()
            assert expected * 0.5 <= delay <= expected * 1.5

    def test_reset_clears_attempts(self):
        from aitbc.utils.time_utils import ExponentialBackoff

        backoff = ExponentialBackoff(base_delay=1.0, max_delay=100.0, jitter=0.0)
        backoff.next_delay()
        backoff.next_delay()
        backoff.reset()
        assert backoff.attempts == 0
        assert backoff.next_delay() == 1.0

    def test_current_delay_does_not_advance(self):
        from aitbc.utils.time_utils import ExponentialBackoff

        backoff = ExponentialBackoff(base_delay=2.0, max_delay=100.0, jitter=0.0)
        assert backoff.current_delay() == 2.0
        assert backoff.attempts == 0
        assert backoff.next_delay() == 2.0
        assert backoff.current_delay() == 4.0
