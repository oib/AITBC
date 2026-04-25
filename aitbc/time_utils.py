"""
Time utilities for AITBC
Provides timestamp helpers, duration helpers, timezone handling, and deadline calculations
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Union
import time


def get_utc_now() -> datetime:
    """Get current UTC datetime"""
    return datetime.now(timezone.utc)


def get_timestamp_utc() -> float:
    """Get current UTC timestamp"""
    return time.time()


def format_iso8601(dt: Optional[datetime] = None) -> str:
    """Format datetime as ISO 8601 string in UTC"""
    if dt is None:
        dt = get_utc_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def parse_iso8601(iso_string: str) -> datetime:
    """Parse ISO 8601 string to datetime"""
    dt = datetime.fromisoformat(iso_string)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def timestamp_to_iso(timestamp: float) -> str:
    """Convert timestamp to ISO 8601 string"""
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def iso_to_timestamp(iso_string: str) -> float:
    """Convert ISO 8601 string to timestamp"""
    dt = parse_iso8601(iso_string)
    return dt.timestamp()


def format_duration(seconds: Union[int, float]) -> str:
    """Format duration in seconds to human-readable string"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h"
    else:
        days = int(seconds / 86400)
        return f"{days}d"


def format_duration_precise(seconds: Union[int, float]) -> str:
    """Format duration with precise breakdown"""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")
    
    return " ".join(parts)


def parse_duration(duration_str: str) -> float:
    """Parse duration string to seconds"""
    duration_str = duration_str.strip().lower()
    
    if duration_str.endswith('s'):
        return float(duration_str[:-1])
    elif duration_str.endswith('m'):
        return float(duration_str[:-1]) * 60
    elif duration_str.endswith('h'):
        return float(duration_str[:-1]) * 3600
    elif duration_str.endswith('d'):
        return float(duration_str[:-1]) * 86400
    else:
        return float(duration_str)


def add_duration(dt: datetime, duration: Union[str, timedelta]) -> datetime:
    """Add duration to datetime"""
    if isinstance(duration, str):
        duration = timedelta(seconds=parse_duration(duration))
    return dt + duration


def subtract_duration(dt: datetime, duration: Union[str, timedelta]) -> datetime:
    """Subtract duration from datetime"""
    if isinstance(duration, str):
        duration = timedelta(seconds=parse_duration(duration))
    return dt - duration


def get_time_until(dt: datetime) -> timedelta:
    """Get time until a future datetime"""
    now = get_utc_now()
    return dt - now


def get_time_since(dt: datetime) -> timedelta:
    """Get time since a past datetime"""
    now = get_utc_now()
    return now - dt


def calculate_deadline(duration: Union[str, timedelta], from_dt: Optional[datetime] = None) -> datetime:
    """Calculate deadline from duration"""
    if from_dt is None:
        from_dt = get_utc_now()
    return add_duration(from_dt, duration)


def is_deadline_passed(deadline: datetime) -> bool:
    """Check if deadline has passed"""
    return get_utc_now() >= deadline


def get_deadline_remaining(deadline: datetime) -> float:
    """Get remaining seconds until deadline"""
    delta = deadline - get_utc_now()
    return max(0, delta.total_seconds())


def format_time_ago(dt: datetime) -> str:
    """Format datetime as "time ago" string"""
    delta = get_time_since(dt)
    seconds = delta.total_seconds()
    
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days > 1 else ''} ago"
    else:
        weeks = int(seconds / 604800)
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"


def format_time_in(dt: datetime) -> str:
    """Format datetime as "time in" string"""
    delta = get_time_until(dt)
    seconds = delta.total_seconds()
    
    if seconds < 0:
        return format_time_ago(dt)
    
    if seconds < 60:
        return "in a moment"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"in {minutes} minute{'s' if minutes > 1 else ''}"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"in {hours} hour{'s' if hours > 1 else ''}"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"in {days} day{'s' if days > 1 else ''}"
    else:
        weeks = int(seconds / 604800)
        return f"in {weeks} week{'s' if weeks > 1 else ''}"


def to_timezone(dt: datetime, tz_name: str) -> datetime:
    """Convert datetime to specific timezone"""
    try:
        import pytz
        tz = pytz.timezone(tz_name)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz)
    except ImportError:
        raise ImportError("pytz is required for timezone conversion. Install with: pip install pytz")
    except Exception as e:
        raise ValueError(f"Failed to convert timezone: {e}")


def get_timezone_offset(tz_name: str) -> timedelta:
    """Get timezone offset from UTC"""
    try:
        import pytz
        tz = pytz.timezone(tz_name)
        now = datetime.now(timezone.utc)
        offset = tz.utcoffset(now)
        return offset if offset else timedelta(0)
    except ImportError:
        raise ImportError("pytz is required for timezone operations. Install with: pip install pytz")


def is_business_hours(dt: Optional[datetime] = None, start_hour: int = 9, end_hour: int = 17, timezone: str = "UTC") -> bool:
    """Check if datetime is within business hours"""
    if dt is None:
        dt = get_utc_now()
    
    try:
        import pytz
        tz = pytz.timezone(timezone)
        dt_local = dt.astimezone(tz)
        return start_hour <= dt_local.hour < end_hour
    except ImportError:
        raise ImportError("pytz is required for business hours check. Install with: pip install pytz")


def get_start_of_day(dt: Optional[datetime] = None) -> datetime:
    """Get start of day (00:00:00) for given datetime"""
    if dt is None:
        dt = get_utc_now()
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def get_end_of_day(dt: Optional[datetime] = None) -> datetime:
    """Get end of day (23:59:59) for given datetime"""
    if dt is None:
        dt = get_utc_now()
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def get_start_of_week(dt: Optional[datetime] = None) -> datetime:
    """Get start of week (Monday) for given datetime"""
    if dt is None:
        dt = get_utc_now()
    return dt - timedelta(days=dt.weekday())


def get_end_of_week(dt: Optional[datetime] = None) -> datetime:
    """Get end of week (Sunday) for given datetime"""
    if dt is None:
        dt = get_utc_now()
    return dt + timedelta(days=(6 - dt.weekday()))


def get_start_of_month(dt: Optional[datetime] = None) -> datetime:
    """Get start of month for given datetime"""
    if dt is None:
        dt = get_utc_now()
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def get_end_of_month(dt: Optional[datetime] = None) -> datetime:
    """Get end of month for given datetime"""
    if dt is None:
        dt = get_utc_now()
    if dt.month == 12:
        next_month = dt.replace(year=dt.year + 1, month=1, day=1)
    else:
        next_month = dt.replace(month=dt.month + 1, day=1)
    return next_month - timedelta(seconds=1)


def sleep_until(dt: datetime) -> None:
    """Sleep until a specific datetime"""
    now = get_utc_now()
    if dt > now:
        sleep_seconds = (dt - now).total_seconds()
        time.sleep(sleep_seconds)


def retry_until_deadline(func, deadline: datetime, interval: float = 1.0) -> bool:
    """Retry a function until deadline is reached"""
    while not is_deadline_passed(deadline):
        try:
            result = func()
            if result:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


class Timer:
    """Simple timer context manager for measuring execution time"""
    
    def __init__(self):
        """Initialize timer"""
        self.start_time = None
        self.end_time = None
        self.elapsed = None
    
    def __enter__(self):
        """Start timer"""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timer"""
        self.end_time = time.time()
        self.elapsed = self.end_time - self.start_time
    
    def get_elapsed(self) -> Optional[float]:
        """Get elapsed time in seconds"""
        if self.elapsed is not None:
            return self.elapsed
        elif self.start_time is not None:
            return time.time() - self.start_time
        return None
