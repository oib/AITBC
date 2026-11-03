"""DEPLOY-STASH-POP-CONFLICT-LIVE-1 — a stash-pop conflict must abort the update.

do_git_pull() used to report a conflicting ``git stash pop`` and carry on: the
working tree kept conflict markers in the live checkout and the run went on to
relink units and restart services against marker-laden code. Now the conflict
is fatal — the tree is reset to the just-pulled HEAD (the stash itself is not
dropped by a conflicting pop) and the function returns non-zero so main aborts
before relink/restart.

The test drives the real do_git_pull against two scratch git repositories:
an "upstream" repo the pull fetches from, and a checkout under AITBC_ROOT with
an uncommitted edit that conflicts with the pulled change.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SH = REPO_ROOT / "scripts" / "deployment" / "update.sh"


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


def _conflicting_checkout(tmp_path: Path) -> Path:
    """AITBC_ROOT checkout whose stash pop conflicts with the pull."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(["init", "-b", "main"], upstream)
    (upstream / "conflicted.txt").write_text("base\n")
    _git(["add", "-A"], upstream)
    _git(["commit", "-m", "base"], upstream)

    checkout = tmp_path / "repo"
    _git(["clone", "-b", "main", str(upstream), str(checkout)], tmp_path)

    # Upstream advances the same line the local edit touches.
    (upstream / "conflicted.txt").write_text("upstream change\n")
    _git(["commit", "-am", "upstream"], upstream)

    # Uncommitted local edit → stash before pull → pop conflicts.
    (checkout / "conflicted.txt").write_text("local change\n")
    return checkout


def _do_git_pull(checkout: Path) -> subprocess.CompletedProcess[str]:
    script = f"""
        source {UPDATE_SH}
        AITBC_ROOT={checkout}
        VENV_DIR={checkout}/venv
        GIT_REMOTE={checkout}/../upstream
        NO_CHANGES=false
        detect_gpu() {{ :; }}
        do_git_pull
    """
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)


def test_stash_pop_conflict_aborts_and_leaves_a_clean_tree(tmp_path):
    checkout = _conflicting_checkout(tmp_path)

    result = _do_git_pull(checkout)

    assert result.returncode != 0, "do_git_pull reported success with a stash-pop conflict\n" + result.stdout + result.stderr
    assert "<<<<<<<" not in (checkout / "conflicted.txt").read_text()
    # The pulled commit is in place — only the conflict is backed out.
    assert (checkout / "conflicted.txt").read_text() == "upstream change\n"
    # The conflicting pop does not drop the stash; the local change survives.
    stashes = subprocess.run(["git", "stash", "list"], cwd=checkout, capture_output=True, text=True).stdout
    assert "auto-stash" in stashes


def test_clean_pull_still_restores_the_stash(tmp_path):
    """No regression for the common case: a non-conflicting stash pops cleanly."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(["init", "-b", "main"], upstream)
    (upstream / "a.txt").write_text("a1\n")
    _git(["add", "-A"], upstream)
    _git(["commit", "-m", "base"], upstream)

    checkout = tmp_path / "repo"
    _git(["clone", "-b", "main", str(upstream), str(checkout)], tmp_path)

    (upstream / "b.txt").write_text("new file\n")
    _git(["add", "-A"], upstream)
    _git(["commit", "-m", "upstream"], upstream)

    (checkout / "a.txt").write_text("local edit\n")

    result = _do_git_pull(checkout)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (checkout / "a.txt").read_text() == "local edit\n"
    assert (checkout / "b.txt").read_text() == "new file\n"
