"""#1129 pin: no unresolved merge-conflict markers in tracked files under
scripts/, and every deploy script parses. cfd998044 landed a rebase with
live <<<<<<< ======= >>>>>>> markers and bash -n failed on it."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Git's conflict markers: <<<<<<< and >>>>>>> take a ref label; ======= is
# exactly seven '=' on its own line (banner lines of 8+ are not markers).
import re

MARKERS = (re.compile(r"^<<<<<<< "), re.compile(r"^=======$"), re.compile(r"^>>>>>>> "))


def _tracked_scripts() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "scripts"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [ln for ln in out.stdout.splitlines() if ln]


def test_no_conflict_markers_in_tracked_scripts():
    offenders = []
    for rel in _tracked_scripts():
        path = REPO / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if any(m.match(line) for m in MARKERS):
                offenders.append(f"{rel}:{i}: {line[:40]}")
    assert not offenders, "unresolved conflict markers in tracked files:\n" + "\n".join(offenders)


def test_deploy_scripts_parse():
    deploy_dir = REPO / "scripts/deployment/deploy"
    scripts = sorted(deploy_dir.glob("*.sh"))
    assert scripts, "no deploy scripts found"
    for script in scripts:
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert result.returncode == 0, f"bash -n failed for {script.name}: {result.stderr[:200]}"
