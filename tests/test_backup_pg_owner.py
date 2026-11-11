"""BACKUP-PG-OWNER-1: nightly dump must cover tables regardless of owner.

node0's aitbc_marketplace had 4 postgres-owned tables the role-scoped dump
could not lock. The backup now dumps as the postgres superuser via peer
auth, and the setup script reassigns foreign-owned tables on rerun.
"""

import re
from pathlib import Path

BACKUP = Path("scripts/maintenance/aitbc-backup.sh")
SETUP = Path("scripts/deployment/setup_postgresql_databases.sh")

# A PG_DBS array element is a line containing ONLY a quoted name — a
# commented-out `#"db"` line must NOT satisfy membership (#1777: the old
# substring check passed with the entry commented out).
_PG_DBS_ENTRY = re.compile(r'^\s*"([a-z0-9_]+)"\s*$', re.MULTILINE)
_SETUP_DB = re.compile(r'^setup_database "([a-z0-9_]+)"', re.MULTILINE)


def _pg_dbs(src: str) -> set[str]:
    block = src.split("PG_DBS=(", 1)[1].split(")", 1)[0]
    return set(_PG_DBS_ENTRY.findall(block))


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
    dbs = _pg_dbs(BACKUP.read_text())
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
        assert db in dbs, f"{db} missing from PG_DBS"


def test_backup_covers_node0_live_only_dbs():
    """#1777: node0 carries PG databases no repo script creates.

    Live census (11 Nov): aitbc_edge (17 tables — node0's pool-hub env
    DSNs point at it), aitbc_prod (126 tables, coordinator-scale schema),
    aitbc_staging (empty today). They must stay in PG_DBS or their data is
    silently unbacked-up.
    """
    dbs = _pg_dbs(BACKUP.read_text())
    for db in ("aitbc_edge", "aitbc_prod", "aitbc_staging"):
        assert db in dbs, f"{db} missing from PG_DBS"


def test_backup_covers_every_db_the_setup_script_creates():
    """Every `setup_database` target must be in PG_DBS — a new service DB
    added to provisioning without a backup entry is silently uncovered."""
    pg_dbs = _pg_dbs(BACKUP.read_text())
    created = set(_SETUP_DB.findall(SETUP.read_text()))
    assert created, "no setup_database calls parsed — check the regex"
    missing = created - pg_dbs
    assert not missing, f"setup creates {sorted(missing)} but PG_DBS does not list them"
