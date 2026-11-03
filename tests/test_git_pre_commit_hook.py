"""UTILS-GIT-PRE-COMMIT-HOOK-BLOCKS-ON-IGNORED-CACHE-DIRS-1: the hook checks
tracked files, not ignored caches."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
HOOK = REPO_ROOT / "scripts/utils/git-pre-commit-hook.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _run_hook(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(repo / "scripts/utils/git-pre-commit-hook.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts/utils").mkdir(parents=True)
    shutil.copy(HOOK, repo / "scripts/utils/git-pre-commit-hook.sh")
    _git(repo, "init", "-q")
    _git(repo, "add", "scripts/utils/git-pre-commit-hook.sh")
    return repo


def test_ignored_cache_dirs_pass(repo):
    """A root with untracked/ignored .pytest_cache, .venv, node_modules etc.
    must pass — those dirs exist on every developer machine."""
    for d in (".pytest_cache", ".ruff_cache", ".venv", ".vscode", "node_modules", "cli_env"):
        (repo / d / "x").mkdir(parents=True)
    (repo / ".gitignore").write_text(".pytest_cache/\n.ruff_cache/\n.venv/\n.vscode/\nnode_modules/\ncli_env/\n")
    _git(repo, "add", ".gitignore")
    result = _run_hook(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_tracked_forbidden_dir_fails(repo):
    """If content under a forbidden dir is actually in the index, the hook
    still blocks the commit."""
    (repo / ".vscode").mkdir()
    (repo / ".vscode/settings.json").write_text("{}")
    _git(repo, "add", ".vscode/settings.json")
    result = _run_hook(repo)
    assert result.returncode == 1
    assert ".vscode" in result.stdout


def test_tracked_forbidden_file_fails(repo):
    (repo / "test_scratch.py").write_text("x = 1\n")
    _git(repo, "add", "test_scratch.py")
    result = _run_hook(repo)
    assert result.returncode == 1
    assert "test_*.py" in result.stdout
