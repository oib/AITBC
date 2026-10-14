"""Shared skip for tests that shell out to ``git`` against the repository.

``git ls-files``/``git grep``/``git status`` raise ``CalledProcessError`` in a
``git archive`` export or any copy that drops ``.git`` — and grep-style guards
worse: they pass *vacuously* over an empty file list. Mark the test or the
module so the non-run shows up as a skip instead of a crash or a silent pass.

``.git`` is a directory in a normal checkout but a *file* in a linked worktree,
so the check is ``exists()``, never ``is_dir()``.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

GIT_CHECKOUT_PRESENT = (REPO_ROOT / ".git").exists()

requires_git_checkout = pytest.mark.skipif(
    not GIT_CHECKOUT_PRESENT,
    reason="needs a .git checkout (use a worktree or rsync with .git)",
)
