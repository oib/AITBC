"""ENG-1: importing aitbc.auth / aitbc.auth.api_key must not touch the filesystem.

Regression coverage for the module-level ``api_key_manager = APIKeyManager()``:
``APIKeyManager.__init__`` acquires a filelock on ``<API_KEY_STORAGE_PATH>.lock``
(filelock creates the parent directory, so hosts without a writable
``/var/lib/aitbc`` got ``PermissionError`` at *import*). The singleton is now
built lazily on first access; ``api_key_manager`` still resolves to a real
``APIKeyManager`` instance.

Note: filelock unlinks the lock file on release, so ``.lock`` is only
observable while the lock is held — the assertions below check inside it.

Every check runs in a subprocess: the singleton is process-global, so import
order inside this pytest process cannot provide isolation.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_NAME = "api_keys.json"


def _run(code: str, env_overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("API_KEY_STORAGE_PATH", None)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
        timeout=120,
    )


@pytest.mark.parametrize("stmt", ["import aitbc.auth.api_key", "import aitbc.auth"])
def test_import_with_unwritable_storage_dir(tmp_path, stmt):
    """Import with a storage path that cannot be created: no raise, no files.

    The storage parent is a regular file, so acquiring the filelock would fail
    for any user including root — a stronger check than chmod bits.
    """
    blocker = tmp_path / "blocker"
    blocker.write_text("regular file")
    storage = blocker / STORAGE_NAME
    result = _run(stmt, {"API_KEY_STORAGE_PATH": str(storage)})
    assert result.returncode == 0, result.stderr
    assert [p.name for p in tmp_path.iterdir()] == ["blocker"]


def test_import_package_alone_creates_no_files(tmp_path):
    """`import aitbc.auth` alone must leave the storage directory empty."""
    storage = tmp_path / STORAGE_NAME
    result = _run("import aitbc.auth", {"API_KEY_STORAGE_PATH": str(storage)})
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_from_import_form_returns_instance_and_creates_lock_on_first_use(tmp_path):
    """The exact `from aitbc.auth import api_key_manager` form resolves through
    the package __getattr__ delegation, yields a real APIKeyManager, and the
    lock file exists at the configured path while the lock is held."""
    storage = tmp_path / STORAGE_NAME
    code = (
        "import os\n"
        "from aitbc.auth import api_key_manager, APIKeyManager\n"
        "assert isinstance(api_key_manager, APIKeyManager), type(api_key_manager)\n"
        "with api_key_manager._lock:\n"
        f"    assert os.path.exists({str(storage) + '.lock'!r})\n"
    )
    result = _run(code, {"API_KEY_STORAGE_PATH": str(storage)})
    assert result.returncode == 0, result.stderr


def test_env_path_set_after_import_before_first_use_is_honored(tmp_path):
    """API_KEY_STORAGE_PATH assigned after import but before first access wins."""
    storage = tmp_path / STORAGE_NAME
    code = (
        "import os\n"
        "import aitbc.auth\n"
        f"os.environ['API_KEY_STORAGE_PATH'] = {str(storage)!r}\n"
        "from aitbc.auth import api_key_manager\n"
        f"assert api_key_manager.storage_path == {str(storage)!r}, api_key_manager.storage_path\n"
        "with api_key_manager._lock:\n"
        f"    assert os.path.exists({str(storage) + '.lock'!r})\n"
    )
    result = _run(code, {})  # env var intentionally absent at import time
    assert result.returncode == 0, result.stderr


def test_repeated_access_returns_same_cached_instance(tmp_path):
    code = (
        "import aitbc.auth.api_key as m\n"
        "assert m.api_key_manager is m.api_key_manager\n"
        "assert m.get_api_key_manager() is m.api_key_manager\n"
        "from aitbc.auth import api_key_manager\n"
        "assert api_key_manager is m.api_key_manager\n"
    )
    result = _run(code, {"API_KEY_STORAGE_PATH": str(tmp_path / STORAGE_NAME)})
    assert result.returncode == 0, result.stderr
