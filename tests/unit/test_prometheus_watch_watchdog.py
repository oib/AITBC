"""Watchdog coverage for ``aitbc prometheus alerts --watch`` (PROM-WATCH-WATCHDOG-1).

The unit used to ping ``WATCHDOG=1`` once at the end of each poll loop. Under
load a single iteration -- Prometheus query plus notify POSTs with retries --
ran past ``WatchdogSec=75`` and systemd SIGABRT'd the watcher (21 restarts on
hub during the 22 Oct OOM night; the ``status=6/ABRT`` journal lines).

The fix pings at the top of the iteration, after the query, and after every
notify attempt, and bounds the blocking calls. These tests stand in for
systemd: a real AF_UNIX datagram socket replaces ``NOTIFY_SOCKET`` (the ping
helper writes to it byte-for-byte as in production) and a fake monotonic clock
makes step durations deterministic. Assertions are on the *gaps between
pings* -- that silence is what systemd actually watches.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import httpx
import pytest
from click.testing import CliRunner

from aitbc_cli.commands import prometheus as prom

REPO = Path(__file__).resolve().parents[2]


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def _alert(name: str = "ServiceDown", state: str = "firing") -> dict[str, Any]:
    return {
        "labels": {"alertname": name, "severity": "critical"},
        "annotations": {"summary": f"{name} summary"},
        "state": state,
        "activeAt": "2026-10-01T10:00:00.500000000Z",
    }


@pytest.fixture(autouse=True)
def _close_alert_log_handlers():
    yield
    import logging

    alert_logger = logging.getLogger("aitbc.alert-events")
    for handler in list(alert_logger.handlers):
        handler.close()
        alert_logger.removeHandler(handler)


def _drain(sock: socket.socket) -> list[bytes]:
    datagrams = []
    while True:
        try:
            datagrams.append(sock.recv(64))
        except BlockingIOError:
            return datagrams


@pytest.fixture
def harness(monkeypatch, tmp_path):
    """Drive the watch loop with scripted polls, a fake clock, and a real
    datagram socket standing in for systemd's NOTIFY_SOCKET.

    Returns (run, clock, ping_times, calls) where run() invokes the command
    and afterwards drains the socket; ping_times holds the fake-clock instant
    of every _sd_notify_watchdog() call; calls records the timeout kwarg seen
    by the httpx.post fake.
    """
    clock = _Clock()
    ping_times: list[float] = []
    calls: dict[str, list[Any]] = {"post_timeouts": [], "posts": []}

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock_path = tmp_path / "notify.sock"
    sock.bind(str(sock_path))
    sock.setblocking(False)
    monkeypatch.setenv("NOTIFY_SOCKET", str(sock_path))

    monkeypatch.setattr(prom.time, "monotonic", clock)
    monkeypatch.setattr(prom, "configure_logging", lambda **kwargs: None)

    real_ping = prom._sd_notify_watchdog

    def spy() -> None:
        ping_times.append(clock.now)
        real_ping()

    monkeypatch.setattr(prom, "_sd_notify_watchdog", spy)

    def run(
        polls: list[list[dict[str, Any]] | None],
        *,
        fetch_seconds: float = 0.0,
        post_seconds: float = 0.0,
        notify_urls: tuple[str, ...] = (),
    ) -> Any:
        queue = list(polls)

        def fake_get(url, path, params=None, timeout=10):
            clock.advance(fetch_seconds)
            item = queue.pop(0)
            return {} if item is None else {"status": "success", "data": {"alerts": item}}

        def fake_post(url, json=None, headers=None, timeout=None):
            clock.advance(post_seconds)
            calls["post_timeouts"].append(timeout)
            calls["posts"].append(url)

            class _Resp:
                def raise_for_status(self):
                    return None

            return _Resp()

        def fake_sleep(_seconds):
            if not queue:
                raise KeyboardInterrupt

        monkeypatch.setattr(prom, "_prometheus_get", fake_get)
        monkeypatch.setattr(prom.httpx, "post", fake_post)
        monkeypatch.setattr(prom.time, "sleep", fake_sleep)

        extra = [arg for u in notify_urls for arg in ("--notify-url", u)]
        log = tmp_path / "alerts.log"
        result = CliRunner().invoke(
            prom.prometheus,
            ["alerts", "--watch", "--interval", "0", "--alert-log", str(log), *extra],
            obj={"output_format": "table", "config": None},
        )
        return result, _drain(sock)

    yield run, clock, ping_times, calls
    sock.close()


def _gaps(times: list[float]) -> list[float]:
    return [b - a for a, b in zip(times, times[1:], strict=False)]


def test_pings_between_steps_never_leave_a_75s_silence(harness) -> None:
    """One iteration totalling ~120s (> old WatchdogSec=75) still pings:
    top-of-loop, after the query, after each notify attempt."""
    run, clock, ping_times, _ = harness
    result, datagrams = run(
        [[_alert()]],
        fetch_seconds=40.0,
        post_seconds=40.0,
        notify_urls=("https://ops.example/hook",),
    )
    assert result.exit_code == 0, result.output
    # Every datagram the loop emitted is a real WATCHDOG=1 ping on the socket.
    assert datagrams and all(d == b"WATCHDOG=1" for d in datagrams)
    assert len(datagrams) == len(ping_times)
    # The old code pinged once per iteration: a 120s+ iteration was one giant
    # silent gap > 75s. Now every consecutive gap sits under the old window.
    assert max(_gaps(ping_times)) <= 40.0
    # Top-of-loop ping exists: the first ping precedes the query, not after it.
    assert ping_times[0] == 0.0


def test_a_stall_longer_than_the_window_is_detectable(harness) -> None:
    """A wedged step stops the ping stream for longer than WatchdogSec=300 --
    the silence systemd uses to kill a truly hung watcher."""
    run, clock, ping_times, _ = harness
    # Every poll's fetch is a 400s wedge: the gap between the ping at the top
    # of the iteration and the ping after the query is the hang detection
    # window.
    result, datagrams = run([[_alert()], []], fetch_seconds=400.0)
    assert result.exit_code == 0, result.output
    assert max(_gaps(ping_times)) >= 300.0
    # And the loop still pinged before and after the stalled steps: a hang
    # silence, not a dead stream.
    assert len(ping_times) >= 4
    assert datagrams and all(d == b"WATCHDOG=1" for d in datagrams)


def test_query_and_notify_calls_carry_explicit_timeouts(harness, monkeypatch) -> None:
    """The query GET wraps its budget into an httpx.Timeout with a capped
    connect phase; every notify POST carries _NOTIFY_TIMEOUT."""
    _, clock, _, calls = harness

    get_timeouts: list[Any] = []

    def fake_httpx_get(url, params=None, timeout=None):
        get_timeouts.append(timeout)
        clock.advance(1.0)

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"status": "success", "data": {"alerts": []}}

        return _Resp()

    def fake_sleep(_seconds):
        raise KeyboardInterrupt

    # Do not fake _prometheus_get here -- its Timeout wrapping is under test.
    monkeypatch.setattr(prom.httpx, "get", fake_httpx_get)
    monkeypatch.setattr(prom.time, "sleep", fake_sleep)
    result = CliRunner().invoke(
        prom.prometheus,
        ["alerts", "--watch", "--interval", "0"],
        obj={"output_format": "table", "config": None},
    )
    assert result.exit_code == 0, result.output
    assert get_timeouts, "httpx.get was never called"
    t = get_timeouts[0]
    assert isinstance(t, httpx.Timeout)
    assert float(t.connect) <= 5.0
    assert float(t.read) <= 10.0


def test_notify_retry_spending_stops_at_the_budget(harness, monkeypatch) -> None:
    """Three URLs x 40s attempts would run ~120s; the 60s notify budget lets
    two POSTs land (t=40, t=80) and skips the third as a counted error."""
    _, clock, _, calls = harness
    from aitbc_cli.commands.prometheus import _notify

    def slow_post(url, json=None, headers=None, timeout=None):
        calls["posts"].append(url)
        calls["post_timeouts"].append(timeout)
        clock.advance(40.0)

        class _Resp:
            def raise_for_status(self):
                return None

        return _Resp()

    monkeypatch.setattr(prom.httpx, "post", slow_post)
    stats: dict[str, Any] = {}
    _notify(
        ("https://a.example", "https://b.example", "https://c.example"),
        {"event": "test"},
        stats,
    )
    # attempts: a@t=0 posts (lands t=40), b@t=40 posts (lands t=80), c@t=80 is
    # over the 60s deadline and is counted, not posted.
    assert len(calls["posts"]) == 2
    assert stats.get("notify_errors") == 1
    for t in calls["post_timeouts"]:
        assert isinstance(t, httpx.Timeout)
        assert float(t.read) <= 5.0
        assert float(t.connect) <= 3.0
