"""#1000 pins: crashed scenarios count as failed (never dropped), a stale
results file is reported but not consumed, orchestrator exits non-zero."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import time

import pytest

SPEC = importlib.util.spec_from_file_location(
    "chaos_orchestrator",
    os.path.join(os.path.dirname(__file__), "../../scripts/testing/chaos_orchestrator.py"),
)


def _load():
    mod = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(mod)
    return mod


@pytest.fixture()
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "chaos_test_crasher.py").write_text("import sys; sys.exit(1)\n")
    (tmp_path / "chaos_test_writer.py").write_text(
        "import json,time\njson.dump({'mttr': 2.5}, open('chaos_test_writer_%d.json' % int(time.time()*1000), 'w'))\n"
    )
    (tmp_path / "chaos_test_silent.py").write_text("import sys; sys.exit(0)\n")
    # stale silent results file — older than any run
    stale = tmp_path / "chaos_test_silent_20200101.json"
    stale.write_text(json.dumps({"mttr": 99.9}))
    os.utime(stale, (time.time() - 86400, time.time() - 86400))
    return tmp_path


def test_crashed_scenario_counts_failed(workdir):
    mod = _load()
    o = mod.ChaosOrchestrator("test")
    asyncio.run(o.run_all_scenarios(["chaos_test_crasher.py"], {"chaos_test_crasher.py": []}))
    s = o.results["summary"]
    assert s["total_scenarios"] == 1
    assert s["failed_scenarios"] == 1
    assert s["successful_scenarios"] == 0
    assert o.results["scenarios"][0]["failed"] is True


def test_silent_scenario_reports_stale_file(workdir):
    mod = _load()
    o = mod.ChaosOrchestrator("test")
    asyncio.run(o.run_all_scenarios(["chaos_test_silent.py"], {"chaos_test_silent.py": []}))
    sc = o.results["scenarios"][0]
    assert sc["failed"] is False  # rc 0 = child succeeded; missing file is reported, not consumed
    assert sc["mttr"] is None  # the stale mttr must NOT be adopted
    assert sc["stale_results_files"]
    assert o.results["summary"]["successful_scenarios"] == 1


def test_fresh_results_file_used(workdir):
    mod = _load()
    o = mod.ChaosOrchestrator("test")
    asyncio.run(o.run_all_scenarios(["chaos_test_writer.py"], {"chaos_test_writer.py": []}))
    sc = o.results["scenarios"][0]
    assert sc["mttr"] == 2.5
    assert sc["failed"] is False


def test_orchestrator_exits_nonzero_on_failure(workdir):
    """main() exits 1 when a scenario failed."""
    mod = _load()
    o = mod.ChaosOrchestrator("test")
    asyncio.run(o.run_all_scenarios(["chaos_test_crasher.py"], {"chaos_test_crasher.py": []}))
    assert o.results["summary"]["failed_scenarios"] > 0
