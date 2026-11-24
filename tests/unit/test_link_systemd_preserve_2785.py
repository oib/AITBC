"""#2785: link-systemd.sh must not delete operator-installed config.

Two preservation-policy violations are pinned here:

1. The DISABLED_SERVICES reconcile ran ``rm -rf`` on the entry BEFORE the
   symlink-vs-regular-file check — a real unit file matching a disabled
   name was deleted outright.
2. ``<unit>.service.d`` drop-in dirs were ``rm -rf``'d unconditionally
   before re-linking — an operator-maintained drop-in directory at that
   path was wiped and replaced by a symlink.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "utils" / "link-systemd.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


@pytest.fixture
def sandbox(tmp_path: Path) -> dict:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "systemctl"
    stub.write_text("#!/bin/bash\nexit 0\n")
    stub.chmod(0o755)

    sysdir = tmp_path / "systemd"
    etcdir = tmp_path / "etc"
    tmpfiles = tmp_path / "tmpfiles.d"
    for d in (sysdir, etcdir, tmpfiles):
        d.mkdir()

    # Operator-installed REAL unit file whose basename is disabled.
    real_unit = sysdir / "aitbc-market.service"
    real_unit.write_text("[Unit]\nDescription=operator-installed\n")
    # A repo-pointed symlink for another disabled unit — ours to remove.
    link_unit = sysdir / "aitbc-legacy-svc.service"
    link_unit.symlink_to(REPO_ROOT / "apps" / "market" / "aitbc-market.service")

    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "AITBC_SYSTEMD_DIR": str(sysdir),
        "AITBC_ETC_DIR": str(etcdir),
        "AITBC_TMPFILES_DIR": str(tmpfiles),
        "DISABLED_SERVICES": "aitbc-market aitbc-legacy-svc",
    }
    return {"sysdir": sysdir, "real_unit": real_unit, "link_unit": link_unit, "env": env}


def _run(sandbox: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=sandbox["env"], timeout=120)


def test_disabled_regular_file_is_preserved(sandbox: dict) -> None:
    result = _run(sandbox)
    assert sandbox["real_unit"].exists(), "operator-installed file for a disabled unit was deleted"
    assert "Kept operator-installed file for disabled unit" in result.stdout


def test_disabled_symlink_is_still_removed(sandbox: dict) -> None:
    _run(sandbox)
    assert not sandbox["link_unit"].exists() and not sandbox["link_unit"].is_symlink(), (
        "repo-pointed symlink for a disabled unit must still be swept"
    )


def test_dropin_helper_preserves_real_directories() -> None:
    """Static pin for the .d path (no repo .d dirs exist to exercise live):
    link_dropin_dir must keep non-symlink targets and only rm links."""
    src = SCRIPT.read_text()
    assert "link_dropin_dir()" in src
    helper = src.split("link_dropin_dir()", 1)[1].split("\n}\n", 1)[0]
    assert '[ -e "$target_dir" ] && [ ! -L "$target_dir" ]' in helper
    # both .d call sites go through the helper — the only rm -rf of
    # target_dir left in the file is the guarded one inside the helper
    assert src.count("link_dropin_dir ") >= 2
    assert src.count('rm -rf "$target_dir"') == 1
