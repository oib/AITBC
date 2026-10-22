"""numpy must not load at coordinator-api startup via ``aitbc.tee.benchmark``.

The TEE package ``__init__`` eagerly imports ``TEEBenchmark``, and
``coordinator_api.main`` pulls the package in during router setup — so a
top-level ``import numpy`` in ``benchmark.py`` cost ~9.4s of import time
and numpy's RSS on every coordinator start, for a ``np.percentile`` call
that only runs when a benchmark summary is requested. The import is now
function-scoped inside ``summary()``.

Both checks run in fresh subprocesses: ``sys.modules`` state is
process-global, so the pytest process cannot provide import isolation.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pythonpath() -> str:
    parts = [str(REPO_ROOT)]
    for base in (REPO_ROOT / "apps", REPO_ROOT / "packages" / "py"):
        for src in sorted(base.glob("*/src")):
            parts.append(str(src))
    extra = os.environ.get("PYTHONPATH")
    return os.pathsep.join(parts + ([extra] if extra else []))


def _run(code: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = _pythonpath()
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=REPO_ROOT, timeout=timeout
    )


def test_coordinator_main_import_does_not_load_numpy() -> None:
    proc = _run(
        "import coordinator_api.main, sys\n"  # noqa: S404 - module import is the check
        "sys.exit(0 if 'numpy' not in sys.modules else 1)\n",
        timeout=180,
    )
    assert proc.returncode == 0, f"importing coordinator_api.main loaded numpy:\n{proc.stderr[-2000:]}"


def test_benchmark_summary_still_computes_percentiles() -> None:
    proc = _run(
        "import sys\n"
        "from aitbc.tee.benchmark import TEEBenchmark, TEEBenchmarkResult\n"
        "assert 'numpy' not in sys.modules, 'benchmark import pulled numpy'\n"
        "b = TEEBenchmark(name='t')\n"
        "for i, lat in enumerate([1.0, 2.0, 3.0, 4.0]):\n"
        "    b.results.append(TEEBenchmarkResult(name='op', latency_ms=lat, memory_bytes=8))\n"
        "s = b.summary()\n"
        "assert s['count'] == 4.0 and s['min_ms'] <= s['p50_ms'] <= s['p95_ms'] <= s['p99_ms'] <= s['max_ms'], s\n"
        "print('numpy after summary:', 'numpy' in sys.modules)\n",
    )
    assert proc.returncode == 0, f"benchmark summary failed:\n{proc.stderr[-2000:]}"
