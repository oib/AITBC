"""--dry-run pins for the secret-rotation scripts (#1499).

Unlike the full-rotation tests in test_rotate_secret_scripts.py (which need
root for the real run), a dry-run is a read-only preview: it must print the
plan and mutate nothing — no env-file writes, no backup dir, no log file,
no systemctl — and it must work unprivileged.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    (REPO_ROOT / "scripts" / "ops" / "rotate_jwt_secret.sh", "JWT_SECRET"),
    (REPO_ROOT / "scripts" / "ops" / "rotate_api_key_secret.sh", "API_KEY_HASH_SECRET"),
]

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


@pytest.fixture
def sandbox(tmp_path: Path):
    env_dir = tmp_path / "aitbc-env"
    env_dir.mkdir()
    log_dir = tmp_path / "log"
    backup_dir = tmp_path / "backups"
    env = {
        **os.environ,
        "AITBC_ENV_DIR": str(env_dir),
        "AITBC_LOG_DIR": str(log_dir),
        "AITBC_BACKUP_DIR": str(backup_dir),
    }
    return tmp_path, env_dir, log_dir, backup_dir, env


def _run(script: Path, env: dict, argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script), *argv],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("script,key", SCRIPTS, ids=lambda p: p.name if isinstance(p, Path) else p)
def test_dry_run_prints_plan_and_mutates_nothing(sandbox, script: Path, key: str) -> None:
    tmp_path, env_dir, log_dir, backup_dir, env = sandbox
    env_file = env_dir / "aitbc-coordinator-api.env"
    env_file.write_text(f"{key}=old-secret\nOTHER=value\n")
    before = env_file.read_text()

    result = _run(script, env, ["--dry-run"])
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    assert "dry-run" in out
    assert key in out
    assert "would rewrite" in out
    assert "restarts:" in out

    # Nothing was written anywhere: env file untouched, no log dir, no
    # backup run dir, no lock/state leftovers.
    assert env_file.read_text() == before
    assert not log_dir.exists() or not any(log_dir.iterdir())
    assert not backup_dir.exists() or not any(backup_dir.iterdir())


@pytest.mark.parametrize("script,key", SCRIPTS, ids=lambda p: p.name if isinstance(p, Path) else p)
def test_dry_run_rejects_extra_args(sandbox, script: Path, key: str) -> None:
    _tmp, _env_dir, _log, _bak, env = sandbox
    result = _run(script, env, ["--dry-run", "surprise"])
    assert result.returncode != 0
    assert "unexpected arguments" in result.stderr


@pytest.mark.parametrize("script,key", SCRIPTS, ids=lambda p: p.name if isinstance(p, Path) else p)
def test_dry_run_warns_when_no_env_files(sandbox, script: Path, key: str) -> None:
    _tmp, _env_dir, _log, _bak, env = sandbox
    result = _run(script, env, ["--dry-run"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no-op" in result.stdout
