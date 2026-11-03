"""#882: create_aitbc_user.sh must not recursively chown an installed node.

On base it ran ``chown -R aitbc:aitbc`` over /var/lib/aitbc, /var/log/aitbc
and /run/aitbc — on an installed node that rewrites the owner of every
chain database, keystore file and log already on disk — and it forced
``chmod 750 root:aitbc`` on /etc/aitbc even when the directory predated
the script.

The fix keeps the whole thing idempotent: directories are chowned
non-recursively (the dir itself, not existing contents), the keystore
stays root-owned, and /etc/aitbc's mode is only set when the script
itself creates the directory. All paths are env-overridable so tests and
non-standard layouts never touch the real /var, /etc or /run.
"""

import os
import pwd
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deployment" / "create_aitbc_user.sh"

pytestmark = pytest.mark.skipif(os.geteuid() != 0, reason="needs root for chown")


def _src() -> str:
    return SCRIPT.read_text()


def test_no_recursive_chown_in_script():
    assert not __import__("re").search(r"chown\s+-[a-zA-Z]*R", _src()), "recursive chown still present"


def _stub_bin(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    # Identity tools: user/group already exist; mutating tools are no-ops.
    (bindir / "getent").write_text("#!/bin/bash\nexit 0\n")
    (bindir / "id").write_text('#!/bin/bash\nif [ "$1" = "-u" ]; then echo 999; fi\nexit 0\n')
    for stub in ("groupadd", "useradd", "usermod"):
        (bindir / stub).write_text("#!/bin/bash\nexit 0\n")
    for f in bindir.iterdir():
        f.chmod(0o755)
    return bindir


def _run(tmp_path, etc_exists=True, log_exists=True):
    lib = tmp_path / "lib" / "aitbc"
    log = tmp_path / "log" / "aitbc"
    run = tmp_path / "run" / "aitbc"
    etc = tmp_path / "etc" / "aitbc"
    for d in (lib, run):
        d.mkdir(parents=True, exist_ok=True)
    if log_exists:
        log.mkdir(parents=True, exist_ok=True)
    if etc_exists:
        etc.mkdir(parents=True, exist_ok=True)
        etc.chmod(0o755)
    # Pre-existing data that must keep its owner.
    (lib / "data").mkdir(exist_ok=True)
    chain_db = lib / "data" / "chain.db"
    chain_db.write_text("x")
    keystore = lib / "keystore"
    keystore.mkdir(exist_ok=True)
    (keystore / "genesis-wallet.json").write_text("{}")

    bindir = _stub_bin(tmp_path)
    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["AITBC_LIB_DIR"] = str(lib)
    env["AITBC_LOG_DIR"] = str(log)
    env["AITBC_RUN_DIR"] = str(run)
    env["AITBC_ETC_DIR"] = str(etc)
    r = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    return r, lib, log, run, etc, chain_db, keystore


def test_existing_data_is_not_recursively_chowned(tmp_path):
    r, lib, _log, _run_d, _etc, chain_db, keystore = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    aitbc_uid = pwd.getpwnam("aitbc").pw_uid
    assert lib.stat().st_uid == aitbc_uid, "top-level dir itself should be aitbc-owned"
    assert chain_db.stat().st_uid == 0, "existing data was recursively chowned to aitbc"
    assert keystore.stat().st_uid == 0, "keystore must stay root-owned"


def test_installed_etc_aitbc_mode_untouched(tmp_path):
    r, _lib, _log, _run_d, etc, _db, _ks = _run(tmp_path, etc_exists=True)
    assert r.returncode == 0, r.stderr
    assert stat.S_IMODE(etc.stat().st_mode) == 0o755, "script changed mode of a pre-existing /etc/aitbc"


def test_fresh_etc_aitbc_gets_restricted_mode(tmp_path):
    r, _lib, _log, _run_d, etc, _db, _ks = _run(tmp_path, etc_exists=False)
    assert r.returncode == 0, r.stderr
    assert stat.S_IMODE(etc.stat().st_mode) == 0o750


def test_second_run_is_idempotent(tmp_path):
    r1, _l, _lo, _ru, _e, _d, _k = _run(tmp_path)
    assert r1.returncode == 0, r1.stderr
    r2, _l, _lo, _ru, _e, _d, _k = _run(tmp_path)
    assert r2.returncode == 0, r2.stderr
