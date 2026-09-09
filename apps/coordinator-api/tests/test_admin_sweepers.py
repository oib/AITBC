"""Tests for the read-only sweeper report on the admin router.

The report exists because the sweepers are run_forever coroutines with no other
handle on them: the only externally visible difference between "enabled and
working" and "enabled and crashed out of its loop" is the task registry status,
so these tests pin how that status is classified.
"""

from coordinator_api.contexts.infrastructure.routers import admin


class _FakeRegistry:
    def __init__(self, statuses):
        self._statuses = statuses

    def get_task_status(self):
        return dict(self._statuses)


def _patch(monkeypatch, specs, statuses):
    import coordinator_api.core.lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "get_task_manager", lambda: _FakeRegistry(statuses))
    monkeypatch.setattr(admin, "_sweeper_specs", lambda: specs)
    monkeypatch.setattr(admin, "_extra_config", lambda name: {})


class _Sweeper:
    def __init__(self):
        self.interval_seconds = 60
        self.batch_size = 25
        self._session_factory = object()


def test_an_enabled_sweeper_that_finished_is_reported_degraded(monkeypatch):
    # A forever-loop that reports "completed" has stopped sweeping while the
    # config still claims it is on. That is the case this endpoint exists for.
    specs = [
        ("alive", lambda: True, _Sweeper, "still looping"),
        ("crashed", lambda: True, _Sweeper, "fell out of its loop"),
        ("never_started", lambda: True, _Sweeper, "enabled but absent from the registry"),
    ]
    _patch(monkeypatch, specs, {"alive": "running", "crashed": "completed"})

    report = admin.collect_sweeper_report()
    by_name = {entry["name"]: entry for entry in report["sweepers"]}

    assert by_name["alive"]["status"] == "running"
    assert by_name["alive"]["healthy"] is True
    assert by_name["crashed"]["status"] == "completed"
    assert by_name["crashed"]["healthy"] is False
    assert by_name["never_started"]["status"] == "not started"
    assert report["degraded"] == ["crashed", "never_started"]


def test_a_disabled_sweeper_is_not_degraded(monkeypatch):
    # Off on purpose is not a fault, and it must not read as one: the settlement
    # reconciler ships disabled by default.
    specs = [("off", lambda: False, _Sweeper, "opted out per deployment")]
    _patch(monkeypatch, specs, {})

    report = admin.collect_sweeper_report()
    entry = report["sweepers"][0]

    assert entry["enabled"] is False
    assert entry["status"] == "disabled"
    assert entry["healthy"] is True
    assert report["degraded"] == []
    # Config is still reported, so an operator can see what it would run with.
    assert entry["config"] == {"batch_size": 25, "interval_seconds": 60}


def test_background_tasks_outside_the_spec_table_are_still_listed(monkeypatch):
    # The registry holds whatever main.py started. A task this table does not
    # know about must surface rather than vanish from the report.
    _patch(monkeypatch, [("known", lambda: True, _Sweeper, "in the table")], {"known": "running", "mystery": "running"})

    report = admin.collect_sweeper_report()

    assert report["other_tasks"] == [{"name": "mystery", "status": "running"}]


def test_config_is_read_off_a_real_instance():
    # The point of constructing the sweeper is that env-resolved settings live
    # on the instance; private attributes are not part of the report.
    config = admin._sweeper_config(_Sweeper)

    assert config == {"batch_size": 25, "interval_seconds": 60}


def test_a_sweeper_that_cannot_be_constructed_does_not_break_the_report():
    class _Broken:
        def __init__(self):
            raise RuntimeError("no database")

    config = admin._sweeper_config(_Broken)

    assert "RuntimeError" in config["error"]


def test_the_real_spec_table_matches_the_tasks_main_starts():
    # Guards against a sweeper being added to main.py and silently missing here.
    names = {name for name, _, _, _ in admin._sweeper_specs()}

    assert names == {
        "escrow_settlement_reconciler",
        "zk_refund_sweeper",
        "acceptance_window_sweeper",
        "stuck_escrow_sweeper",
        "bond_slash_sweeper",
        "stale_miner_reaper",
        "stale_job_reaper",
    }


def test_the_acceptance_window_is_reported_even_though_it_is_not_on_the_instance():
    # sweeper_enabled() returns False when the window is zero, so the window is
    # the setting an operator asks about first; it lives in the acceptance
    # module, not on AcceptanceSweeper.
    extra = admin._extra_config("acceptance_window_sweeper")

    assert "acceptance_window_seconds" in extra
    assert admin._extra_config("stale_job_reaper") == {}
