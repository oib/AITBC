"""#948: end_to_end_workflow summary no longer counts info as failure.

A clean run used to print ``FAILED`` because ``info`` steps (and the two
deliberately simulated steps) were counted in the denominator but could
never be ``success``. Info steps are now reported separately, simulated
steps are marked, and only a real ``error`` step fails the run.
"""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "utils" / "end_to_end_workflow.py"


def _load():
    spec = importlib.util.spec_from_file_location("e2e_workflow", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wf(steps):
    mod = _load()
    wf = mod.MarketWorkflow()
    for status in steps:
        wf.log_step(f"step-{status}", status)
    return wf


def test_success_and_info_steps_report_completed(capsys):
    wf = _wf(["info", "success", "success", "info"])
    wf.print_workflow_summary()
    out = capsys.readouterr().out
    assert "COMPLETED" in out
    assert "FAILED" not in out


def test_error_step_reports_failed(capsys):
    wf = _wf(["success", "error"])
    wf.print_workflow_summary()
    assert "FAILED" in capsys.readouterr().out


def test_simulated_steps_are_marked_and_not_errors(capsys):
    wf = _wf(["success", "simulated", "info"])
    wf.print_workflow_summary()
    out = capsys.readouterr().out
    assert "COMPLETED" in out
    assert "Simulated Steps: 1" in out
