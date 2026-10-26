"""WATCHER-REEMIT-1: a watcher restart must not re-emit active alerts.

The firing map is persisted beside the alert log; a new process
hydrates it and only emits genuine state changes.
"""

import json
from datetime import UTC, datetime

from aitbc_cli.commands.prometheus import _load_firing_state, _save_firing_state


ALERT = {"labels": {"alertname": "X", "instance": "n0:9009"}, "state": "firing"}


def _firing():
    return {"id1": {"alert": ALERT, "silenced": False, "last_notify": None}}


def test_round_trip(tmp_path):
    p = tmp_path / "alerts.log.state"
    _save_firing_state(str(p), _firing())
    loaded = _load_firing_state(str(p))
    assert loaded["id1"]["alert"]["labels"]["alertname"] == "X"
    assert loaded["id1"]["silenced"] is False
    assert loaded["id1"]["last_notify"] is None


def test_restart_suppresses_reemit(tmp_path):
    """Simulated restart: run1 saves state; run2 loads it — the same
    alert-id must read as already-known (firing.get() is not None, so
    the emit branch is skipped)."""
    p = tmp_path / "alerts.log.state"
    run1 = _firing()
    _save_firing_state(str(p), run1)
    run2 = _load_firing_state(str(p))
    # The emit loop checks `state is None` before emitting — hydrated
    # state must look identical to an in-memory tracked alert.
    assert run2.get("id1") is not None
    # And it must carry the alert record for a later resolve event.
    assert run2["id1"]["alert"] == ALERT


def test_missing_and_corrupt_state(tmp_path):
    assert _load_firing_state(str(tmp_path / "nope.state")) == {}
    bad = tmp_path / "alerts.log.state"
    bad.write_text("{not json")
    assert _load_firing_state(str(bad)) == {}
    bad.write_text(json.dumps({"version": 9, "firing": {"id1": {"alert": ALERT}}}))
    assert _load_firing_state(str(bad)) == {}


ALERT2 = {"labels": {"alertname": "Y", "instance": "n1:9009"}, "state": "firing"}


def test_restart_simulation_emits_nothing(tmp_path):
    """Full emit path: run1 emits 'firing', saves state; run2 (fresh
    process) loads it and emits nothing for the same alert. Stubbing
    the load makes run2 emit again — the mutation is bound."""
    from aitbc_cli.commands.prometheus import _emit_alert_changes

    state_file = str(tmp_path / "alerts.log.state")
    events: list[str] = []
    run1 = _load_firing_state(state_file)
    _emit_alert_changes({"id1": ALERT2}, run1, [], 0.0, datetime.now(UTC), 0.0, True, lambda n, a, **k: events.append(n))
    _save_firing_state(state_file, run1)
    assert events == ["prometheus_alert_firing"]
    events.clear()
    run2 = _load_firing_state(state_file)
    _emit_alert_changes({"id1": ALERT2}, run2, [], 1.0, datetime.now(UTC), 0.0, True, lambda n, a, **k: events.append(n))
    assert events == []


def test_really_new_alert_still_emits_after_restart(tmp_path):
    from aitbc_cli.commands.prometheus import _emit_alert_changes

    state_file = str(tmp_path / "alerts.log.state")
    _save_firing_state(state_file, {"old": {"alert": ALERT, "silenced": False, "last_notify": None}})
    events: list[str] = []
    run2 = _load_firing_state(state_file)
    _emit_alert_changes(
        {"old": ALERT, "new": ALERT2}, run2, [], 0.0, datetime.now(UTC), 0.0, True, lambda n, a, **k: events.append(n)
    )
    assert events == ["prometheus_alert_firing"]


def test_watch_twice_no_reemit(tmp_path, monkeypatch):
    """Drive the real watch command twice — run2 must append nothing.
    Fails if the state load at the call site is stubbed (firing = {})
    or the save call is removed (state file never written)."""
    import time as _time

    from click.testing import CliRunner
    from aitbc_cli.commands.prometheus import alerts
    import aitbc_cli.commands.prometheus as prom

    raw = {"labels": {"alertname": "X", "instance": "n0", "severity": "warning"}, "state": "firing"}
    monkeypatch.setattr(
        prom,
        "_prometheus_get",
        lambda url, path: {"status": "success", "data": {"alerts": [raw]}},
    )

    class _Stop(Exception):
        pass

    monkeypatch.setattr(_time, "sleep", lambda s: (_ for _ in ()).throw(_Stop()))

    alert_log = str(tmp_path / "alerts.log")
    runner = CliRunner()
    args = ["--watch", "--prometheus-url", "http://x", "--alert-log", alert_log, "--interval", "1"]

    result1 = runner.invoke(alerts, args, obj={"output_format": "plain"})
    lines1 = [ln for ln in open(alert_log).read().splitlines() if ln.strip()]
    assert any('"prometheus_alert_firing"' in ln for ln in lines1), result1.output

    runner.invoke(alerts, args, obj={"output_format": "plain"})
    lines2 = [ln for ln in open(alert_log).read().splitlines() if ln.strip()]
    # prometheus_watch_started legitimately fires once per process; the
    # state-change events must not repeat.
    assert not any('"prometheus_alert_' in ln for ln in lines2[len(lines1) :]), (
        f"restart re-emitted alert events: {lines2[len(lines1) :]}"
    )
