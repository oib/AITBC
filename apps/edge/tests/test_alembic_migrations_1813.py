"""#1813: edge schema migrations must actually run, and must converge legacy DBs.

``init_db`` only calls ``SQLModel.metadata.create_all`` — missing tables are
created, existing ones are never ALTERed — and nothing ran alembic at startup.
aitbc-test-shop's ``compute_requests`` silently lacked ``escrow_id`` /
``escrow_amount`` until patched by hand during #1809 remediation. The unit now
carries an ``ExecStartPre`` alembic step (same pattern as coordinator-api);
these tests pin both halves: the unit invokes it, and ``alembic upgrade head``
converges a pre-migration database to head.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
EDGE_DIR = REPO_ROOT / "apps" / "edge"
HEAD_REVISION = "c9f2a4b6d8e1"

# The exact shape aitbc-test-shop's edge DB had before remediation: every
# column the pre-escrow models declared, non-unique request_id index, and no
# alembic_version table.
LEGACY_COMPUTE_REQUESTS_DDL = """
CREATE TABLE compute_requests (
    id VARCHAR NOT NULL,
    request_id VARCHAR NOT NULL,
    gpu_id VARCHAR NOT NULL,
    model_name VARCHAR NOT NULL,
    input_data JSON,
    priority VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    owner_id VARCHAR,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    started_at DATETIME,
    completed_at DATETIME,
    error VARCHAR,
    extra_data JSON,
    PRIMARY KEY (id)
);
CREATE INDEX ix_compute_requests_request_id ON compute_requests (request_id);
CREATE INDEX ix_compute_requests_status ON compute_requests (status);
CREATE INDEX ix_compute_requests_owner_id ON compute_requests (owner_id);
"""


def test_edge_unit_runs_alembic_before_start() -> None:
    unit = (EDGE_DIR / "aitbc-edge.service").read_text()
    exec_start_pre = re.search(r"^ExecStartPre=(.*)$", unit, re.MULTILINE)
    assert exec_start_pre, "aitbc-edge.service has no ExecStartPre"
    assert "alembic" in exec_start_pre.group(1) and "upgrade head" in exec_start_pre.group(1)
    # Ordering matters: migrations must precede the service process.
    assert unit.index("ExecStartPre=") < unit.index("ExecStart=")


@pytest.mark.timeout(120)
def test_alembic_upgrade_converges_legacy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "aitbc_edge_legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(LEGACY_COMPUTE_REQUESTS_DDL)

    from alembic import command
    from alembic.config import Config

    from aitbc_edge.config import settings

    # env.py resolves the target through settings.database.effective_url —
    # point it at the scratch DB, not the deployed one.
    monkeypatch.setattr(settings.database, "url", f"sqlite:///{db_path}")

    cfg = Config(str(EDGE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(EDGE_DIR / "alembic"))
    command.upgrade(cfg, "head")

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(compute_requests)")}
        assert {"escrow_id", "escrow_amount"} <= columns
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(compute_requests)")}
        assert "ix_compute_requests_escrow_id" in indexes
        # request_id must have been converged to unique by 9f2c7a1e4b6d
        unique_flag = {row[1]: row[2] for row in conn.execute("PRAGMA index_list(compute_requests)")}
        assert unique_flag.get("ix_compute_requests_request_id") == 1
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        assert version == (HEAD_REVISION,)

    # A second upgrade on the converged DB is a no-op, not an error.
    command.upgrade(cfg, "head")
