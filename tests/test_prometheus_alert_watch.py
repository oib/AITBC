"""``aitbc prometheus alerts --watch`` reports alert state changes and keeps a log of them (register SD-2).

The watcher used to report an alert once per process lifetime and never report that it had stopped, so a refire after
a resolve was silent, and the only trace of an alert was a line among the one-per-poll httpx lines of the service log.
On 2026-10-01 two ServiceDown alerts for stopped node exporters had been firing for three days unnoticed. These tests
pin the replacement: transitions in both directions, a dedicated events-only file, and an unanswered poll that never
reads as "everything resolved".
"""

from __future__ import annotations

import itertools
import json
import logging
import stat
import time
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import prometheus as prom

REPO = Path(__file__).resolve().parents[1]


def _alert(name: str = "ServiceDown", state: str = "firing", **labels: str) -> dict[str, Any]:
    return {
        "labels": {"alertname": name, "severity": "critical", **labels},
        "annotations": {"summary": f"{name} summary"},
        "state": state,
        "activeAt": "2026-10-01T10:00:00.500000000Z",
    }


@pytest.fixture(autouse=True)
def _close_alert_log_handlers():
    yield
    alert_logger = logging.getLogger("aitbc.alert-events")
    for handler in list(alert_logger.handlers):
        handler.close()
        alert_logger.removeHandler(handler)


@pytest.fixture
def watch(monkeypatch, tmp_path):
    """Run the watcher over scripted polls. A poll is a list of alerts, or None when Prometheus does not answer."""

    def run(
        polls: list[list[dict[str, Any]] | None],
        *extra: str,
        alert_log: Path | None = None,
        on_sleep: Any = None,
    ):
        queue = list(polls)

        def fake_get(url, path, params=None, timeout=10):
            item = queue.pop(0)
            return {} if item is None else {"status": "success", "data": {"alerts": item}}

        def fake_sleep(_seconds):
            if not queue:
                raise KeyboardInterrupt
            # Between-poll hook: lets a test change the silence file (or anything
            # else) while the watcher is "asleep" instead of only at start.
            if on_sleep is not None:
                on_sleep()

        monkeypatch.setattr(prom, "_prometheus_get", fake_get)
        monkeypatch.setattr(prom.time, "sleep", fake_sleep)
        monkeypatch.setattr(prom, "configure_logging", lambda **kwargs: None)
        log = alert_log or tmp_path / "alerts.log"
        result = CliRunner().invoke(
            prom.prometheus,
            ["alerts", "--watch", "--interval", "0", "--alert-log", str(log), *extra],
            obj={"output_format": "table", "config": None},
        )
        logged = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        printed = [json.loads(line) for line in result.output.splitlines() if line.startswith("{")]
        return result, logged, printed

    return run


def _kinds(events: list[dict[str, Any]]) -> list[str]:
    return [e["event"] for e in events]


def test_a_firing_alert_is_reported_once_however_long_it_fires(watch) -> None:
    result, logged, printed = watch([[_alert()], [_alert()], [_alert()]])
    assert result.exit_code == 0
    assert _kinds(logged) == ["prometheus_watch_started", "prometheus_alert_firing"] == _kinds(printed)


def test_resolution_is_reported_with_how_long_the_alert_was_active(watch) -> None:
    _, logged, printed = watch([[_alert()], []])
    assert (
        _kinds(logged)
        == ["prometheus_watch_started", "prometheus_alert_firing", "prometheus_alert_resolved"]
        == _kinds(printed)
    )
    resolved = logged[2]
    assert resolved["state"] == "resolved" and resolved["alertname"] == "ServiceDown"
    assert resolved["active_at"] == "2026-10-01T10:00:00.500000000Z"
    assert isinstance(resolved["duration_seconds"], int) and resolved["duration_seconds"] >= 0


def test_a_refire_after_a_resolve_is_reported_again(watch) -> None:
    """The old watcher kept every alert it had ever reported in a set, so this was silent."""
    _, logged, _ = watch([[_alert()], [], [_alert()]])
    assert _kinds(logged) == [
        "prometheus_watch_started",
        "prometheus_alert_firing",
        "prometheus_alert_resolved",
        "prometheus_alert_firing",
    ]
    assert logged[1]["via"] == "startup" and logged[3]["via"] == "transition"


def test_a_pending_alert_is_not_an_event_until_it_fires(watch) -> None:
    _, logged, _ = watch([[_alert(state="pending")], [_alert(state="firing")]])
    assert _kinds(logged) == ["prometheus_watch_started", "prometheus_alert_firing"]


def test_a_firing_alert_that_goes_pending_again_counts_as_resolved(watch) -> None:
    _, logged, _ = watch([[_alert()], [_alert(state="pending")]])
    assert _kinds(logged) == ["prometheus_watch_started", "prometheus_alert_firing", "prometheus_alert_resolved"]


def test_label_sets_of_one_alertname_are_separate_alerts(watch) -> None:
    _, logged, _ = watch([[_alert(instance="hub"), _alert(instance="hub1")], [_alert(instance="hub")]])
    assert _kinds(logged) == [
        "prometheus_watch_started",
        "prometheus_alert_firing",
        "prometheus_alert_firing",
        "prometheus_alert_resolved",
    ]
    assert logged[-1]["labels"]["instance"] == "hub1"


def test_an_unanswered_poll_is_not_a_resolution(watch) -> None:
    """``_prometheus_get`` returns {} when Prometheus is unreachable; that must not read as "no alerts"."""
    result, logged, _ = watch([[_alert()], None, [_alert()]])
    assert result.exit_code == 0
    assert _kinds(logged) == ["prometheus_watch_started", "prometheus_alert_firing"]


def test_an_alert_that_clears_during_an_outage_resolves_once_prometheus_answers(watch) -> None:
    _, logged, _ = watch([[_alert()], None, []])
    assert _kinds(logged) == ["prometheus_watch_started", "prometheus_alert_firing", "prometheus_alert_resolved"]


def test_the_alert_log_holds_only_events_each_a_complete_json_line(watch) -> None:
    _, logged, _ = watch([[_alert()], [], [_alert()]])
    assert len(logged) == 4
    for event in logged:
        assert {"event", "via", "timestamp", "timestamp_unix"} <= set(event)
        if event["event"] == "prometheus_watch_started":
            continue
        assert {"alertname", "state", "severity", "summary", "labels"} <= set(event)
        assert event["severity"] == "critical" and event["summary"] == "ServiceDown summary"


def test_no_emit_silences_stdout_but_not_the_alert_log(watch) -> None:
    _, logged, printed = watch([[_alert()], []], "--no-emit")
    assert _kinds(logged) == ["prometheus_watch_started", "prometheus_alert_firing", "prometheus_alert_resolved"]
    assert printed == []


def test_an_unwritable_alert_log_does_not_stop_the_watcher(watch, tmp_path) -> None:
    result, logged, printed = watch([[_alert()], []], alert_log=tmp_path / "missing-dir" / "alerts.log")
    assert result.exit_code == 0 and logged == []
    assert _kinds(printed) == ["prometheus_watch_started", "prometheus_alert_firing", "prometheus_alert_resolved"]


def test_the_watch_unit_writes_the_alert_log_inside_a_path_its_sandbox_allows() -> None:
    """ProtectSystem=strict makes /var read-only: the unit needs the log directory in ReadWritePaths or the file is never written."""
    unit = (REPO / "scripts" / "monitoring" / "aitbc-prometheus-watch.service").read_text()
    exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    assert "--alert-log /var/log/aitbc/alerts.log" in exec_start
    read_write = next(line for line in unit.splitlines() if line.startswith("ReadWritePaths="))
    assert "/var/log/aitbc" in read_write.split("=", 1)[1].split()


def test_the_watch_unit_loads_an_optional_env_file_and_runs_a_watchdog() -> None:
    """Tuning knobs live in /etc/aitbc/prometheus-watch.env; WatchdogSec restarts a hung loop, not just a crash."""
    unit = (REPO / "scripts" / "monitoring" / "aitbc-prometheus-watch.service").read_text()
    assert "EnvironmentFile=-/etc/aitbc/prometheus-watch.env" in unit
    assert any(line.startswith("WatchdogSec=") for line in unit.splitlines())


def _capture_notify(monkeypatch, fail_urls: set[str] | None = None) -> list[tuple[str, dict[str, Any]]]:
    """Stub ``httpx.post`` and collect (url, payload) pairs; ``fail_urls`` always raise."""
    sent: list[tuple[str, dict[str, Any]]] = []
    fail = fail_urls or set()

    class _Resp:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url, json=None, timeout=None):
        sent.append((url, json))
        if url in fail:
            raise prom.httpx.ConnectError("connection refused")
        return _Resp()

    monkeypatch.setattr(prom.httpx, "post", fake_post)
    return sent


def _write_silences(path: Path, entries: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(entries))


def test_every_event_is_posted_to_every_notify_url(watch, monkeypatch, tmp_path) -> None:
    sent = _capture_notify(monkeypatch)
    watch(
        [[_alert()], []],
        "--notify-url",
        "http://ops-a/hook",
        "--notify-url",
        "http://ops-b/hook",
        alert_log=tmp_path / "alerts.log",
    )
    events = {(url, payload["event"]) for url, payload in sent}
    for url in ("http://ops-a/hook", "http://ops-b/hook"):
        for event in ("prometheus_watch_started", "prometheus_alert_firing", "prometheus_alert_resolved"):
            assert (url, event) in events


def test_a_failing_notify_url_is_retried_once_and_never_interrupts_the_watch(watch, monkeypatch, tmp_path) -> None:
    sent = _capture_notify(monkeypatch, fail_urls={"http://ops-b/hook"})
    result, logged, _ = watch(
        [[_alert()]],
        "--notify-url",
        "http://ops-b/hook",
        "--notify-url",
        "http://ops-a/hook",
        alert_log=tmp_path / "alerts.log",
    )
    assert result.exit_code == 0
    assert _kinds(logged) == ["prometheus_watch_started", "prometheus_alert_firing"]
    # Failing URL: two attempts (initial + one retry) per event; good URL: one.
    assert len([s for s in sent if s[0] == "http://ops-b/hook"]) == 4
    assert len([s for s in sent if s[0] == "http://ops-a/hook"]) == 2


def test_a_silenced_alert_is_recorded_but_not_pushed(watch, monkeypatch, tmp_path) -> None:
    sent = _capture_notify(monkeypatch)
    silence_file = tmp_path / "silences.json"
    _write_silences(silence_file, [{"match": {"alertname": "ServiceDown"}, "reason": "exporter retired"}])
    _, logged, _ = watch(
        [[_alert()], [_alert()], []],
        "--notify-url",
        "http://ops-a/hook",
        "--silence-file",
        str(silence_file),
        alert_log=tmp_path / "alerts.log",
    )
    fired = next(e for e in logged if e["event"] == "prometheus_alert_firing")
    resolved = next(e for e in logged if e["event"] == "prometheus_alert_resolved")
    assert fired["silenced"] is True and fired["silence_reason"] == "exporter retired"
    assert resolved["silenced"] is True
    # Only the watcher's own lifecycle event was pushed; both alert transitions were muted.
    assert {p["event"] for _, p in sent} == {"prometheus_watch_started"}


def test_a_silence_matches_on_a_label_subset_and_leaves_other_labelsets_alone(watch, monkeypatch, tmp_path) -> None:
    sent = _capture_notify(monkeypatch)
    silence_file = tmp_path / "silences.json"
    _write_silences(silence_file, [{"match": {"alertname": "ServiceDown", "labels": {"instance": "hub1:9100"}}}])
    _, logged, _ = watch(
        [[_alert(instance="hub:9100"), _alert(instance="hub1:9100")]],
        "--notify-url",
        "http://ops-a/hook",
        "--silence-file",
        str(silence_file),
        alert_log=tmp_path / "alerts.log",
    )
    firings = [e for e in logged if e["event"] == "prometheus_alert_firing"]
    by_instance = {e["labels"]["instance"]: e for e in firings}
    assert by_instance["hub1:9100"]["silenced"] is True
    assert "silenced" not in by_instance["hub:9100"]
    pushed_firings = [p for _, p in sent if p["event"] == "prometheus_alert_firing"]
    assert [p["labels"]["instance"] for p in pushed_firings] == ["hub:9100"]


def test_an_expired_until_silences_nothing(watch, monkeypatch, tmp_path) -> None:
    sent = _capture_notify(monkeypatch)
    silence_file = tmp_path / "silences.json"
    _write_silences(
        silence_file,
        [{"match": {"alertname": "ServiceDown"}, "until": "2000-01-01T00:00:00Z", "reason": "old window"}],
    )
    _, logged, _ = watch(
        [[_alert()]],
        "--notify-url",
        "http://ops-a/hook",
        "--silence-file",
        str(silence_file),
        alert_log=tmp_path / "alerts.log",
    )
    fired = next(e for e in logged if e["event"] == "prometheus_alert_firing")
    assert "silenced" not in fired
    assert {p["event"] for _, p in sent} == {"prometheus_watch_started", "prometheus_alert_firing"}


def test_a_silence_removed_mid_run_refires_the_alert(watch, monkeypatch, tmp_path) -> None:
    sent = _capture_notify(monkeypatch)
    silence_file = tmp_path / "silences.json"
    _write_silences(silence_file, [{"match": {"alertname": "ServiceDown"}}])
    _, logged, _ = watch(
        [[_alert()], [_alert()]],
        "--notify-url",
        "http://ops-a/hook",
        "--silence-file",
        str(silence_file),
        alert_log=tmp_path / "alerts.log",
        on_sleep=lambda: silence_file.unlink(missing_ok=True),
    )
    kinds = _kinds(logged)
    assert kinds == ["prometheus_watch_started", "prometheus_alert_firing", "prometheus_alert_firing"]
    assert logged[1]["silenced"] is True
    assert logged[2]["via"] == "silence_expired" and "silenced" not in logged[2]
    assert [p["event"] for _, p in sent] == ["prometheus_watch_started", "prometheus_alert_firing"]


def test_an_empty_match_and_a_malformed_file_both_fail_open(watch, monkeypatch, tmp_path) -> None:
    sent = _capture_notify(monkeypatch)
    silence_file = tmp_path / "silences.json"
    _write_silences(silence_file, [{"match": {}, "reason": "silences nothing"}])
    _, logged, _ = watch(
        [[_alert()]],
        "--notify-url",
        "http://ops-a/hook",
        "--silence-file",
        str(silence_file),
        alert_log=tmp_path / "alerts.log",
    )
    assert "silenced" not in next(e for e in logged if e["event"] == "prometheus_alert_firing")

    silence_file.write_text("{ this is not json")
    _, logged, _ = watch(
        [[_alert()]],
        "--notify-url",
        "http://ops-a/hook",
        "--silence-file",
        str(silence_file),
        alert_log=tmp_path / "alerts2.log",
    )
    assert "silenced" not in next(e for e in logged if e["event"] == "prometheus_alert_firing")
    assert "prometheus_alert_firing" in {p["event"] for _, p in sent}


def test_a_still_firing_alert_is_reminded_on_the_interval(watch, monkeypatch, tmp_path) -> None:
    ticks = itertools.count(step=120)
    monkeypatch.setattr(prom.time, "monotonic", lambda: float(next(ticks)))
    _, logged, _ = watch(
        [[_alert()], [_alert()], [_alert()]],
        "--remind-interval",
        "60",
        alert_log=tmp_path / "alerts.log",
    )
    assert _kinds(logged) == [
        "prometheus_watch_started",
        "prometheus_alert_firing",
        "prometheus_alert_still_firing",
        "prometheus_alert_still_firing",
    ]
    assert all(e["state"] == "firing" for e in logged[1:])


def test_a_silenced_alert_is_not_reminded(watch, monkeypatch, tmp_path) -> None:
    ticks = itertools.count(step=120)
    monkeypatch.setattr(prom.time, "monotonic", lambda: float(next(ticks)))
    silence_file = tmp_path / "silences.json"
    _write_silences(silence_file, [{"match": {"alertname": "ServiceDown"}}])
    _, logged, _ = watch(
        [[_alert()], [_alert()], [_alert()]],
        "--remind-interval",
        "60",
        "--silence-file",
        str(silence_file),
        alert_log=tmp_path / "alerts.log",
    )
    assert _kinds(logged) == ["prometheus_watch_started", "prometheus_alert_firing"]


def test_reminder_clocks_restart_after_an_outage(watch, monkeypatch, tmp_path) -> None:
    """A reminder is only as honest as the data behind it; an unreachable poll resets the cadence."""
    ticks = itertools.count(step=120)
    monkeypatch.setattr(prom.time, "monotonic", lambda: float(next(ticks)))
    _, logged, _ = watch(
        [[_alert()], None, [_alert()]],
        "--remind-interval",
        "60",
        alert_log=tmp_path / "alerts.log",
    )
    assert _kinds(logged) == ["prometheus_watch_started", "prometheus_alert_firing"]


def test_the_metrics_file_reports_the_watchers_own_health(watch, tmp_path) -> None:
    metrics = tmp_path / "watch.prom"
    watch([[_alert()], []], "--metrics-file", str(metrics), alert_log=tmp_path / "alerts.log")
    content = metrics.read_text()
    assert "aitbc_prometheus_watch_poll_timestamp_seconds " in content
    assert "aitbc_prometheus_watch_prometheus_reachable 1" in content
    assert "aitbc_prometheus_watch_firing 0" in content
    assert "aitbc_prometheus_watch_notify_errors_total 0" in content


def test_the_metrics_file_is_world_readable_for_node_exporter(watch, tmp_path) -> None:
    # mkstemp creates 0600; without the widen, the prometheus user cannot read
    # the textfile and every scrape logs "permission denied" (seen on hub).
    metrics = tmp_path / "watch.prom"
    watch([[_alert()]], "--metrics-file", str(metrics), alert_log=tmp_path / "alerts.log")
    assert stat.S_IMODE(metrics.stat().st_mode) & 0o044 == 0o044


def test_the_metrics_file_marks_prometheus_unreachable(watch, tmp_path) -> None:
    metrics = tmp_path / "watch.prom"
    watch([None, [_alert()]], "--metrics-file", str(metrics), alert_log=tmp_path / "alerts.log")
    assert "aitbc_prometheus_watch_prometheus_reachable 1" in metrics.read_text()
    # A second run ending on a dead poll reports 0 instead.
    watch([[_alert()], None], "--metrics-file", str(metrics), alert_log=tmp_path / "alerts.log")
    assert "aitbc_prometheus_watch_prometheus_reachable 0" in metrics.read_text()


def test_an_unwritable_metrics_file_does_not_stop_the_watcher(watch, tmp_path) -> None:
    result, logged, _ = watch(
        [[_alert()]],
        "--metrics-file",
        str(tmp_path / "missing-dir" / "watch.prom"),
        alert_log=tmp_path / "alerts.log",
    )
    assert result.exit_code == 0
    assert _kinds(logged) == ["prometheus_watch_started", "prometheus_alert_firing"]


def _history_event(event: str, alertname: str = "ServiceDown", labels: dict[str, str] | None = None, **extra):
    record: dict[str, Any] = {
        "event": event,
        "alertname": alertname,
        "state": "resolved" if event == "prometheus_alert_resolved" else "firing",
        "severity": "critical",
        "labels": labels or {},
        "timestamp": "2026-10-02T10:00:00",
        "timestamp_unix": time.time(),
        "via": "transition",
    }
    record.update(extra)
    return record


def _history(tmp_path, lines: list[dict[str, Any]], *args: str, path: Path | None = None):
    log = path or tmp_path / "alerts.log"
    if path is None:
        log.write_text("".join(json.dumps(e) + "\n" for e in lines))
    result = CliRunner().invoke(
        prom.prometheus,
        ["alert-history", "--path", str(log), *args],
        obj={"output_format": "json", "config": None},
    )
    return result, json.loads(result.output)


def test_alert_history_replays_events_and_what_is_still_firing(tmp_path) -> None:
    result, out = _history(
        tmp_path,
        [
            _history_event("prometheus_alert_firing", "ServiceDown", {"instance": "a"}),
            _history_event("prometheus_alert_resolved", "ServiceDown", {"instance": "a"}),
            _history_event("prometheus_alert_firing", "RpcErrorsSpiking", {"instance": "b"}),
        ],
    )
    assert result.exit_code == 0
    assert out["scanned_events"] == 3 and out["matched_events"] == 3
    assert [a["alertname"] for a in out["firing_now"]] == ["RpcErrorsSpiking"]


def test_alert_history_filters_by_state_node_and_name(tmp_path) -> None:
    _, out = _history(
        tmp_path,
        [
            _history_event("prometheus_alert_firing", "ServiceDown", {"node": "hub"}),
            _history_event("prometheus_alert_firing", "ServiceDown", {"node": "node0"}, silenced=True),
            _history_event("prometheus_alert_resolved", "ServiceDown", {"node": "hub"}),
        ],
        "--state",
        "resolved",
    )
    assert out["matched_events"] == 1
    _, out = _history(
        tmp_path,
        [
            _history_event("prometheus_alert_firing", "ServiceDown", {"node": "hub"}),
            _history_event("prometheus_alert_firing", "ServiceDown", {"node": "node0"}, silenced=True),
        ],
        "--state",
        "silenced",
    )
    assert out["matched_events"] == 1
    _, out = _history(
        tmp_path,
        [
            _history_event("prometheus_alert_firing", "ServiceDown", {"node": "hub"}),
            _history_event("prometheus_alert_firing", "ServiceDown", {"node": "node0"}),
        ],
        "--node",
        "node0",
    )
    assert out["matched_events"] == 1 and out["firing_now"][0]["labels"]["node"] == "node0"


def test_alert_history_last_keeps_the_newest_matches(tmp_path) -> None:
    _, out = _history(
        tmp_path,
        [
            _history_event("prometheus_alert_firing", "A"),
            _history_event("prometheus_alert_firing", "B"),
            _history_event("prometheus_alert_firing", "C"),
        ],
        "--last",
        "2",
    )
    assert [e["alertname"] for e in out["events"]] == ["B", "C"]


def test_alert_history_on_a_missing_log_is_empty_not_an_error(tmp_path) -> None:
    result, out = _history(tmp_path, [], path=tmp_path / "never-written.log")
    assert result.exit_code == 0
    assert out["events"] == [] and out["firing_now"] == [] and out["scanned_events"] == 0


def test_alert_history_since_filters_events_but_not_firing_now(tmp_path) -> None:
    old = _history_event("prometheus_alert_firing", "ServiceDown")
    old["timestamp_unix"] = time.time() - 3 * 86400
    recent = _history_event("prometheus_alert_firing", "RpcErrorsSpiking")
    _, out = _history(tmp_path, [old, recent], "--since", "24h")
    # Only the recent event matches --since, but the old alert never resolved:
    # firing-now replays the whole stream, so it is still reported.
    assert out["matched_events"] == 1
    assert {a["alertname"] for a in out["firing_now"]} == {"ServiceDown", "RpcErrorsSpiking"}
