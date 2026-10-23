"""Tests for the scope-cgroup OOM check in scripts/monitoring/memory-monitor.sh
(MEMMON-ROOT-OOM-1).

The collector used to read only per-unit memory.events, so it printed
"OK: No OOM kills" while the container root cgroup was enforcing its wall
(18 kills on 22 Oct). The script now also reads the root + user.slice +
system.slice counters, exports them as textfile metrics, and only says "OK"
when both sides were actually read and show no NEW kills since the previous
run (kept in a state file).

The script is driven as a subprocess with AITBC_CGROUP_ROOT pointed at a
fixture tree -- same pattern the repo uses for the other textfile exporters.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "monitoring" / "memory-monitor.sh"

_EVENTS = "low 0\nhigh 0\nmax 0\noom 0\noom_group_kill 0\noom_kill {kills}\n"


def _events(dirpath: Path, kills: int) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "memory.events").write_text(_EVENTS.format(kills=kills))


def _cgroup_tree(
    base: Path,
    *,
    root: int | None = 18,
    user_slice: int | None = 15,
    system_slice: int | None = 3,
    current: int | None = 2_520_000_000,
    peak: int | None = 3_797_573_632,
    max_bytes: int | str | None = 4_096_000_000,
) -> Path:
    root_dir = base / "cgroup"
    if root is not None:
        _events(root_dir, root)
    if user_slice is not None:
        _events(root_dir / "user.slice", user_slice)
    if system_slice is not None:
        _events(root_dir / "system.slice", system_slice)
    if current is not None:
        root_dir.mkdir(parents=True, exist_ok=True)
        (root_dir / "memory.current").write_text(str(current))
    if peak is not None:
        (root_dir / "memory.peak").write_text(str(peak))
    if max_bytes is not None:
        (root_dir / "memory.max").write_text(str(max_bytes))
    return root_dir


def _run(tmp_path: Path, cgroup: Path, state: Path | None = None) -> tuple[subprocess.CompletedProcess[str], Path]:
    textfile = tmp_path / "textfile"
    textfile.mkdir(exist_ok=True)
    log = tmp_path / "log"
    log.mkdir(exist_ok=True)
    state_path = state or (tmp_path / "state")
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "AITBC_CGROUP_ROOT": str(cgroup),
        "AITBC_TEXTFILE_DIR": str(textfile),
        "AITBC_MEMMON_STATE": str(state_path),
        "AITBC_MEMMON_LOG": str(log / "mon.log"),
    }
    proc = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env, timeout=60)
    return proc, state_path


def _metrics(tmp_path: Path) -> str:
    prom = tmp_path / "textfile" / "memory-monitor.prom"
    return prom.read_text() if prom.exists() else ""


def test_metrics_report_all_scopes_and_root_gauges(tmp_path) -> None:
    cgroup = _cgroup_tree(tmp_path)
    proc, _ = _run(tmp_path, cgroup)
    text = _metrics(tmp_path)
    assert 'aitbc_cgroup_oom_kill_total{cgroup="root"} 18' in text
    assert 'aitbc_cgroup_oom_kill_total{cgroup="user.slice"} 15' in text
    assert 'aitbc_cgroup_oom_kill_total{cgroup="system.slice"} 3' in text
    assert 'aitbc_cgroup_memory_current_bytes{cgroup="root"} 2520000000' in text
    assert 'aitbc_cgroup_memory_peak_bytes{cgroup="root"} 3797573632' in text
    assert 'aitbc_cgroup_memory_max_bytes{cgroup="root"} 4096000000' in text


def test_uncapped_memory_max_is_emitted_as_plus_inf(tmp_path) -> None:
    cgroup = _cgroup_tree(tmp_path, max_bytes="max")
    _run(tmp_path, cgroup)
    assert 'aitbc_cgroup_memory_max_bytes{cgroup="root"} +Inf' in _metrics(tmp_path)


def test_first_run_establishes_baseline_without_alarming_on_existing_kills(tmp_path) -> None:
    """Deploy-day behaviour: the counters start at their real cumulative
    values (18/15/3 on hub), no state file exists, and the run must NOT
    report them as new kills -- exactly like the increase() alert rule."""
    cgroup = _cgroup_tree(tmp_path)
    proc, state_path = _run(tmp_path, cgroup)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "new cgroup OOM kill" not in proc.stdout
    # baseline was written for next-run comparison
    state = state_path.read_text()
    assert "root=18" in state and "user.slice=15" in state and "system.slice=3" in state


def test_a_new_kill_is_reported_once_then_goes_quiet(tmp_path) -> None:
    cgroup = _cgroup_tree(tmp_path)
    first, state_path = _run(tmp_path, cgroup)
    assert first.returncode == 0
    # one new kill at the root since the baseline run
    _events(cgroup, 19)
    second, _ = _run(tmp_path, cgroup, state=state_path)
    assert second.returncode == 1
    assert "ALERT" in second.stdout and "1 new cgroup OOM kill(s)" in second.stdout and "root:+1" in second.stdout
    # state advanced: the same count must not re-alert the following run
    third, _ = _run(tmp_path, cgroup, state=state_path)
    assert third.returncode == 0
    assert "new cgroup OOM kill" not in third.stdout


def test_missing_scope_counters_never_print_ok(tmp_path) -> None:
    """No memory.events anywhere: the verdict is unavailable/INCOMPLETE,
    never the 'OK' that hid the 22 Oct kills."""
    cgroup = _cgroup_tree(tmp_path, root=None, user_slice=None, system_slice=None, current=None, peak=None, max_bytes=None)
    proc, _ = _run(tmp_path, cgroup)
    assert proc.returncode == 0  # degraded, not failed
    # The OOM check must not print its clean verdict -- the wording below is
    # the "all clear" that hid the 22 Oct kills. (An unrelated "OK: System
    # memory" line from the free(1) check is fine.)
    assert "no OOM kills" not in proc.stdout
    assert "INCOMPLETE" in proc.stdout or "SKIPPED" in proc.stdout
    # and no metric file is published off an unread scan
    assert _metrics(tmp_path) == ""


def test_flat_counters_print_the_ok_side_of_the_verdict(tmp_path) -> None:
    """Scope counters readable and unchanged => the run may say its clean
    line; wording must still show the counts it judged on."""
    cgroup = _cgroup_tree(tmp_path)
    first, state_path = _run(tmp_path, cgroup)
    second, _ = _run(tmp_path, cgroup, state=state_path)
    assert second.returncode == 0
    assert "new cgroup OOM kill" not in second.stdout
    # Whatever the per-unit side found on this host, the scope half of the
    # verdict must name the counters it read.
    assert "root=18" in second.stdout or "root=18" in (tmp_path / "log" / "mon.log").read_text()
