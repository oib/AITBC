"""Regression tests for the coordinator-api Alembic migration graph.

These tests exercise the migration graph end-to-end on a temporary SQLite
database: online upgrade to head, downgrade to base, and offline SQL
emission. They are intentionally standalone (shelling out to ``alembic``) so
they validate the exact command-line path operations teams use.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from .test_b8_schema_conformance import _semantic_schema

_COORDINATOR_ROOT = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = _COORDINATOR_ROOT.parent.parent


def _run_alembic(
    tmp_path: Path, *args: str, db_name: str = "test_migrations.db", check: bool = True
) -> subprocess.CompletedProcess[str]:
    db_path = tmp_path / db_name
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    # The repo root is needed so `import aitbc` resolves; `coordinator_api.src` is
    # needed for the alembic env itself.
    env["PYTHONPATH"] = f"{_COORDINATOR_ROOT / 'src'}:{REPO_ROOT}"
    # Ensure app settings can boot inside the subprocess without a real audit dir
    env.setdefault("AUDIT_LOG_DIR", str(tmp_path / "audit"))
    env.setdefault("TEST_MODE", "true")

    cmd = [sys.executable, "-m", "alembic", *args]
    result = subprocess.run(
        cmd,
        cwd=_COORDINATOR_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        pytest.fail(
            f"alembic {' '.join(args)} failed (exit {result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def test_alembic_offline_sql(tmp_path: Path) -> None:
    """Offline SQL generation should complete and emit core schema statements."""
    result = _run_alembic(tmp_path, "upgrade", "head", "--sql")
    stdout = result.stdout
    assert "CREATE TABLE" in stdout, "Offline SQL should contain CREATE TABLE statements"
    assert "UPDATE alembic_version" in stdout, "Offline SQL should update alembic_version"
    assert "CREATE INDEX IF NOT EXISTS" in stdout, "Offline SQL should contain idempotent index creation"


def test_alembic_single_head() -> None:
    """The migration graph should have exactly one head."""
    # test fixture using a fixed literal path, not production temp-file handling
    result = _run_alembic(Path("/tmp"), "heads")  # nosec B108
    heads = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(heads) == 1, f"Expected exactly one head, got: {heads}"


def _version_num(db_path: Path) -> str | None:
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    return version


def test_upgrade_head_twice_is_noop(tmp_path: Path) -> None:
    """B-8 follow-on (a/b): a second `upgrade head` on a stamped DB is a no-op."""
    db_path = tmp_path / "test_migrations.db"
    _run_alembic(tmp_path, "upgrade", "head")
    before = _semantic_schema(db_path)
    version = _version_num(db_path)

    second = _run_alembic(tmp_path, "upgrade", "head")

    assert "Running upgrade" not in second.stdout, f"second upgrade ran migrations:\n{second.stdout[-2000:]}"
    assert _semantic_schema(db_path) == before, "schema changed on re-upgrade"
    assert _version_num(db_path) == version


def test_downgrade_latest_then_upgrade_roundtrips(tmp_path: Path) -> None:
    """B-8 follow-on (c): downgrade -1 then upgrade head restores the schema."""
    db_path = tmp_path / "test_migrations.db"
    _run_alembic(tmp_path, "upgrade", "head")
    before = _semantic_schema(db_path)
    head_version = _version_num(db_path)

    _run_alembic(tmp_path, "downgrade", "-1")
    assert _version_num(db_path) != head_version

    _run_alembic(tmp_path, "upgrade", "head")

    assert _version_num(db_path) == head_version
    after = _semantic_schema(db_path)
    assert after == before, "schema differs after downgrade+upgrade round-trip"


def test_energy_floor_downgrade_drops_indexed_columns(tmp_path: Path) -> None:
    """Regression (B3 sweep): f53990f9d6cc drops columns that baseline-owned
    indexes reference (``ix_*_model_id``/``ix_*_resource_id``). SQLite refuses
    ``DROP COLUMN`` while an index still uses the column, so the downgrade must
    drop those indexes first."""
    db_path = tmp_path / "test_migrations.db"
    heads = _run_alembic(tmp_path, "heads").stdout.split()
    _run_alembic(tmp_path, "upgrade", "f53990f9d6cc")
    _run_alembic(tmp_path, "downgrade", "-1")  # used to raise OperationalError
    _run_alembic(tmp_path, "upgrade", "head")
    assert _version_num(db_path) == heads[0]


# Revisions whose downgrade() deliberately refuses -- a frozen baseline (B-8)
# and a cleanup that would re-create incorrect FKs. Not defects.
_KNOWN_UNDOWNGRADABLE = frozenset({"initial_migration", "d38eb9f3a80b"})

# add_developer_platform: its downgrade() drops treasury_allocation and its
# upgrade() recreates it from older DDL that lacks proposal_id, so
# reconcile_schema's unguarded CREATE INDEX fails on the way back to head.
# Fixing requires editing upgrade() bodies -- out of scope for a
# downgrade-side sweep; recorded here so nothing *new* hides behind it.
_KNOWN_REUPGRADE_BROKEN = frozenset({"add_developer_platform"})

# Revisions whose drop-then-recreate round-trip is stable but not identical:
# the revision's own DDL predates the frozen 001 baseline (it was written
# for databases 001 could not yet produce), so restored columns/indexes differ
# in type spelling, nullability, or name while enforcing the same schema
# semantics. The mapping pins the differing tables so new drift fails loudly.
_KNOWN_DRIFT: dict[str, frozenset[str]] = {
    # 001-owned indexes on the dropped columns cannot be restored by any
    # upgrade; the columns themselves return identical.
    "f53990f9d6cc": frozenset({"gpu_bookings", "gpu_registry", "job"}),
    "1a7d8e9b0c2f": frozenset({"transaction_audit_record"}),
    "8a9c1d2e3f4b": frozenset({"tee_attestation"}),
    "79e94b77d6bd": frozenset({"provider_bond", "slash_appeal"}),
    "e8cc4d5738ef": frozenset({"grant_milestone", "grant_proposal"}),
    "add_job_cross_chain_columns": frozenset({"job"}),
    "7350cc615a22": frozenset({"analytics_market_metrics"}),
    "add_global_marketplace": frozenset(
        {
            "global_marketplace_analytics",
            "global_marketplace_configs",
            "global_marketplace_governance",
            "global_marketplace_offers",
            "global_marketplace_transactions",
            "marketplace_regions",
        }
    ),
    "add_cross_chain_reputation": frozenset(
        {"cross_chain_reputation_aggregations", "cross_chain_reputation_events", "reputation_metrics"}
    ),
    "add_dynamic_pricing_tables": frozenset(
        {"market_metrics", "price_forecasts", "pricing_audit_log", "pricing_history", "provider_pricing_strategies"}
    ),
}


def _revision_chain() -> list[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_COORDINATOR_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_COORDINATOR_ROOT / "alembic"))
    return [s.revision for s in ScriptDirectory.from_config(cfg).walk_revisions()]


# The sweep spawns one alembic subprocess per migration revision and measured
# 525s on node2 (2026-10-14), so the 60s ini timeout could only ever kill it —
# every observed failure was that boundary, not intermittency. 1800s is ~3x
# the measurement; a miss under it is a real hang, so no flaky mark.
@pytest.mark.timeout(1800)
@pytest.mark.slow
def test_full_downgrade_roundtrip_sweep(tmp_path: Path) -> None:
    """B3: every revision downgraded one step on a correctly built schema,
    then upgraded back to head and compared semantically with the head schema.

    Asserts the *tolerance lists above exactly*: any revision that newly
    fails to downgrade, newly fails to re-upgrade, or newly drifts makes this
    test fail. Runs ~9 minutes measured on node2 (fresh database per
    revision) -- hence slow and the explicit timeout.
    """
    head_db = tmp_path / "sweep_head.db"
    _run_alembic(tmp_path, "upgrade", "head", db_name="sweep_head.db")
    head_schema = _semantic_schema(head_db)
    head_version = _version_num(head_db)

    chain = _revision_chain()
    assert len(chain) > 30, f"suspiciously short chain: {chain}"
    unexpected: list[str] = []
    for i, rev in enumerate(chain):
        name = f"sweep_{i}.db"
        _run_alembic(tmp_path, "upgrade", rev, db_name=name)
        down = _run_alembic(tmp_path, "downgrade", "-1", db_name=name, check=False)
        if down.returncode != 0:
            if rev not in _KNOWN_UNDOWNGRADABLE:
                tail = down.stderr.strip().splitlines()[-1] if down.stderr.strip() else "?"
                unexpected.append(f"{rev}: downgrade failed: {tail[:120]}")
            continue
        up = _run_alembic(tmp_path, "upgrade", "head", db_name=name, check=False)
        if up.returncode != 0:
            if rev not in _KNOWN_REUPGRADE_BROKEN:
                tail = up.stderr.strip().splitlines()[-1] if up.stderr.strip() else "?"
                unexpected.append(f"{rev}: re-upgrade failed: {tail[:120]}")
            continue
        assert _version_num(tmp_path / name) == head_version, f"{rev}: version drift after re-upgrade"
        after = _semantic_schema(tmp_path / name)
        if after != head_schema:
            if rev not in _KNOWN_DRIFT:
                tabs = sorted(t for t in set(after) | set(head_schema) if after.get(t) != head_schema.get(t))
                unexpected.append(f"{rev}: unexpected drift on {tabs}")
            else:
                tabs = frozenset(t for t in set(after) | set(head_schema) if after.get(t) != head_schema.get(t))
                if tabs != _KNOWN_DRIFT[rev]:
                    unexpected.append(f"{rev}: drift tables changed: expected {_KNOWN_DRIFT[rev]}, got {tabs}")
    assert not unexpected, "sweep regressions:\n" + "\n".join(unexpected)
