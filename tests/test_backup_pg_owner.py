"""BACKUP-PG-OWNER-1: nightly dump must cover tables regardless of owner.

node0's aitbc_marketplace had 4 postgres-owned tables the role-scoped dump
could not lock. The backup now dumps as the postgres superuser via peer
auth, and the setup script reassigns foreign-owned tables on rerun.
"""

from pathlib import Path

BACKUP = Path("scripts/maintenance/aitbc-backup.sh")
SETUP = Path("scripts/deployment/setup_postgresql_databases.sh")


def test_backup_dumps_as_superuser():
    src = BACKUP.read_text()
    assert "sudo -u postgres pg_dump" in src
    # role-scoped dump with the same-named user is gone from the dump path
    assert 'PGPASSWORD="$pg_pw" pg_dump -U "$pg_user" -h localhost "$pg_db"' not in src


def test_backup_still_removes_failed_artifact():
    src = BACKUP.read_text()
    assert 'rm -f "${BACKUP_DIR}/postgres_${pg_db}.sql.gz"' in src


def test_setup_reassigns_foreign_owned_tables():
    src = SETUP.read_text()
    assert "tableowner <>" in src
    assert "OWNER TO" in src
    assert "foreign_tables" in src


def test_backup_covers_previously_unlisted_dbs():
    """#1528: DBs empty at the 24 Oct census must stay in PG_DBS.

    'Empty fleet-wide' was never a guarantee — coordinator-api's
    DATABASE_URL once pointed at aitbc_coordinator while the app ran
    SQLite (PG-TARGET-1). An unlisted DB that later receives writes is
    silently unbacked-up; an empty pg_dump costs ~20 KB, so every DB the
    setup script can create must be listed (the existence check skips
    hosts where it was never created).
    """
    src = BACKUP.read_text()
    pg_dbs_block = src.split("PG_DBS=(", 1)[1].split(")", 1)[0]
    for db in (
        "aitbc",
        "aitbc_ai",
        "aitbc_coordinator",
        "aitbc_exchange",
        "aitbc_wallet",
        "aitbc_governance",
        "aitbc_marketplace",
        "aitbc_trading",
        "aitbc_mempool",
        "aitbc_gpu",
        "aitbc_poolhub",
    ):
        assert f'"{db}"' in pg_dbs_block, f"{db} missing from PG_DBS"
