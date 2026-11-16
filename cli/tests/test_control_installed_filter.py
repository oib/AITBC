"""aitbc start|stop|restart must skip role-ideal units not installed on the host.

#2089 (SCENARIO-21): ``_role_services`` resolves the role-ideal manifest from
``scripts/monitoring/health_check.sh`` — shared by every node of that role.
A shop node legitimately lacks hub-side units (#1549), so ``--dry-run``
enumerated units systemd does not have and a real run failed on
``Unit not found``. ``_partition_installed`` splits the manifest by
``systemctl is-enabled`` (same predicate as ``service_is_installed`` in
health_check.sh); missing units get an explicit skip line and a ``skipped``
result entry instead of a systemctl action.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import control as control_mod


@pytest.fixture
def runner():
    return CliRunner()


def _mock_run(installed, rcs=None, calls=None):
    """subprocess.run side_effect: is-enabled answers per ``installed``;
    action commands are recorded in ``calls`` and return ``rcs`` codes."""
    rcs = rcs or {}
    recorded: list = calls if calls is not None else []

    def _run(cmd, **kw):
        res = MagicMock()
        res.stderr = ""
        res.stdout = ""
        if cmd[:2] == ["systemctl", "is-enabled"]:
            unit = cmd[-1]
            if unit in installed:
                res.returncode = 0
                res.stdout = "enabled\n"
            else:
                res.returncode = 1
                res.stdout = "not-found\n"
            return res
        recorded.append(cmd)
        svc = cmd[-1]
        rc = rcs.get(svc, 0)
        res.returncode = rc
        res.stdout = "" if rc else "ok"
        res.stderr = "unit failed" if rc else ""
        return res

    return _run


def _invoke(runner, command, argv=None, fmt="table", services=None, installed=None, rcs=None, calls=None):
    services = services or ["aitbc-here.service", "aitbc-absent.service"]
    installed = installed if installed is not None else set(services)
    with (
        patch.object(control_mod, "_role_services", return_value=services),
        patch.object(control_mod, "_systemctl_prefix", return_value=[]),
        patch.object(control_mod.subprocess, "run", side_effect=_mock_run(installed, rcs, calls)),
    ):
        return runner.invoke(command, argv or [], obj={"output_format": fmt})


# --- _partition_installed -----------------------------------------------------


def test_partition_installed_splits_manifest():
    services = ["aitbc-a.service", "aitbc-b.service", "aitbc-c.timer"]
    installed = {"aitbc-a.service", "aitbc-c.timer"}
    with patch.object(control_mod.subprocess, "run", side_effect=_mock_run(installed)):
        got_installed, got_missing = control_mod._partition_installed(services)
    assert got_installed == ["aitbc-a.service", "aitbc-c.timer"]
    assert got_missing == ["aitbc-b.service"]


def test_partition_installed_fails_open_without_systemctl():
    def _boom(cmd, **kw):
        raise OSError("systemctl missing")

    with patch.object(control_mod.subprocess, "run", side_effect=_boom):
        got_installed, got_missing = control_mod._partition_installed(["aitbc-a.service"])
    assert got_installed == ["aitbc-a.service"]
    assert got_missing == []


# --- control commands ---------------------------------------------------------


def test_dry_run_lists_only_installed_units(runner):
    calls: list = []
    result = _invoke(
        runner,
        control_mod.start,
        argv=["--dry-run"],
        services=["aitbc-here.service", "aitbc-absent.service"],
        installed={"aitbc-here.service"},
        calls=calls,
    )
    assert result.exit_code == 0
    assert "would run: systemctl start aitbc-here.service" in result.output
    assert "skipping aitbc-absent.service: unit not installed on this host" in result.output
    assert "would run: systemctl start aitbc-absent.service" not in result.output
    # dry-run never shells out to an action command at all
    assert calls == []


def test_real_run_never_calls_systemctl_for_missing_unit(runner):
    calls: list = []
    result = _invoke(
        runner,
        control_mod.restart,
        services=["aitbc-here.service", "aitbc-absent.service"],
        installed={"aitbc-here.service"},
        calls=calls,
    )
    assert result.exit_code == 0
    assert [c[-1] for c in calls] == ["aitbc-here.service"]
    assert "skipping aitbc-absent.service" in result.output


def test_missing_unit_marked_skipped_in_json_payload(runner):
    result = _invoke(
        runner,
        control_mod.stop,
        argv=["--dry-run"],
        fmt="json",
        services=["aitbc-here.service", "aitbc-absent.service"],
        installed={"aitbc-here.service"},
    )
    assert result.exit_code == 0
    # dry-run's "would run:" echo precedes the doc even in json mode
    # (pre-existing); the payload itself starts at the first '{'.
    doc = json.loads(result.output[result.output.find("{") :])
    statuses = {s["service"]: s["status"] for s in doc["services"]}
    assert statuses == {"aitbc-here.service": "dry-run", "aitbc-absent.service": "skipped"}


def test_all_installed_keeps_previous_behavior(runner):
    calls: list = []
    result = _invoke(
        runner,
        control_mod.start,
        services=["aitbc-a.service", "aitbc-b.service"],
        calls=calls,
    )
    assert result.exit_code == 0
    assert [c[-1] for c in calls] == ["aitbc-a.service", "aitbc-b.service"]
    assert "skipping" not in result.output
