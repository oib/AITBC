"""Tests for scripts/ci/check-unawaited-async.py (RATCHET-UNAWAITED-TEST-BASELINE-1).

The hook must agree with ``--update``: test paths are outside the ratchet's
scope in every mode. Previously the changed-file branch (pre-commit/pre-push)
scanned any ``.py`` path it was given, tests included, so touching one of the
22 survey files (e.g. test_bond_slashing.py's 20 sync ``db_session.commit()``/
``refresh()`` calls) failed the gate while ``--update`` never writes them.
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "check-unawaited-async.py"


@pytest.fixture(scope="module")
def ratchet():
    spec = importlib.util.spec_from_file_location("check_unawaited_async", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestChangedFileModeSkipsTestPaths:
    def test_bond_slashing_test_file_is_skipped(self, ratchet, monkeypatch):
        monkeypatch.chdir(REPO_ROOT)
        assert ratchet.main(["apps/coordinator-api/tests/test_bond_slashing.py"]) == 0

    def test_gossip_network_test_file_is_skipped(self, ratchet, monkeypatch):
        monkeypatch.chdir(REPO_ROOT)
        assert ratchet.main(["apps/blockchain-node/tests/test_gossip_network.py"]) == 0


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "scripts" / "ci").mkdir(parents=True)
    (tmp_path / "scripts" / "ci" / "unawaited-async-baseline.txt").write_text("# unawaited-async findings baseline\n")
    return tmp_path


class TestNonTestPathStillScanned:
    def test_commit_shaped_call_in_async_def_fails(self, ratchet, tmp_path, monkeypatch):
        root = _repo(tmp_path)
        (root / "pkg" / "mod.py").write_text("async def f(s):\n    s.commit()\n")
        monkeypatch.setattr(ratchet, "REPO_ROOT", root)
        monkeypatch.setattr(ratchet, "BASELINE", root / "scripts" / "ci" / "unawaited-async-baseline.txt")
        monkeypatch.chdir(root)
        assert ratchet.main(["pkg/mod.py"]) == 1

    def test_noqa_marker_absorbs_the_call(self, ratchet, tmp_path, monkeypatch):
        root = _repo(tmp_path)
        (root / "pkg" / "mod.py").write_text("async def f(s):\n    s.commit()  # noqa: unawaited-async\n")
        monkeypatch.setattr(ratchet, "REPO_ROOT", root)
        monkeypatch.setattr(ratchet, "BASELINE", root / "scripts" / "ci" / "unawaited-async-baseline.txt")
        monkeypatch.chdir(root)
        assert ratchet.main(["pkg/mod.py"]) == 0


class TestUpdateWritesNoTestLines:
    def test_update_baseline_excludes_tests(self, ratchet, tmp_path, monkeypatch):
        root = _repo(tmp_path)
        (root / "apps" / "tests").mkdir(parents=True)
        (root / "apps" / "mod.py").write_text("async def f(s):\n    s.commit()\n")
        (root / "apps" / "tests" / "test_mod.py").write_text("async def f(s):\n    s.commit()\n")
        monkeypatch.setattr(ratchet, "REPO_ROOT", root)
        baseline = root / "scripts" / "ci" / "unawaited-async-baseline.txt"
        monkeypatch.setattr(ratchet, "BASELINE", baseline)
        monkeypatch.chdir(root)
        assert ratchet.main(["--update"]) == 0
        lines = [ln for ln in baseline.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
        assert lines == ["apps/mod.py\tf\ts.commit()\t1"]
        assert not any("tests" in Path(ln.split("\t")[0]).parts for ln in lines)
