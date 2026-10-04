"""End-to-end tests for scripts/maintenance/aitbc-backup.sh hardening.

The script runs as root under systemd against fleet paths, so tests drive it
with every external dependency replaced: data dirs are env-pointed at tmp
dirs (BACKUP_BASE/CHAIN_DB_DIR/KEYSTORE_DIR/WALLETS_DIR/LEGACY_WALLET_DIRS/
ETC_AITBC_DIR/ETC_PROMETHEUS_DIR keep their production defaults) and
redis-cli/sqlite3/gpg/systemd-cat/sudo/psql/python are stubs on PATH that
record what they were asked to do.
"""

import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "maintenance" / "aitbc-backup.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")

# Stubs are written into a PATH-first bin dir per test. systemd-cat appends
# "[priority] message" lines to $STUB_LOG; gpg records each --encrypt source
# basename to $GPG_CALLS; redis-cli replies come from env vars.
STUBS = {
    "systemd-cat": '#!/bin/sh\nmsg="$(cat)"; printf "[%s] %s\\n" "$4" "$msg" >> "$STUB_LOG"\n',
    "sudo": '#!/bin/sh\nwhile [ "$1" = "-u" ]; do shift 2; done; exec "$@"\n',
    "psql": "#!/bin/sh\nexit 0\n",
    "pg_dump": "#!/bin/sh\nexit 1\n",
    "sqlite3": '#!/bin/sh\necho "CREATE TABLE t(x INTEGER);"\n',
    "redis-cli": """#!/bin/sh
case "$1" in
  BGSAVE)
    printf '%s\\n' "${REDIS_STUB_BGSAVE:-Background saving started}"
    exit "${REDIS_STUB_BGSAVE_RC:-0}";;
  CONFIG)
    case "$3" in
      dir) printf 'dir\\n%s\\n' "${REDIS_STUB_DIR}";;
      dbfilename) printf 'dbfilename\\n%s\\n' "${REDIS_STUB_DBF:-dump.rdb}";;
    esac;;
esac
""",
    "gpg": """#!/bin/sh
out=""; prev=""; src=""
for a in "$@"; do
  [ "$prev" = "-o" ] && out="$a"
  prev="$a"; src="$a"
done
basename "$src" >> "$GPG_CALLS"
cp "$src" "$out"
""",
    # shred -u <file>: last argument is the file; stub removes it.
    "shred": '#!/bin/sh\nlast=""; for a in "$@"; do last="$a"; done; rm -f "$last"\n',
    "python-stub": "#!/bin/sh\nexit 0\n",
}


def _snap_name(days_ago: int) -> str:
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y%m%d_010203")


def _make_snapshot(base: Path, name: str, good: bool = True, fresh_mtime: bool = False) -> Path:
    d = base / name
    d.mkdir(parents=True)
    if good:
        (d / "chain_ait-hub.aitbc.bubuit.net_chain.db.gz").write_bytes(b"\x1f\x8bFAKE")
    else:
        (d / "postgres_aitbc_market.sql.gz").write_bytes(b"\x1f\x8bFAKE")
    if fresh_mtime:
        now = time.time()
        os.utime(d, (now, now))
    return d


@pytest.fixture
def env(tmp_path):
    """Hermetic environment for one backup run."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in STUBS.items():
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)

    chain_data = tmp_path / "chaindata" / "ait-hub.aitbc.bubuit.net"
    chain_data.mkdir(parents=True)
    (chain_data / "chain.db").write_bytes(b"db")

    keystore = tmp_path / "keystore"
    keystore.mkdir()
    (keystore / "key.json").write_text("{}")
    wallets = tmp_path / "wallets"
    wallets.mkdir()
    (wallets / "w.json").write_text("{}")
    etc_aitbc = tmp_path / "etc-aitbc"
    etc_aitbc.mkdir()
    (etc_aitbc / "blockchain.env").write_text("X=1\n")
    etc_prometheus = tmp_path / "etc-prometheus"
    etc_prometheus.mkdir()
    redis_dir = tmp_path / "redisdir"
    redis_dir.mkdir()
    (redis_dir / "dump.rdb").write_bytes(b"RDBFILE")

    base = tmp_path / "backups"
    base.mkdir()

    e = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "BACKUP_BASE": str(base),
        "CHAIN_DB_DIR": str(chain_data.parent),
        "KEYSTORE_DIR": str(keystore),
        "WALLETS_DIR": str(wallets),
        "LEGACY_WALLET_DIRS": str(tmp_path / "no-legacy"),
        "ETC_AITBC_DIR": str(etc_aitbc),
        "ETC_PROMETHEUS_DIR": str(etc_prometheus),
        "PYTHON": str(bin_dir / "python-stub"),
        "STUB_LOG": str(tmp_path / "backup.log"),
        "GPG_CALLS": str(tmp_path / "gpg_calls"),
        "REDIS_STUB_DIR": str(redis_dir),
        "RETENTION_DAYS": "30",
        "BACKUP_KEEP_MIN_GOOD": "7",
    }
    return SimpleNamespace(base=base, env=e, tmp=tmp_path)


def _run(env: SimpleNamespace, **overrides) -> subprocess.CompletedProcess:
    e = dict(env.env)
    e.update(overrides)
    return subprocess.run(["bash", str(SCRIPT)], env=e, capture_output=True, text=True, timeout=180)


def _log(env: SimpleNamespace) -> str:
    log = env.tmp / "backup.log"
    return log.read_text() if log.exists() else ""


def _dir_names(base: Path) -> set:
    return {d.name for d in base.iterdir() if d.is_dir()}


def test_prune_keeps_newest_n_good(env):
    """Keep-min is enforced on good snapshots only; the newest N survive."""
    _make_snapshot(env.base, _snap_name(45))  # good, newest-2 after the run
    _make_snapshot(env.base, _snap_name(50))  # good, pruned (3rd)
    _make_snapshot(env.base, _snap_name(60))  # good, pruned (4th)
    _make_snapshot(env.base, _snap_name(70), good=False)  # bad: never counts
    r = _run(env, BACKUP_KEEP_MIN_GOOD="2")
    assert r.returncode == 0
    names = _dir_names(env.base)
    # today's snapshot + the newest surviving good one
    assert _snap_name(45) in names
    assert len(names) == 2
    log = _log(env)
    assert f"removing '{_snap_name(50)}'" in log
    assert f"removing '{_snap_name(60)}'" in log
    assert "among the last 2 good snapshots" in log


def test_prune_ignores_mtime(env):
    """A fresh mtime must not rescue an old-named dir (the Sep-8-touch bug)."""
    old = _make_snapshot(env.base, _snap_name(80), fresh_mtime=True)
    assert time.time() - old.stat().st_mtime < 60
    r = _run(env, BACKUP_KEEP_MIN_GOOD="1")
    assert r.returncode == 0
    assert not old.exists()
    assert f"removing '{_snap_name(80)}'" in _log(env)


def test_no_prune_when_run_produces_no_good_snapshot(env):
    """A failed run must never empty the vault."""
    old_good = _make_snapshot(env.base, _snap_name(90))
    old_bad = _make_snapshot(env.base, _snap_name(95), good=False)
    r = _run(env, CHAIN_DB_DIR=str(env.tmp / "missing-chain-dir"))
    assert r.returncode == 0
    assert old_good.exists() and old_bad.exists()
    assert "pruning skipped entirely" in _log(env)


def test_prune_skips_unparseable_names(env):
    """Names that are not YYYYMMDD_HHMMSS are never touched."""
    for name in ("manual_copy", "2026-13-99_wrong", "keepme"):
        (env.base / name).mkdir()
    old = _make_snapshot(env.base, _snap_name(75))
    r = _run(env, BACKUP_KEEP_MIN_GOOD="1")
    assert r.returncode == 0
    names = _dir_names(env.base)
    assert {"manual_copy", "2026-13-99_wrong", "keepme"} <= names
    assert not old.exists()
    log = _log(env)
    assert "'manual_copy' does not match YYYYMMDD_HHMMSS" in log


def test_redis_noauth_is_error_and_nonzero(env):
    """NOAUTH must surface as an error and fail the run, not warn-and-exit-0."""
    r = _run(env, REDIS_STUB_BGSAVE="NOAUTH Authentication required.")
    assert r.returncode == 1
    log = _log(env)
    assert "Redis BGSAVE FAILED" in log
    assert "NOAUTH Authentication required." in log
    today = [d for d in env.base.iterdir() if d.is_dir()][0]
    assert not (today / "redis.rdb").exists()


def test_redis_ok_copies_rdb(env):
    r = _run(env)
    assert r.returncode == 0
    today = [d for d in env.base.iterdir() if d.is_dir()][0]
    assert (today / "redis.rdb").read_bytes() == b"RDBFILE"


def test_gpg_default_artifact_list_unchanged(env):
    r = _run(env, BACKUP_GPG_RECIPIENT="ops@example.invalid")
    assert r.returncode == 0
    calls = (env.tmp / "gpg_calls").read_text().split()
    assert calls == ["keystore.tar.gz", "wallets.tar.gz", "etc-aitbc.tar.gz"]
