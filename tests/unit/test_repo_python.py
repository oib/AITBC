"""Branch tests for scripts/ci/repo-python.sh.

The resolver exists because a hook script that lands on a dependency-poor
system python3 reports "checked" while it checked nothing. Its contract:
$PYTHON env (validated, then trusted) -> <checkout>/venv/bin/python -> the main
checkout's venv (so a linked worktree still finds the reference venv) -> exit 1
naming PYTHON=<interpreter>. A candidate must be -x AND run a trivial import.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "repo-python.sh"


def _run(cwd: Path, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHON", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "f").write_text("x")
    _git(repo, "add", "f")
    _git(repo, "commit", "-qm", "init")
    return repo


def _make_venv_python(repo: Path) -> Path:
    """A 'venv python' that is -x and runs: symlink to this interpreter."""
    py = repo / "venv" / "bin" / "python"
    py.parent.mkdir(parents=True, exist_ok=True)
    py.symlink_to(sys.executable)
    return py


def test_env_python_wins(tmp_path: Path) -> None:
    result = _run(tmp_path, {"PYTHON": sys.executable})
    assert result.returncode == 0
    assert result.stdout.strip() == sys.executable


def test_env_python_broken_fails(tmp_path: Path) -> None:
    result = _run(tmp_path, {"PYTHON": "/nonexistent/interpreter"})
    assert result.returncode == 1
    assert result.stdout == ""
    assert "PYTHON=" in result.stderr or "PYTHON" in result.stderr


def test_checkout_venv_used(repo: Path) -> None:
    venv_py = _make_venv_python(repo)
    result = _run(repo)
    assert result.returncode == 0
    assert result.stdout.strip() == str(venv_py)


def test_worktree_resolves_main_checkout_venv(repo: Path, tmp_path: Path) -> None:
    """A linked worktree has no venv/ of its own; the resolver must find the
    main checkout's venv through --git-common-dir."""
    venv_py = _make_venv_python(repo)
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "--detach", "-q", str(wt))
    try:
        assert not (wt / "venv").exists()
        result = _run(wt)
        assert result.returncode == 0
        assert result.stdout.strip() == str(venv_py)
    finally:
        _git(repo, "worktree", "remove", "--force", str(wt))


def test_dangling_venv_symlink_falls_through(repo: Path, tmp_path: Path) -> None:
    """-x passes for a symlink only if its target exists; a dangling one is not
    runnable and must fall through to the next candidate."""
    _make_venv_python(repo)
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "--detach", "-q", str(wt))
    try:
        (wt / "venv" / "bin").mkdir(parents=True)
        (wt / "venv" / "bin" / "python").symlink_to("/nonexistent/python")
        result = _run(wt)
        assert result.returncode == 0
        assert result.stdout.strip() == str(repo / "venv" / "bin" / "python")
    finally:
        _git(repo, "worktree", "remove", "--force", str(wt))


def test_nothing_resolvable_fails_with_python_hint(tmp_path: Path) -> None:
    """No PYTHON env, no venv anywhere (not even a git repo): exit 1, a stderr
    line naming PYTHON=<interpreter>, and nothing on stdout."""
    result = _run(tmp_path)
    assert result.returncode == 1
    assert result.stdout == ""
    assert "PYTHON=" in result.stderr


def test_env_python_that_exists_but_is_not_python_fails(tmp_path: Path) -> None:
    """An -x file that does not run Python (`true` accepts -c silently and would
    fake a pass) is rejected by the import check."""
    fake = tmp_path / "fake-python"
    fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(0o755)
    result = _run(tmp_path, {"PYTHON": str(fake)})
    assert result.returncode == 1
    assert result.stdout == ""
