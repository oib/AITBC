"""CI-UNAWAITED-ASYNC-BASELINE-KEYED-BY-LINE-1 — the baseline must key on
file + enclosing function + call text, not file:line.

Old format: a baselined ``redis.set`` at line 7 failed the hook after two
lines were added above it, while a *new* unawaited ``redis.setex`` landing
on line 7 passed. Keying on the call itself makes moving code neither
fail nor hide a finding.
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "check-unawaited-async.py"

BASE_SRC = "async def f(redis):\n    x = 1\n    redis.set('k', 'v')\n"
MOVED_SRC = "async def f(redis):\n    y = 0\n    x = 1\n    yy = 0\n    redis.set('k', 'v')\n"
NEWCALL_SRC = "async def f(redis):\n    x = 1\n    redis.setex('k', 5, 'v')\n"


@pytest.fixture()
def ratchet():
    spec = importlib.util.spec_from_file_location("check_unawaited_async", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def scratch(ratchet, tmp_path, monkeypatch):
    (tmp_path / "apps").mkdir()
    (tmp_path / "scripts" / "ci").mkdir(parents=True)
    (tmp_path / "scripts" / "ci" / "unawaited-async-baseline.txt").write_text("# baseline\n")
    monkeypatch.setattr(ratchet, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ratchet, "BASELINE", tmp_path / "scripts" / "ci" / "unawaited-async-baseline.txt")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_moved_code_stays_baselined(ratchet, scratch):
    target = scratch / "apps" / "mod.py"
    target.write_text(BASE_SRC)
    assert ratchet.main(["--update"]) == 0
    target.write_text(MOVED_SRC)
    assert ratchet.main(["--all"]) == 0


def test_new_call_on_a_baselined_line_fails(ratchet, scratch):
    target = scratch / "apps" / "mod.py"
    target.write_text(BASE_SRC)
    assert ratchet.main(["--update"]) == 0
    target.write_text(NEWCALL_SRC)
    assert ratchet.main(["--all"]) == 1


def test_sync_def_nested_under_async_is_not_a_finding(ratchet, scratch):
    target = scratch / "apps" / "mod.py"
    target.write_text("async def outer(db):\n    def inner():\n        db.commit()\n    return inner\n")
    assert ratchet.main(["--all"]) == 0


def test_update_reports_added_and_removed(ratchet, scratch, capsys):
    target = scratch / "apps" / "mod.py"
    target.write_text(BASE_SRC)
    assert ratchet.main(["--update"]) == 0
    capsys.readouterr()
    target.write_text(NEWCALL_SRC)
    assert ratchet.main(["--update"]) == 0
    out = capsys.readouterr().out
    assert "+1" in out and "setex" in out
    assert "-1" in out and "redis.set('k', 'v')" in out
