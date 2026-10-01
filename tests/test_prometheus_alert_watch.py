"""``aitbc prometheus alerts --watch`` reports alert state changes and keeps a log of them (register SD-2).

The watcher used to report an alert once per process lifetime and never report that it had stopped, so a refire after
a resolve was silent, and the only trace of an alert was a line among the one-per-poll httpx lines of the service log.
On 2026-10-01 two ServiceDown alerts for stopped node exporters had been firing for three days unnoticed. These tests
pin the replacement: transitions in both directions, a dedicated events-only file, and an unanswered poll that never
reads as "everything resolved".
"""

from __future__ import annotations

import json
import logging
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

    def run(polls: list[list[dict[str, Any]] | None], *extra: str, alert_log: Path | None = None):
        queue = list(polls)

        def fake_get(url, path, params=None, timeout=10):
            item = queue.pop(0)
            return {} if item is None else {"status": "success", "data": {"alerts": item}}

        def fake_sleep(_seconds):
            if not queue:
                raise KeyboardInterrupt

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
    assert _kinds(logged) == ["prometheus_alert_firing"] == _kinds(printed)


def test_resolution_is_reported_with_how_long_the_alert_was_active(watch) -> None:
    _, logged, printed = watch([[_alert()], []])
    assert _kinds(logged) == ["prometheus_alert_firing", "prometheus_alert_resolved"] == _kinds(printed)
    resolved = logged[1]
    assert resolved["state"] == "resolved" and resolved["alertname"] == "ServiceDown"
    assert resolved["active_at"] == "2026-10-01T10:00:00.500000000Z"
    assert isinstance(resolved["duration_seconds"], int) and resolved["duration_seconds"] >= 0


def test_a_refire_after_a_resolve_is_reported_again(watch) -> None:
    """The old watcher kept every alert it had ever reported in a set, so this was silent."""
    _, logged, _ = watch([[_alert()], [], [_alert()]])
    assert _kinds(logged) == ["prometheus_alert_firing", "prometheus_alert_resolved", "prometheus_alert_firing"]


def test_a_pending_alert_is_not_an_event_until_it_fires(watch) -> None:
    _, logged, _ = watch([[_alert(state="pending")], [_alert(state="firing")]])
    assert _kinds(logged) == ["prometheus_alert_firing"]


def test_a_firing_alert_that_goes_pending_again_counts_as_resolved(watch) -> None:
    _, logged, _ = watch([[_alert()], [_alert(state="pending")]])
    assert _kinds(logged) == ["prometheus_alert_firing", "prometheus_alert_resolved"]


def test_label_sets_of_one_alertname_are_separate_alerts(watch) -> None:
    _, logged, _ = watch([[_alert(instance="hub"), _alert(instance="hub1")], [_alert(instance="hub")]])
    assert _kinds(logged) == ["prometheus_alert_firing", "prometheus_alert_firing", "prometheus_alert_resolved"]
    assert logged[-1]["labels"]["instance"] == "hub1"


def test_an_unanswered_poll_is_not_a_resolution(watch) -> None:
    """``_prometheus_get`` returns {} when Prometheus is unreachable; that must not read as "no alerts"."""
    result, logged, _ = watch([[_alert()], None, [_alert()]])
    assert result.exit_code == 0
    assert _kinds(logged) == ["prometheus_alert_firing"]


def test_an_alert_that_clears_during_an_outage_resolves_once_prometheus_answers(watch) -> None:
    _, logged, _ = watch([[_alert()], None, []])
    assert _kinds(logged) == ["prometheus_alert_firing", "prometheus_alert_resolved"]


def test_the_alert_log_holds_only_events_each_a_complete_json_line(watch) -> None:
    _, logged, _ = watch([[_alert()], [], [_alert()]])
    assert len(logged) == 3
    for event in logged:
        assert {"event", "alertname", "state", "severity", "summary", "labels", "timestamp"} <= set(event)
        assert event["severity"] == "critical" and event["summary"] == "ServiceDown summary"


def test_no_emit_silences_stdout_but_not_the_alert_log(watch) -> None:
    _, logged, printed = watch([[_alert()], []], "--no-emit")
    assert _kinds(logged) == ["prometheus_alert_firing", "prometheus_alert_resolved"]
    assert printed == []


def test_an_unwritable_alert_log_does_not_stop_the_watcher(watch, tmp_path) -> None:
    result, logged, printed = watch([[_alert()], []], alert_log=tmp_path / "missing-dir" / "alerts.log")
    assert result.exit_code == 0 and logged == []
    assert _kinds(printed) == ["prometheus_alert_firing", "prometheus_alert_resolved"]


def test_the_watch_unit_writes_the_alert_log_inside_a_path_its_sandbox_allows() -> None:
    """ProtectSystem=strict makes /var read-only: the unit needs the log directory in ReadWritePaths or the file is never written."""
    unit = (REPO / "scripts" / "monitoring" / "aitbc-prometheus-watch.service").read_text()
    exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    assert "--alert-log /var/log/aitbc/alerts.log" in exec_start
    read_write = next(line for line in unit.splitlines() if line.startswith("ReadWritePaths="))
    assert "/var/log/aitbc" in read_write.split("=", 1)[1].split()
