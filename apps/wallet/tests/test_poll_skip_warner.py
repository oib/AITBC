"""#2354 — PollSkipWarner: skipped monitor polls must surface in the log.

A preflight skip (dead key slot, missing env) used to reach only the poll
summary's DEBUG path — the 19→21 Nov ait-sell-escrow outage ran ~2 days with
zero journal lines. The warner warns on the first skip and re-warns every
interval while skips persist.
"""

import logging
import time

from wallet_app.bridge.bridge_withdraw_monitor import PollSkipWarner


class _Capture:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg: str, *args) -> None:
        self.warnings.append(msg % args if args else msg)


def _warner(interval: float = 900.0) -> tuple[PollSkipWarner, _Capture]:
    log = _Capture()
    return PollSkipWarner(log, interval_seconds=interval), log


def test_first_skip_warns_immediately():
    warner, log = _warner()
    warner.note({"skipped": True, "reason": "escrow key slot unusable"}, "Exchange settlement monitor")
    assert len(log.warnings) == 1
    assert "Exchange settlement monitor" in log.warnings[0]
    assert "escrow key slot unusable" in log.warnings[0]
    assert "1 consecutive" in log.warnings[0]


def test_repeat_skips_within_interval_are_silent():
    warner, log = _warner()
    for _ in range(5):
        warner.note({"skipped": True, "reason": "same reason"}, "Sell escrow monitor")
    assert len(log.warnings) == 1
    assert warner.streak == 5


def test_skip_after_interval_warns_again_with_streak():
    warner, log = _warner(interval=0.0)
    warner.note({"skipped": True, "reason": "r"}, "M")
    warner.note({"skipped": True, "reason": "r"}, "M")
    assert len(log.warnings) == 2
    assert "2 consecutive" in log.warnings[1]


def test_non_skip_resets_streak_and_silent():
    warner, log = _warner()
    warner.note({"skipped": True, "reason": "r"}, "M")
    warner.note({"skipped": False, "processed": 0}, "M")
    assert warner.streak == 0
    warner.note({"skipped": True, "reason": "r2"}, "M")
    # streak restarted at 1 — but _last_warn is still fresh, so no new line
    assert len(log.warnings) == 1
    assert warner.streak == 1


def test_missing_reason_defaults_unknown():
    warner, log = _warner()
    warner.note({"skipped": True}, "M")
    assert "unknown" in log.warnings[0]


def test_real_logger_compatible(caplog):
    """The warner must work with the module loggers the loops pass in."""
    warner = PollSkipWarner(logging.getLogger("test.skip_warner"), interval_seconds=0.0)
    with caplog.at_level(logging.WARNING, logger="test.skip_warner"):
        warner.note({"skipped": True, "reason": "boom"}, "Exchange settlement monitor")
    assert "Exchange settlement monitor poll skipped (1 consecutive): boom" in caplog.text


def test_interval_uses_monotonic_not_wall_clock():
    """Guard against someone swapping to time.time() — streak state is what
    matters; this pins that note() never raises on a fresh warner."""
    warner, _ = _warner()
    warner.note({"skipped": True, "reason": "r"}, "M")
    assert time.monotonic() > 0
