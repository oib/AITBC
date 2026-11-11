"""#1730 — setup.sh must never create world-readable env files.

``ensure_service_env_files`` in ``scripts/deployment/setup.sh`` used
``touch`` + ``chmod 644`` for missing per-service and shared env files —
the same defect #1719 fixed in ``update.sh``'s ``ensure_env_files``. The
0644 stubs are how ``aitbc-island-ipfs.env`` (node0/1/2) and
``aitbc-island-swarm-probe.env`` (hub/hub1) ended up world-readable.

The function now mirrors update.sh: stubs are created ``0600`` owned by
the unit's ``User=`` (falling back to root), shared files owner ``aitbc``
when that user exists, and pre-existing files get other-class access
stripped. ``setup.sh`` also gained the ``BASH_SOURCE`` guard update.sh
already had so the function can be sourced in tests.

Tests drive the real function against a scratch systemd dir and scratch
``/etc/aitbc`` via ``AITBC_SYSTEMD_DIR`` / ``AITBC_ETC_DIR`` overrides —
never the real ``/etc``.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SH = REPO_ROOT / "scripts" / "deployment" / "setup.sh"


def _run(
    tmp_path: Path, units: dict[str, str], preexisting: dict[str, str] | None = None
) -> tuple[subprocess.CompletedProcess[str], Path]:
    systemd_dir = tmp_path / "systemd"
    etc_dir = tmp_path / "etc-aitbc"
    systemd_dir.mkdir()
    etc_dir.mkdir()

    for name, body in units.items():
        (systemd_dir / name).write_text(body)
    for name, content in (preexisting or {}).items():
        p = etc_dir / name
        p.write_text(content)
        p.chmod(0o644)

    script = f"""
        source {SETUP_SH}
        ensure_service_env_files
        exit $?
    """
    env = {
        **os.environ,
        "AITBC_ROOT": str(REPO_ROOT),
        "AITBC_SYSTEMD_DIR": str(systemd_dir),
        "AITBC_ETC_DIR": str(etc_dir),
    }
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env), etc_dir


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _other_bits(mode: int) -> int:
    return mode & 0o007


def test_missing_per_service_env_created_owner_only(tmp_path):
    result, etc_dir = _run(
        tmp_path,
        {"aitbc-foo.service": "[Service]\nUser=aitbc\n"},
    )
    assert result.returncode == 0, result.stderr

    for f in [etc_dir / "aitbc-foo.env", etc_dir / "node.env", etc_dir / "blockchain.env"]:
        assert f.exists(), f"{f} not created"
        assert _mode(f) == 0o600, f"{f} mode {_mode(f):o} != 600"
        assert _other_bits(_mode(f)) == 0


def test_existing_world_readable_env_is_tightened(tmp_path):
    result, etc_dir = _run(
        tmp_path,
        {"aitbc-foo.service": "[Service]\nUser=aitbc\n"},
        preexisting={"aitbc-foo.env": "SECRET=x\n"},
    )
    assert result.returncode == 0, result.stderr

    env = etc_dir / "aitbc-foo.env"
    assert env.read_text() == "SECRET=x\n"
    assert _other_bits(_mode(env)) == 0, f"other-class bits remain: {_mode(env):o}"


def test_unit_without_user_still_gets_0600(tmp_path):
    result, etc_dir = _run(
        tmp_path,
        {"aitbc-bar.timer": "[Timer]\n"},
    )
    assert result.returncode == 0, result.stderr

    f = etc_dir / "aitbc-bar.env"
    assert f.exists()
    assert _mode(f) == 0o600


def test_no_644_creation_path_remains():
    """Static guard: the touch+chmod-644 pattern must not come back."""
    text = SETUP_SH.read_text()
    fn = text.split("ensure_service_env_files() {", 1)[1].split("\n}\n", 1)[0]
    assert "chmod 644" not in fn
    assert "chmod 666" not in fn
