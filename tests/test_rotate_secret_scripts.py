"""rotate_jwt_secret.sh and rotate_api_key_secret.sh driven for real (#852, #854).

The scripts run against a scratch env directory with systemctl/sleep/curl
stubbed on PATH. They previously aborted on an unbound ``$1`` under ``set -u``
and claimed a dual-secret overlap no service implemented; now

* the documented stdin usage works end to end,
* the overlap is real: the retired secret is kept in ``*_SECRET_PREVIOUS`` so
  ``aitbc.auth.jwt`` and the partners router can keep verifying it,
* backups and the generated rollback script live in a per-run directory under
  a private root (no fixed /tmp path), and a rollback restores only this run's
  backups — a concurrent run's ``*.env.backup_*`` files are left alone.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
JWT_SCRIPT = REPO_ROOT / "scripts" / "ops" / "rotate_jwt_secret.sh"
APIKEY_SCRIPT = REPO_ROOT / "scripts" / "ops" / "rotate_api_key_secret.sh"

pytestmark = [
    pytest.mark.skipif(shutil.which("bash") is None or shutil.which("python3") is None, reason="needs bash and python3"),
    pytest.mark.skipif(os.geteuid() != 0, reason="the rotation scripts refuse to run as non-root"),
]

SERVICES = ["aitbc-coordinator-api", "aitbc-market"]

STUBS = {
    "systemctl": "#!/bin/bash\nexit 0\n",
    "sleep": "#!/bin/bash\nexit 0\n",
    "curl": "#!/bin/bash\nexit 0\n",
}


def _write_env_files(env_dir: Path, key: str, old_secret: str) -> None:
    for service in SERVICES:
        (env_dir / f"{service}.env").write_text(f"# {service}\n{key}={old_secret}\nOTHER=value\n")


def _run(script: Path, env: dict, stdin: str = "", argv: list[str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script), *(argv or [])],
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture
def sandbox(tmp_path: Path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in STUBS.items():
        stub = bindir / name
        stub.write_text(body)
        stub.chmod(0o755)
    env_dir = tmp_path / "aitbc-env"
    env_dir.mkdir()
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "AITBC_ENV_DIR": str(env_dir),
        "AITBC_LOG_DIR": str(tmp_path / "log"),
        "AITBC_BACKUP_DIR": str(tmp_path / "backups"),
    }
    return tmp_path, env_dir, env


def test_scripts_are_valid_bash() -> None:
    for script in (JWT_SCRIPT, APIKEY_SCRIPT):
        subprocess.run(["bash", "-n", str(script)], check=True)


@pytest.mark.parametrize("script", [JWT_SCRIPT, APIKEY_SCRIPT], ids=lambda p: p.name)
def test_refuses_secret_on_argv(sandbox, script: Path) -> None:
    _tmp, _env_dir, env = sandbox
    result = _run(script, env, argv=["should-not-be-here"])
    assert result.returncode != 0
    assert "stdin" in result.stdout + result.stderr


@pytest.mark.parametrize(
    "script,key",
    [(JWT_SCRIPT, "JWT_SECRET"), (APIKEY_SCRIPT, "API_KEY_HASH_SECRET")],
    ids=lambda p: p.name if isinstance(p, Path) else p,
)
def test_documented_stdin_rotation(sandbox, script: Path, key: str) -> None:
    """A full run on stdin: env files end with the new secret, the retired one
    in ``*_SECRET_PREVIOUS`` for the (now real) overlap, and no leftovers."""
    _tmp, env_dir, env = sandbox
    old_secret = "old-secret-that-is-long-enough-0123456789"
    new_secret = "new/secret&with=sed-unfriendly.chars0123456789abcdef"
    _write_env_files(env_dir, key, old_secret)

    result = _run(script, env, stdin=f"{new_secret}\n")
    assert result.returncode == 0, result.stdout + result.stderr

    for service in SERVICES:
        text = (env_dir / f"{service}.env").read_text()
        assert f"{key}={new_secret}" in text
        assert f"{key}_NEW" not in text
        # The overlap is real now: the retired secret stays verifiable.
        assert f"{key}_PREVIOUS={old_secret}" in text
        assert "OTHER=value" in text

    # Successful run cleans its own backup/rollback artefacts (scratch copies
    # are all inside the sandbox, so nothing else on the host is touched).
    assert not list(env_dir.glob("*.env.backup_*"))


@pytest.mark.parametrize(
    "script,key",
    [(JWT_SCRIPT, "JWT_SECRET"), (APIKEY_SCRIPT, "API_KEY_HASH_SECRET")],
    ids=lambda p: p.name if isinstance(p, Path) else p,
)
def test_second_rotation_appends_previous(sandbox, script: Path, key: str) -> None:
    _tmp, env_dir, env = sandbox
    _write_env_files(env_dir, key, "first-secret-0123456789abcdef0123456789")
    assert _run(script, env, stdin="second-secret-0123456789abcdef012345678\n").returncode == 0
    assert _run(script, env, stdin="third-secret-0123456789abcdef0123456789\n").returncode == 0
    text = (env_dir / f"{SERVICES[0]}.env").read_text()
    assert f"{key}=third-secret-0123456789abcdef0123456789" in text
    prev = [line for line in text.splitlines() if line.startswith(f"{key}_PREVIOUS=")]
    assert prev == [f"{key}_PREVIOUS=second-secret-0123456789abcdef012345678,first-secret-0123456789abcdef0123456789"]
