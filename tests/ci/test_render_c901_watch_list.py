"""Smoke test for the C901 watch-list renderer (#1517)."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER = REPO_ROOT / "scripts/ci/render-c901-watch-list.py"
COMMITTED = REPO_ROOT / "scripts/ci/c901-watch-list.md"


def test_render_c901_watch_list_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(RENDER)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    assert "Tier 1" in proc.stdout
    assert "except-ratchet" in proc.stdout


def test_committed_watch_list_present():
    assert COMMITTED.is_file()
    text = COMMITTED.read_text()
    assert "Do not edit by hand" in text
    assert "check-except-ratchet.sh" in text
