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
