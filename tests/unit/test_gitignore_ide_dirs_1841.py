"""GITIGNORE-IDE-DIRS-1 (#1841): IDE/agent-tool local state must stay out of git.

The #1757 ghp_ PAT entered public history via .windsurf/workflows/ — .devin/
was ignored but .windsurf/ and its siblings were not, leaving the exact
recurrence path open. These pins assert the real .gitignore covers the
dirs agent tooling drops at checkout root, and that none are tracked.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

IDE_DIRS = [".devin", ".windsurf", ".codeium", ".cursor", ".agentic", ".claude"]


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def test_ide_dirs_are_ignored() -> None:
    for d in IDE_DIRS:
        probe = f"{d}/local-state.tmp"
        result = _git("check-ignore", "-q", probe)
        assert result.returncode == 0, f"{d}/ is not covered by .gitignore"


def test_ide_dirs_are_not_tracked() -> None:
    tracked = _git("ls-files")
    assert tracked.returncode == 0, tracked.stderr
    for line in tracked.stdout.splitlines():
        top = line.split("/", 1)[0]
        assert top not in IDE_DIRS, f"{line} is tracked but should be ignored"
