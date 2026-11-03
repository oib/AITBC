"""CI-PARITY-BLIND-TO-UNLISTED-TEST-DIRS-1 — a ``tests`` directory nobody
lists in testpaths must fail the parity check, not print "parity ok".

apps/ollama_gate/tests sat outside testpaths for a day: the check only
compared testpaths with the classification, never the disk, so a new suite
ran in no gate and nothing noticed.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "check_test_suite_parity.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_test_suite_parity", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unlisted_tests_dir_is_reported(tmp_path):
    (tmp_path / "apps" / "newapp" / "tests").mkdir(parents=True)
    (tmp_path / "apps" / "newapp" / "tests" / "test_x.py").write_text("def test_x(): pass\n")
    parity = _load()
    assert parity.uncovered_test_dirs(root=tmp_path, paths=["apps/oldapp/tests"]) == ["apps/newapp/tests"]


def test_listed_or_nested_dir_is_covered(tmp_path):
    d = tmp_path / "apps" / "newapp" / "tests"
    d.mkdir(parents=True)
    (d / "test_x.py").write_text("def test_x(): pass\n")
    parity = _load()
    assert parity.uncovered_test_dirs(root=tmp_path, paths=["apps/newapp/tests"]) == []
    assert parity.uncovered_test_dirs(root=tmp_path, paths=["apps"]) == []


def test_dir_without_pytest_files_is_not_a_suite(tmp_path):
    # examples/tests carry only __init__.py or jest specs — not pytest.
    d = tmp_path / "apps" / "market" / "examples" / "tests"
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("")
    (d / "applyTheme.spec.ts").write_text("")
    parity = _load()
    assert parity.uncovered_test_dirs(root=tmp_path, paths=[]) == []


def test_repo_has_no_uncovered_suites():
    parity = _load()
    assert parity.uncovered_test_dirs() == []
