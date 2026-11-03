"""UTILS-FIX-PERMISSIONS-STRIPS-EXEC-OPENS-ENV-1 — no blanket chmod of the checkout.

fix-permissions.sh and quick-fix.sh (identical bodies) ran ``chmod 664`` on
every file under /opt/aitbc and ``+x`` only on *.sh/*.py: venv/bin tools and
git hooks lost their execute bit and every mode-600 secret (.env files,
keystores) became world-readable. quick-fix.sh is retired and the surviving
fix-permissions.sh is scoped to source files — never venv/, .git/, .env* or
key material.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "utils" / "fix-permissions.sh"


def test_quick_fix_is_retired():
    assert not (REPO_ROOT / "scripts" / "utils" / "quick-fix.sh").exists()


def test_no_blanket_chmod_of_every_file():
    body = SCRIPT.read_text()
    assert "chmod -R" not in body
    # every chmod must come through a -name-filtered find, never a bare
    # "-type f -exec chmod" over the whole tree
    for line in body.splitlines():
        if "-exec chmod" in line:
            assert "-name" in line or "-type d" in line, line


def test_sensitive_paths_are_excluded():
    body = SCRIPT.read_text()
    for needle in ("venv", ".git", ".env"):
        assert needle in body, f"{needle!r} must appear in the exclusion list"
