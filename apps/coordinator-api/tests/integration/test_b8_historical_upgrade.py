"""B-8 residual: historical-schema upgrade regression.

The eight tenant_* tables are only created by ``001_initial_migration``'s
``create_all``, which never runs on an already-stamped database — proven on
the 2026-08-09 coordinator.db backup (stamped ``236edfbd9728``): a real
``alembic upgrade head`` left all eight missing until migration
``e7f2a9c4b1d0`` was added. That upgrade also surfaced a non-constant
``server_default=sa.text("[]")`` in ``5d8339a13a12`` (fixed to ``'[]'``).

This test emulates the historical condition: build the current schema, drop
the tenant tables, stamp the database back to the revision *before* the
current head, then ``upgrade head`` and assert the schema converges to the
declared models — plus a sentinel row in an untouched table survives.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from .test_b8_schema_conformance import _COORDINATOR_ROOT, _get_model_columns, _run_alembic

_TENANT_TABLES = [
    "tenants",
    "tenant_users",
    "tenant_quotas",
    "usage_records",
    "invoices",
    "tenant_api_keys",
    "tenant_audit_logs",
    "tenant_metrics",
]


def _previous_head_revision() -> str:
    """Resolve the single down_revision of the current head."""
    cfg = Config(str(_COORDINATOR_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_COORDINATOR_ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    assert head, "no migration head found"
    down = script.get_revision(head).down_revision
    if isinstance(down, tuple):
        assert len(down) == 1, f"head has multiple parents: {down}"
        down = down[0]
    assert isinstance(down, str)
    return down


def test_historical_schema_upgrade_converges(tmp_path: Path):
    # 1. Build the current schema, then roll it back to the pre-head era:
    #    stamp the previous revision and drop the tenant tables, emulating a
    #    database created before the multitenant feature existed.
    db_path = _run_alembic(tmp_path, "upgrade", "head")
    prev = _previous_head_revision()

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        for table in _TENANT_TABLES:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
        # Sentinel data in a table the upgrade must not disturb.
        conn.execute(text("DELETE FROM global_marketplace_configs"))
        conn.execute(
            text(
                "INSERT INTO global_marketplace_configs "
                "(id, config_key, config_value, config_type, description, category, "
                "is_public, is_encrypted, created_at, updated_at) "
                "VALUES ('cfg_b8_sentinel', 'b8_sentinel', 'survived', 'string', "
                "'B-8 sentinel', 'test', 1, 0, '2026-09-08 00:00:00', '2026-09-08 00:00:00')"
            )
        )
    engine.dispose()

    _run_alembic(tmp_path, "stamp", prev)

    # 2. Upgrade from the frozen historical state.
    _run_alembic(tmp_path, "upgrade", "head")

    # 3. Converged: every declared table exists with matching columns.
    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    db_tables: dict[str, set[str]] = {}
    for table_name in inspector.get_table_names():
        if table_name == "alembic_version":
            continue
        db_tables[table_name] = {col["name"] for col in inspector.get_columns(table_name)}

    model_tables = _get_model_columns()
    missing = set(model_tables) - set(db_tables)
    extra = set(db_tables) - set(model_tables)
    assert not missing, f"Tables missing after historical upgrade: {missing}"
    assert not extra, f"Extra tables after historical upgrade: {extra}"

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT config_value FROM global_marketplace_configs WHERE id = 'cfg_b8_sentinel'")
        ).fetchall()
    engine.dispose()
    assert rows == [("survived",)], "sentinel row lost during upgrade"
