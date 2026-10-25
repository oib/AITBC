"""PG-TARGET-1 stream 2: governance money columns are exact decimal.

001 created every Decimal-backed column as ``sa.Float()`` —
``DOUBLE PRECISION`` on PostgreSQL — while the models declare
``Numeric(20, 8)``. Revision ``004`` converts them; ``passing_threshold``
stays Float because the model keeps it ``float``.

Runs on a temporary SQLite file; PostgreSQL coverage is a compile check
of the converted column under the postgresql dialect (``NUMERIC(20, 8)``,
not ``DOUBLE PRECISION``). No live database is touched.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

GOV_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = GOV_ROOT.parent.parent

_NUMERIC_COLUMNS = {
    "governance_profiles": {"voting_power", "delegated_power"},
    "proposals": {"quorum_required", "yes_votes", "no_votes", "votes_for", "votes_against", "votes_abstain"},
    "votes": {"voting_power_used", "power_at_snapshot", "delegated_power_at_snapshot", "voting_power", "vote_weight"},
    "delegations": {"voting_power"},
    "governance_tokens": {"token_balance", "staked_tokens", "voting_power", "rewards_claimed", "rewards_pending"},
    "token_stakes": {"amount_staked", "rewards_earned"},
    "dao_treasury": {"total_balance", "allocated_funds"},
    "transparency_reports": {"total_voting_power_participated", "treasury_inflow", "treasury_outflow"},
}


def _run_alembic(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path}/gov_migrations.db"
    env["PYTHONPATH"] = f"{GOV_ROOT / 'src'}:{REPO_ROOT}:{REPO_ROOT / 'packages/aitbc-shared'}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=GOV_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic {' '.join(args)} failed (exit {result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def _column_types(db_path: Path, table: str) -> dict[str, str]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {r[1]: r[2].upper() for r in con.execute(f"SELECT * FROM pragma_table_info('{table}')")}
    finally:
        con.close()


def test_upgrade_head_converts_money_columns_to_numeric(tmp_path: Path) -> None:
    db_path = tmp_path / "gov_migrations.db"
    _run_alembic(tmp_path, "upgrade", "head")
    still_float = [
        f"{table}.{col}"
        for table, cols in _NUMERIC_COLUMNS.items()
        for col in cols
        if "FLOAT" in _column_types(db_path, table).get(col, "") or "DOUBLE" in _column_types(db_path, table).get(col, "")
    ]
    assert not still_float, f"columns still Float after upgrade head: {still_float}"
    # passing_threshold is a ratio, not money — the model keeps it float.
    assert "FLOAT" in _column_types(db_path, "proposals").get("passing_threshold", "")


def test_downgrade_base_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "gov_migrations.db"
    _run_alembic(tmp_path, "upgrade", "head")
    _run_alembic(tmp_path, "downgrade", "-1")  # 004 -> 003: Float again
    assert "FLOAT" in _column_types(db_path, "dao_treasury").get("total_balance", "")
    _run_alembic(tmp_path, "upgrade", "head")
    assert "FLOAT" not in _column_types(db_path, "dao_treasury").get("total_balance", "")


def test_converted_column_compiles_as_postgresql_numeric() -> None:
    col = sa.Column("total_balance", sa.Numeric(20, 8), nullable=False)
    ddl = str(sa.schema.CreateTable(sa.Table("dao_treasury", sa.MetaData(), col)).compile(dialect=postgresql.dialect()))
    assert "NUMERIC(20, 8)" in ddl
    assert "DOUBLE" not in ddl and "FLOAT" not in ddl


def test_sqlite_rebuild_preserves_indexes(tmp_path: Path) -> None:
    """The batch rebuild must not silently eat indexes it does not own."""
    db_path = tmp_path / "gov_migrations.db"
    _run_alembic(tmp_path, "upgrade", "head")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        indexes = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        con.close()
    for expected in ("idx_tokens_holder", "idx_stakes_staker", "idx_exec_log_proposal"):
        assert expected in indexes, f"index lost in the SQLite rebuild: {expected}"
