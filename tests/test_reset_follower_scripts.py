"""reset-follower-to-snapshot.sh and reset-follower-to-genesis.sh with a WAL left on disk.

A process that is killed instead of stopped leaves ``chain.db-wal`` next to ``chain.db``, and a host
running with ``DB_KEEPER_CONNECTION`` keeps its WAL on disk by design. A follower reset then has to:

* make the safety copy of the old database through SQLite, so it holds the commits that exist only
  in the WAL (a bare ``cp`` of ``chain.db`` drops them);
* remove the old ``-wal`` / ``-shm`` before the new file goes in, or SQLite replays those frames onto
  it and leaves a corrupt hybrid.

The scripts run for real here, against a temp data directory, with systemctl, ssh, rsync, chown and
install replaced by stubs on PATH. The genesis script hard-codes /etc/aitbc/blockchain.env, so a copy
with that path pointed into the temp directory is run instead.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SCRIPT = REPO_ROOT / "scripts" / "ops" / "reset-follower-to-snapshot.sh"
GENESIS_SCRIPT = REPO_ROOT / "scripts" / "ops" / "reset-follower-to-genesis.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("sqlite3") is None,
    reason="needs bash and the sqlite3 CLI",
)

OLD_ROWS = 2000
OLD_WAL_ONLY_ROWS = 500

STUBS = {
    "systemctl": "#!/bin/bash\nexit 0\n",
    "chown": "#!/bin/bash\nexit 0\n",
    # ssh <user@host> <command>: run the command locally, with the hub's data dir redirected.
    "ssh": '#!/bin/bash\nshift\ncmd="$1"\ncmd="${cmd//\\/var\\/lib\\/aitbc\\/data/$STUB_HUB_DATA}"\nexec bash -c "$cmd"\n',
    # rsync -avz --progress <user@host:path> <dest>
    "rsync": '#!/bin/bash\nsrc="${@: -2:1}"\ndest="${@: -1}"\ncp "${src#*:}" "$dest"\n',
    # install -D -m MODE -o OWNER -g GROUP <src> <dst>
    "install": (
        "#!/bin/bash\n"
        'while [ $# -gt 2 ]; do case "$1" in -D) shift ;; -m|-o|-g) shift 2 ;; *) break ;; esac; done\n'
        'mkdir -p "$(dirname "$2")"\ncp "$1" "$2"\nchmod 0640 "$2"\n'
    ),
}


def _make_db(path: Path, rows: int, tag: str, chain_id: str) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE block(chain_id TEXT, height INTEGER, hash TEXT, tag TEXT)")
    con.executemany("INSERT INTO block VALUES (?,?,?,?)", [(chain_id, i, f"0x{i:064x}", tag) for i in range(1, rows + 1)])
    con.commit()
    con.close()


def _follower_with_stale_wal(db: Path, chain_id: str) -> None:
    """The old follower DB as a kill -9 leaves it: 2000 rows in chain.db and 500 more only in chain.db-wal."""
    db.parent.mkdir(parents=True, exist_ok=True)
    staging = db.parent / "staging.db"
    writer = sqlite3.connect(staging)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE block(chain_id TEXT, height INTEGER, hash TEXT, tag TEXT)")
    writer.executemany(
        "INSERT INTO block VALUES (?,?,?,?)", [(chain_id, i, f"0x{i:064x}", "old") for i in range(1, OLD_ROWS + 1)]
    )
    writer.commit()
    writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    keeper = sqlite3.connect(staging)  # holds the WAL open, as a keeper does
    keeper.execute("PRAGMA journal_mode=WAL")
    keeper.execute("SELECT 1").fetchall()
    writer.executemany(
        "INSERT INTO block VALUES (?,?,?,?)",
        [(chain_id, i, f"0x{i:064x}", "old-wal") for i in range(OLD_ROWS + 1, OLD_ROWS + OLD_WAL_ONLY_ROWS + 1)],
    )
    writer.commit()
    for suffix in ("", "-wal", "-shm"):
        if Path(f"{staging}{suffix}").exists():
            shutil.copy2(f"{staging}{suffix}", f"{db}{suffix}")
    keeper.close()
    writer.close()
    for suffix in ("", "-wal", "-shm"):
        Path(f"{staging}{suffix}").unlink(missing_ok=True)
    assert Path(f"{db}-wal").stat().st_size > 0, "fixture must leave a non-empty WAL behind"


def _summary(path: Path) -> tuple[int, set[str], str]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT count(*) FROM block").fetchone()[0]
        tags = {r[0] for r in con.execute("SELECT DISTINCT tag FROM block")}
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    return rows, tags, integrity


@pytest.fixture
def sandbox(tmp_path: Path):
    chain_id = f"reset-test-{os.getpid()}"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in STUBS.items():
        stub = bindir / name
        stub.write_text(body)
        stub.chmod(0o755)
    data_dir = tmp_path / "data"
    hub_data = tmp_path / "hub-data"
    db = data_dir / chain_id / "chain.db"
    _follower_with_stale_wal(db, chain_id)
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "CHAIN_ID": chain_id,
        "DB_DIR": str(data_dir),
        "STUB_HUB_DATA": str(hub_data),
        "HUB": "hub.test.invalid",
        "SSH_USER": "root",
    }
    yield chain_id, db, hub_data, tmp_path, env
    Path(f"/tmp/aitbc-follower-snapshot-{chain_id}.db").unlink(missing_ok=True)


def _backups(db: Path, kind: str) -> list[Path]:
    return sorted(p for p in db.parent.glob(f"chain.db.{kind}.*") if not p.name.endswith(("-wal", "-shm")))


def test_the_fixture_really_is_a_stale_wal(sandbox) -> None:
    """Guards the other tests: the main file alone is missing the WAL-only rows."""
    _chain_id, db, _hub, _tmp, _env = sandbox
    copy = db.parent / "main-only.db"
    shutil.copy2(db, copy)
    rows, _tags, _integrity = _summary(copy)
    assert rows < OLD_ROWS + OLD_WAL_ONLY_ROWS


def test_snapshot_reset_installs_a_clean_database_and_a_whole_safety_copy(sandbox) -> None:
    chain_id, db, hub_data, _tmp, env = sandbox
    hub_db = hub_data / chain_id / "chain.db"
    hub_db.parent.mkdir(parents=True)
    _make_db(hub_db, 3000, "hub", chain_id)

    result = subprocess.run(["bash", str(SNAPSHOT_SCRIPT)], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr

    rows, tags, integrity = _summary(db)
    assert (rows, tags, integrity) == (3000, {"hub"}, "ok"), "the old WAL must not be replayed onto the new file"

    (backup,) = _backups(db, "pre-snapshot")
    rows, tags, integrity = _summary(backup)
    assert rows == OLD_ROWS + OLD_WAL_ONLY_ROWS, "the safety copy must include commits that exist only in the WAL"
    assert "old-wal" in tags and integrity == "ok"


def test_genesis_reset_keeps_a_whole_safety_copy_and_installs_cleanly(sandbox) -> None:
    chain_id, db, _hub, tmp_path, env = sandbox
    fixture = tmp_path / "fork.db"
    _make_db(fixture, 500, "genesis", chain_id)
    # The script hard-codes /etc/aitbc/blockchain.env; run a copy that points into the temp dir.
    source = GENESIS_SCRIPT.read_text()
    assert source.count('ENV_FILE="/etc/aitbc/blockchain.env"') == 1
    script = tmp_path / "reset-follower-to-genesis.sh"
    script.write_text(source.replace('ENV_FILE="/etc/aitbc/blockchain.env"', f'ENV_FILE="{tmp_path}/blockchain.env"'))

    result = subprocess.run(
        ["bash", str(script)], env={**env, "CHAIN_DB_FILE": str(fixture)}, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stdout + result.stderr

    assert _summary(db) == (500, {"genesis"}, "ok")
    (backup,) = _backups(db, "pre-reset")
    rows, tags, integrity = _summary(backup)
    assert rows == OLD_ROWS + OLD_WAL_ONLY_ROWS, "the safety copy must include commits that exist only in the WAL"
    assert "old-wal" in tags and integrity == "ok"


@pytest.mark.parametrize("script", [SNAPSHOT_SCRIPT, GENESIS_SCRIPT], ids=lambda p: p.name)
def test_scripts_are_valid_bash(script: Path) -> None:
    subprocess.run(["bash", "-n", str(script)], check=True)
