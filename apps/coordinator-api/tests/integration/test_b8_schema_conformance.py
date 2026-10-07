"""
B-8: Schema-conformance test for the coordinator-api migration graph.

The 001_initial migration is a frozen baseline: explicit ``create_table`` /
``create_index`` DDL generated at commit f7df5b478 (it previously ran
``SQLModel.metadata.create_all`` dynamically, so a fresh deploy received
whatever the current models declared). Subsequent migrations add columns on
top, guarded by ``if_not_exists`` / inspect helpers.

This test asserts that a fresh `alembic upgrade head` produces a schema that
matches the declared models. If it doesn't, there's drift between the
migration graph and the models — which means either a migration is missing
or a model column was added without a migration.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

_COORDINATOR_ROOT = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = _COORDINATOR_ROOT.parent.parent


def _run_alembic(tmp_path: Path, *args: str) -> Path:
    """Run alembic and return the DB path that was used."""
    db_path = tmp_path / "test_conformance.db"
    env = os.environ.copy()
    # The alembic subprocess imports coordinator_api.config.settings, which
    # honours /etc/aitbc/*.env on live nodes. Skip env files and drop inherited
    # database URLs so an earlier test's leaked DATABASE_URL/SQLITE_URL cannot
    # redirect the migration -- _get_model_columns already does the same for
    # its subprocess.
    env["AITBC_SKIP_ENV_FILES"] = "1"
    for var in (
        "SQLITE_URL",
        "MARKET_DATABASE_URL",
        "DATABASE_ADAPTER",
        "DB_TYPE",
        "ENVIRONMENT",
        "APP_ENV",
        "NODE_ENV",
    ):
        env.pop(var, None)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["PYTHONPATH"] = f"{_COORDINATOR_ROOT / 'src'}:{REPO_ROOT}"
    env["AUDIT_LOG_DIR"] = str(tmp_path / "audit")
    env["TEST_MODE"] = "true"

    cmd = [sys.executable, "-m", "alembic", *args]
    result = subprocess.run(
        cmd,
        cwd=_COORDINATOR_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic {' '.join(args)} failed (exit {result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return db_path


def _get_model_columns() -> dict[str, set[str]]:
    """Return {table_name: {column_names}} from the declared SQLModel metadata.

    Runs in a fresh subprocess so other test modules that share the global
    SQLModel.metadata registry do not pollute the declared model set.
    """
    script = """
import json
import coordinator_api.main  # noqa: F401
import coordinator_api.models.multitenant  # noqa: F401
from sqlmodel import SQLModel

tables = {
    name: sorted(col.name for col in table.columns)
    for name, table in SQLModel.metadata.tables.items()
}
print(json.dumps(tables))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{_COORDINATOR_ROOT / 'src'}:{REPO_ROOT}"
    env["AITBC_SKIP_ENV_FILES"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_COORDINATOR_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"failed to collect coordinator model columns:\n{result.stderr}")
    tables = json.loads(result.stdout.strip().splitlines()[-1])
    return {name: set(cols) for name, cols in tables.items()}


def test_fresh_upgrade_head_matches_declared_models(tmp_path: Path):
    """A fresh `alembic upgrade head` should produce a schema matching the models.

    This catches:
    - Model columns added without a migration (schema would be missing them)
    - Migration columns that no longer exist in models (schema would have extras)
    - The frozen 001_initial baseline drifting from the migration graph
    """
    db_path = _run_alembic(tmp_path, "upgrade", "head")

    # Inspect the resulting schema
    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    db_tables: dict[str, set[str]] = {}
    for table_name in inspector.get_table_names():
        if table_name == "alembic_version":
            continue
        db_tables[table_name] = {col["name"] for col in inspector.get_columns(table_name)}
    engine.dispose()

    # Get the declared model columns
    model_tables = _get_model_columns()

    # Compare
    db_table_names = set(db_tables.keys())
    model_table_names = set(model_tables.keys())

    missing_tables = model_table_names - db_table_names
    extra_tables = db_table_names - model_table_names

    assert not missing_tables, f"Tables in models but missing from DB after upgrade: {missing_tables}"
    assert not extra_tables, f"Tables in DB after upgrade but not in models: {extra_tables}"

    for table_name in model_table_names & db_table_names:
        model_cols = model_tables[table_name]
        db_cols = db_tables[table_name]
        missing_cols = model_cols - db_cols
        extra_cols = db_cols - model_cols
        assert not missing_cols, f"Table '{table_name}': columns in models but missing from DB: {missing_cols}"
        assert not extra_cols, f"Table '{table_name}': columns in DB but not in models: {extra_cols}"


def test_alembic_head_is_not_initial_migration(tmp_path: Path):
    """The alembic version table should not be stuck at initial_migration."""
    db_path = _run_alembic(tmp_path, "upgrade", "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        version = result.scalar()
    engine.dispose()

    assert version is not None, "alembic_version table is empty after upgrade head"
    assert version != "initial_migration", "upgrade head stopped at initial_migration — subsequent migrations didn't run"

    # The chain must end at the single head reported by alembic.
    cfg = Config(str(_COORDINATOR_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_COORDINATOR_ROOT / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, f"expected exactly one alembic head, got {heads}"
    assert version == heads[0], f"database ended at {version}, not the single head {heads[0]}"


def _norm_col_type(declared: str) -> str:
    """sqlite ignores VARCHAR lengths and NUMERIC precision — normalize away."""
    return re.sub(r"\(\s*\d+(\s*,\s*\d+)?\s*\)", "", (declared or "").upper()).strip()


def _semantic_schema(db_path: Path) -> dict[str, dict]:
    """Per-table semantic signature: columns, primary key, indexes, foreign keys.

    Normalizations (all verified cosmetic — sqlite treats the variants
    identically):
    - column position is ignored: later migrations add columns via ALTER TABLE,
      which appends; the models declare them in place.
    - VARCHAR(N)/NUMERIC(P,S) spellings are normalized to their base type.
    - ``sqlite_autoindex_*`` names depend on constraint declaration order and
      differ between the chain's create order and the models'; they compare by
      (unique, columns).
    - ``agent_executions.agent_id`` FKs ``agent_reputation_old`` on the chain
      side — a rename artifact kept by a table-rebuild migration; the model
      targets ``agent_reputation``. Allowlisted explicitly.
    """
    engine = create_engine(f"sqlite:///{db_path}")
    con = engine.raw_connection().connection
    out: dict[str, dict] = {}
    tables = sorted(
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version' AND name NOT LIKE 'sqlite_%'"
        )
    )
    for table in tables:
        cols: set[tuple] = set()
        pk: set[str] = set()
        for _cid, name, typ, notnull, _dflt, pkn in con.execute(f'PRAGMA table_info("{table}")'):
            cols.add((name, _norm_col_type(typ), bool(notnull), bool(pkn)))
            if pkn:
                pk.add(name)
        indexes: set[tuple] = set()
        for _seq, iname, unique, _origin, _partial in con.execute(f'PRAGMA index_list("{table}")'):
            icols = tuple(r[2] for r in con.execute(f'PRAGMA index_info("{iname}")'))
            # Unique enforcement is the semantic content; the name is cosmetic
            # (``sqlite_autoindex_*`` numbering and constraint-vs-standalone
            # naming differ between build paths).
            idx_name = "<unique>" if unique else iname
            indexes.add((idx_name, bool(unique), icols))
        fks: set[tuple] = set()
        for row in con.execute(f'PRAGMA foreign_key_list("{table}")'):
            target = "agent_reputation" if row[2] == "agent_reputation_old" else row[2]
            fks.add((row[3], target, row[4]))
        out[table] = {"cols": cols, "pk": pk, "indexes": indexes, "fks": fks}
    engine.dispose()
    return out


def _build_metadata_db(tmp_path: Path) -> Path:
    """Build a database straight from SQLModel.metadata in a clean subprocess."""
    db_path = tmp_path / "test_conformance_meta.db"
    script = """
import coordinator_api.main  # noqa: F401
import coordinator_api.models.multitenant  # noqa: F401
from sqlalchemy import create_engine
from sqlmodel import SQLModel
import sys
SQLModel.metadata.create_all(create_engine(sys.argv[1]))
"""
    env = os.environ.copy()
    env["AITBC_SKIP_ENV_FILES"] = "1"
    env["PYTHONPATH"] = f"{_COORDINATOR_ROOT / 'src'}:{REPO_ROOT}"
    env["AUDIT_LOG_DIR"] = str(tmp_path / "audit_meta")
    env["TEST_MODE"] = "true"
    result = subprocess.run(
        [sys.executable, "-c", script, f"sqlite:///{db_path}"],
        cwd=_COORDINATOR_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"failed to build metadata db:\n{result.stderr}")
    return db_path


def test_chain_schema_matches_model_schema_semantically(tmp_path: Path):
    """Deep compare: the chain-built schema must equal the model-built schema.

    Beyond table/column name sets this checks nullability, primary keys,
    indexes and foreign keys, tolerating only the documented cosmetic classes
    (column position, VARCHAR/NUMERIC spellings, autoindex numbering, the
    agent_reputation->_old FK rename artifact). Any real drift prints the
    differing table and column.
    """
    chain_db = _run_alembic(tmp_path, "upgrade", "head")
    meta_db = _build_metadata_db(tmp_path)

    chain = _semantic_schema(chain_db)
    meta = _semantic_schema(meta_db)

    missing = sorted(set(meta) - set(chain))
    extra = sorted(set(chain) - set(meta))
    assert not missing, f"tables missing from chain-built DB: {missing}"
    assert not extra, f"extra tables in chain-built DB: {extra}"

    problems: list[str] = []
    for table in sorted(set(chain) & set(meta)):
        for key in ("cols", "pk", "indexes", "fks"):
            only_chain = chain[table][key] - meta[table][key]
            only_meta = meta[table][key] - chain[table][key]
            for item in sorted(only_chain, key=str):
                problems.append(f"{table}.{key} only in chain DB: {item}")
            for item in sorted(only_meta, key=str):
                problems.append(f"{table}.{key} only in model schema: {item}")
    assert not problems, "semantic schema drift:\n" + "\n".join(problems)


def test_001_downgrade_raises(tmp_path: Path):
    """Downgrading below the frozen baseline must fail loudly, not drop all."""
    _run_alembic(tmp_path, "upgrade", "initial_migration")

    db_path = tmp_path / "test_conformance.db"
    env = os.environ.copy()
    env["AITBC_SKIP_ENV_FILES"] = "1"
    for var in ("SQLITE_URL", "MARKET_DATABASE_URL", "DATABASE_ADAPTER", "DB_TYPE", "ENVIRONMENT", "APP_ENV", "NODE_ENV"):
        env.pop(var, None)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["PYTHONPATH"] = f"{_COORDINATOR_ROOT / 'src'}:{REPO_ROOT}"
    env["AUDIT_LOG_DIR"] = str(tmp_path / "audit")
    env["TEST_MODE"] = "true"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=_COORDINATOR_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "downgrade below the baseline unexpectedly succeeded"
    assert "the baseline cannot be downgraded" in result.stderr, (
        f"expected the frozen-baseline error, got:\n{result.stderr[-2000:]}"
    )


def test_001_baseline_is_frozen() -> None:
    """Regression guard: 001_initial_migration must stay explicit DDL.

    The baseline was frozen because a dynamic ``create_all`` gives every fresh
    install a different schema (whatever today's models are) and lets the
    migration graph depend on tables it never created. If 001 ever imports
    application code or calls ``create_all``/``drop_all`` again, this fails.
    """
    src = (_COORDINATOR_ROOT / "alembic" / "versions" / "001_initial_migration.py").read_text()
    assert "create_all(" not in src, "001 must not call SQLModel.metadata.create_all"
    assert "drop_all(" not in src, "001 must not call SQLModel.metadata.drop_all"
    assert "import coordinator_api" not in src, "001 must not import the application"
    assert "op.create_table" in src, "001 must contain frozen create_table DDL"
