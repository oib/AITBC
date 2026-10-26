"""control start/stop/restart must emit per-service results before aborting.

CLI-SWALLOW-SWEEP-2 (#570) follow-up: ``_control_services`` used to call
``abort()`` before ``output()``, so on a unit failure the per-service
results document was never emitted in any format. It now prints the
results doc first (stderr under json/yaml, so stdout keeps the single
abort() error document) and then aborts non-zero.
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


def _invoke_control(runner, command, argv=None, fmt="table", rcs=None):
    """Invoke a control command with systemctl stubbed.

    ``rcs`` maps service name -> systemctl returncode; services not in the
    map default to rc 0.
    """
    services = ["aitbc-a.service", "aitbc-b.service"]
    rcs = rcs or {}

    def _run(cmd, **kw):
        svc = cmd[-1]
        rc = rcs.get(svc, 0)
        res = MagicMock()
        res.returncode = rc
        res.stderr = "unit failed" if rc else ""
        res.stdout = "" if rc else "ok"
        return res

    with (
        patch.object(control_mod, "_role_services", return_value=services),
        patch.object(control_mod, "_systemctl_prefix", return_value=[]),
        patch.object(control_mod.subprocess, "run", side_effect=_run),
    ):
        return runner.invoke(command, argv or [], obj={"output_format": fmt})


# --- failure path: results emitted before the non-zero abort -----------------


def test_control_start_failed_unit_emits_results_table(runner):
    result = _invoke_control(runner, control_mod.start, rcs={"aitbc-a.service": 1, "aitbc-b.service": 1})
    assert result.exit_code != 0
    # Per-service results doc is emitted (not swallowed by the abort).
    assert "aitbc-a.service" in result.output
    assert "aitbc-b.service" in result.output
    assert "failed" in result.output


def test_control_start_partial_failure_emits_results_table(runner):
    result = _invoke_control(runner, control_mod.start, rcs={"aitbc-b.service": 1})
    assert result.exit_code != 0
    assert "aitbc-a.service" in result.output
    assert "aitbc-b.service" in result.output
    # Both statuses are visible in the emitted results doc.
    assert '"status": "ok"' in result.output
    assert '"status": "failed"' in result.output


def test_control_stop_failed_unit_emits_results(runner):
    result = _invoke_control(runner, control_mod.stop, rcs={"aitbc-a.service": 1})
    assert result.exit_code != 0
    assert "aitbc-a.service" in result.output


def test_control_restart_failed_unit_emits_results(runner):
    result = _invoke_control(runner, control_mod.restart, rcs={"aitbc-b.service": 1})
    assert result.exit_code != 0
    assert "aitbc-b.service" in result.output


def test_control_start_failed_unit_json_single_stdout_doc(runner):
    """--output json: ONE parseable doc; per-service statuses inside the error doc."""
    result = _invoke_control(runner, control_mod.start, fmt="json", rcs={"aitbc-a.service": 1})
    assert result.exit_code != 0
    # Whole terminal stream must decode as a single JSON document.
    start = result.output.find("{")
    assert start != -1, result.output
    doc = json.loads(result.output[start:])
    assert "error" in doc, result.output
    assert doc["exit_code"] != 0
    names = {s["service"]: s["status"] for s in doc["services"]}
    assert names["aitbc-a.service"] == "failed"
    assert names["aitbc-b.service"] == "ok"


def test_control_start_failed_unit_results_before_abort(runner):
    """Ordering: the results doc appears in the output BEFORE the abort message."""
    result = _invoke_control(runner, control_mod.start, rcs={"aitbc-a.service": 1})
    assert result.exit_code != 0
    results_pos = result.output.find("aitbc-a.service")
    abort_pos = result.output.find("start failed for services")
    assert results_pos != -1, result.output
    assert abort_pos != -1, result.output
    assert results_pos < abort_pos


# --- unchanged paths ----------------------------------------------------------


def test_control_start_success_rc0_results_doc(runner):
    result = _invoke_control(runner, control_mod.start)
    assert result.exit_code == 0
    assert "aitbc-a.service" in result.output
    assert "aitbc-b.service" in result.output
    assert "ok" in result.output


def test_control_start_success_json_single_results_doc(runner):
    result = _invoke_control(runner, control_mod.start, fmt="json")
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    names = [s["service"] for s in doc["services"]]
    assert names == ["aitbc-a.service", "aitbc-b.service"]
    assert all(s["status"] == "ok" for s in doc["services"])


def test_control_start_dry_run_rc0_results_doc(runner):
    result = _invoke_control(runner, control_mod.start, argv=["--dry-run"], rcs={"aitbc-a.service": 1})
    assert result.exit_code == 0
    assert "would run:" in result.output
    assert "dry-run" in result.output
