"""CI-MANUALGATE-OMITS-EIGHT-FAST-SUITES-1 — the manual pre-push gate must
run exactly what `make test-required` runs: the pytest args come from
scripts/ci/test_suites.py, not from a hand-maintained list that can drift.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "run-suite-manual.sh"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import test_suites  # noqa: E402

importlib.reload(test_suites)


def _suite_dirs() -> list[str]:
    return [*test_suites.FAST_SUITES, *test_suites.EXTRA_REQUIRED_FILES]


def test_gate_derives_args_from_test_suites():
    body = SCRIPT.read_text()
    assert "scripts/ci/test_suites.py fast" in body


def test_no_fast_suite_path_is_hardcoded():
    for line in SCRIPT.read_text().splitlines():
        if line.lstrip().startswith("#"):
            continue
        for path in _suite_dirs():
            assert path not in line, f"hardcoded suite path '{path}' in: {line.strip()}"
