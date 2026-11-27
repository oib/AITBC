"""B-8 residual: historical-schema upgrade regression.

The eight tenant_* tables are only created by the ``001_initial_migration``
baseline, which never runs on an already-stamped database — proven on
the 2026-08-09 coordinator.db backup (stamped ``236edfbd9728``): a real
``alembic upgrade head`` left all eight missing until migration
``e7f2a9c4b1d0`` was added. That upgrade also surfaced a non-constant
``server_default=sa.text("[]")`` in ``5d8339a13a12`` (fixed to ``'[]'``).

This test emulates the historical condition by upgrading a fresh database
only to the revision *before* the tenant-table migration — exactly what a
real pre-tenant database looks like: stamped ``prev``, with no tenant
tables and no tables created by later migrations. (The earlier emulation —
build head, drop the tenant tables, stamp ``prev`` — left every post-``prev``
table physically present, so their creating migrations collided with
``table already exists`` on the re-upgrade; #3084.) Then ``upgrade head``
and assert the schema converges to the declared models — plus a sentinel
row in an untouched table survives.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from .test_b8_schema_conformance import _COORDINATOR_ROOT, _get_model_columns, _run_alembic


def _pre_tenant_revision() -> str:
    """Resolve the single down_revision of the tenant-table migration.

    The emulated era is "before the multitenant feature", so the stamp target is the
    parent of e7f2a9c4b1d0 — not of the current head, which has gained migrations
    (add_partner_integration_tables, c3a91f7e5b02) that sit on top of it.
    """
    cfg = Config(str(_COORDINATOR_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_COORDINATOR_ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    down = script.get_revision("e7f2a9c4b1d0").down_revision
    if isinstance(down, tuple):
        assert len(down) == 1, f"tenant migration has multiple parents: {down}"
        down = down[0]
    assert isinstance(down, str)
    return down


def test_historical_schema_upgrade_converges(tmp_path: Path):
    # 1. Build the true historical state: a fresh database upgraded only to
    #    the pre-tenant revision.
    prev = _pre_tenant_revision()
    db_path = _run_alembic(tmp_path, "upgrade", prev)

    # Sentinel data in a kept table the upgrade must not disturb. (dao_vote
    # predates the stamp point and keeps a stable, FK-free schema across the
    # post-prev migrations.)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM dao_vote"))
        conn.execute(
            text(
                "INSERT INTO dao_vote "
                "(id, proposal_id, member_id, support, weight, tx_hash, created_at) "
                "VALUES ('vote_b8_sentinel', 'prop_b8', 'member_b8', 1, 1.0, NULL, "
                "'2026-09-08 00:00:00')"
            )
        )
    engine.dispose()

    # 2. Upgrade from the frozen historical state.
    _run_alembic(tmp_path, "upgrade", "head")

    # 3. Converged: every declared table exists with matching columns.
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
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
        rows = conn.execute(text("SELECT proposal_id FROM dao_vote WHERE id = 'vote_b8_sentinel'")).fetchall()
    engine.dispose()
    assert rows == [("prop_b8",)], "sentinel row lost during upgrade"
