"""#2589: ``aitbc start|stop|restart`` must keep the single-document stdout
contract and survive a hung systemctl unit.

- ``--dry-run`` echoed ``would run: systemctl ...`` unconditionally, so
  ``--dry-run --output json`` stdout was not parseable JSON.
- ``subprocess.run(..., timeout=120)`` raised ``TimeoutExpired`` uncaught,
  ending the loop mid-wave: units already restarted were never listed and
  later units were never attempted.

Pins: json dry-run parses as one document; a timeout on unit b yields
results for a, b (timeout) and c; a timeout resolving role services aborts
cleanly instead of tracebacking.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import control as control_mod


@pytest.fixture
def runner():
    return CliRunner()


def _run_with_timeout(services, timeouts, calls=None):
    """subprocess.run side_effect: is-enabled answers installed for all
    ``services``; action commands record in ``calls`` and raise
    TimeoutExpired for units named in ``timeouts``."""
    recorded: list = calls if calls is not None else []

    def _run(cmd, **kw):
        res = MagicMock()
        res.stderr = ""
        res.stdout = ""
        if cmd[:2] == ["systemctl", "is-enabled"]:
            res.returncode = 0
            res.stdout = "enabled\n"
            return res
        recorded.append(cmd)
        if cmd[-1] in timeouts:
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 120))
        res.returncode = 0
        res.stdout = "ok"
        return res

    return _run


def _invoke(runner, command, argv, fmt="json", services=None, timeouts=None, calls=None):
    services = services or ["aitbc-a.service", "aitbc-b.service", "aitbc-c.service"]
    with (
        patch.object(control_mod, "_role_services", return_value=services),
        patch.object(control_mod, "_systemctl_prefix", return_value=[]),
        patch.object(
            control_mod.subprocess,
            "run",
            side_effect=_run_with_timeout(services, timeouts or set(), calls),
        ),
    ):
        return runner.invoke(command, argv, obj={"output_format": fmt})


def test_json_dry_run_stdout_is_single_document(runner):
    result = _invoke(runner, control_mod.restart, ["--dry-run"])
    assert result.exit_code == 0
    assert "would run:" not in result.output
    doc = json.loads(result.output)
    assert doc["action"] == "restart"
    assert [s["status"] for s in doc["services"]] == ["dry-run"] * 3


def test_timeout_on_one_unit_reports_all_attempted(runner):
    calls: list = []
    result = _invoke(
        runner,
        control_mod.restart,
        [],
        timeouts={"aitbc-b.service"},
        calls=calls,
    )
    # every unit was attempted, not just up to the hung one
    assert [c[-1] for c in calls] == [
        "aitbc-a.service",
        "aitbc-b.service",
        "aitbc-c.service",
    ]
    # json abort emits the error document as the only stdout document
    doc = json.loads(result.output)
    assert doc["error"] == "CLIError"
    statuses = {s["service"]: s["status"] for s in doc["services"]}
    assert statuses == {
        "aitbc-a.service": "ok",
        "aitbc-b.service": "timeout",
        "aitbc-c.service": "ok",
    }
    assert "aitbc-b.service" in doc["message"]
    assert result.exit_code != 0


def test_human_timeout_lists_unit_and_continues(runner):
    result = _invoke(
        runner,
        control_mod.restart,
        [],
        fmt="table",
        timeouts={"aitbc-b.service"},
    )
    assert result.exit_code != 0
    assert "aitbc-b.service" in result.output
    assert "timeout" in result.output


def test_role_services_timeout_aborts_cleanly(runner):
    def _boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 30))

    with (
        patch.object(control_mod, "_systemctl_prefix", return_value=[]),
        patch.object(control_mod.subprocess, "run", side_effect=_boom),
    ):
        result = runner.invoke(control_mod.start, [], obj={"output_format": "json"})
    assert result.exit_code != 0
    assert "TimeoutExpired" not in result.output
    assert "Traceback" not in result.output
    doc = json.loads(result.output[result.output.find("{") :])
    assert doc["error"] == "CLIError"
