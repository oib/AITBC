"""UTILS-SETUP-CREDENTIALS-RERUN-REGENERATES-1 — a rerun must not rotate secrets.

setup-credentials.py regenerated api_hash_secret and keystore_password on
every run whenever blockchain.env lacked the values and overwrote the
credential files it had just installed — a second run silently changed the
keystore password. It now skips a credential file that already exists unless
``--rotate`` is passed, and writes new files O_EXCL 0600.
"""

from __future__ import annotations

import importlib.util
import stat
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "utils" / "setup-credentials.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("aitbc_setup_credentials", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(tmp_path: Path, argv: list[str], env_files: dict[str, str] | None = None):
    mod = _load_module()
    cred_dir = tmp_path / "credentials"
    env_file = tmp_path / "blockchain.env"
    env_file.write_text("")
    for name, contents in (env_files or {}).items():
        cred_dir.mkdir(exist_ok=True)
        (cred_dir / name).write_text(contents)
        (cred_dir / name).chmod(0o600)
    rc = mod.main(argv + ["--credentials-dir", str(cred_dir), "--env-file", str(env_file)])
    return rc, cred_dir


def test_rerun_keeps_an_existing_credential(tmp_path):
    rc, cred_dir = _run(tmp_path, [], {"api_hash_secret": "original-secret"})
    assert rc == 0
    assert (cred_dir / "api_hash_secret").read_text() == "original-secret"


def test_rotate_replaces_an_existing_credential(tmp_path):
    rc, cred_dir = _run(tmp_path, ["--rotate"], {"api_hash_secret": "original-secret"})
    assert rc == 0
    assert (cred_dir / "api_hash_secret").read_text() != "original-secret"


def test_new_credential_is_created_mode_600(tmp_path):
    rc, cred_dir = _run(tmp_path, [])
    assert rc == 0
    cred = cred_dir / "api_hash_secret"
    assert cred.exists()
    assert stat.S_IMODE(cred.stat().st_mode) == 0o600
    assert len(cred.read_text()) == 64


def test_env_value_beats_generation(tmp_path):
    mod = _load_module()
    cred_dir = tmp_path / "credentials"
    env_file = tmp_path / "blockchain.env"
    env_file.write_text("API_KEY_HASH_SECRET=from-env\nKEYSTORE_PASSWORD=envpw\n")
    rc = mod.main(["--credentials-dir", str(cred_dir), "--env-file", str(env_file)])
    assert rc == 0
    assert (cred_dir / "api_hash_secret").read_text() == "from-env"
    assert (cred_dir / "keystore_password").read_text() == "envpw"
