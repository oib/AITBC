"""The escrow row carries the contract's lifecycle state (#780 step b).

Until the row held it, each RPC worker kept its own copy of the contract. These tests
pin the columns the migration adds, the helper that builds them for a row rebuilt from
chain facts, the writers that fill them, and that the migration backfill and the helper
state the same rules.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine

from aitbc_chain.base_models import Escrow, Transaction
from aitbc_chain.contracts.escrow import (
    DEFAULT_FEE_BPS,
    EscrowManager,
    contract_id_for,
    default_milestones,
    deserialise_milestones,
    escrow_state_columns,
    row_state_for,
    serialise_milestones,
)
from aitbc_chain.metadata import chain_metadata

_APP_ROOT = Path(__file__).resolve().parent.parent

CHAIN = "test-chain"
BUYER = "0xe8b0db006F34bf5b5d2B22553C017431E8e86e4F"
PROVIDER = "0xD4d85501E6cD447972Db19370307F1E3B1510016"
T0 = datetime(2026, 9, 2, 21, 16, 5)
LOCKED = 3_600_000  # 0.1 AIT

PREVIOUS_HEAD = "a7c3d9e2f184"


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    chain_metadata.create_all(engine)
    with Session(engine) as open_session:
        yield open_session


def test_state_follows_the_settlement_timestamps():
    assert row_state_for(None, None) == "funded"
    assert row_state_for(T0, None) == "released"
    assert row_state_for(None, T0) == "refunded"


def test_columns_for_a_funded_row():
    cols = escrow_state_columns(buyer=BUYER, provider=PROVIDER, job_id="job-1", amount_units=LOCKED, created_at=T0)
    assert cols["contract_id"] == contract_id_for(BUYER, PROVIDER, "job-1")
    assert cols["state"] == "funded"
    assert cols["expires_at"] == T0 + timedelta(days=30)
    assert cols["fee_bps"] == DEFAULT_FEE_BPS
    assert cols["current_milestone"] == 0
    assert cols["milestones"] == [
        {"milestone_id": "milestone_1", "description": "Complete job", "amount": "0.1", "completed": False}
    ]


def test_a_released_row_has_its_milestone_completed():
    cols = escrow_state_columns(
        buyer=BUYER, provider=PROVIDER, job_id="job-1", amount_units=LOCKED, created_at=T0, released_at=T0
    )
    assert cols["state"] == "released"
    assert cols["milestones"][0]["completed"] is True


def test_protected_row_uses_its_quoted_fee_and_unprotected_ignores_it():
    protected = escrow_state_columns(
        buyer=BUYER,
        provider=PROVIDER,
        job_id="job-1",
        amount_units=LOCKED,
        created_at=T0,
        protected=True,
        energy_fee_basis_points=300,
    )
    unprotected = escrow_state_columns(
        buyer=BUYER,
        provider=PROVIDER,
        job_id="job-1",
        amount_units=LOCKED,
        created_at=T0,
        protected=False,
        energy_fee_basis_points=300,
    )
    assert protected["fee_bps"] == 300
    assert unprotected["fee_bps"] == DEFAULT_FEE_BPS


def test_milestones_survive_json_and_come_back_as_decimal():
    milestones = default_milestones(Decimal("1.5"))
    stored = serialise_milestones(milestones)
    assert json.loads(json.dumps(stored))[0]["amount"] == "1.5"
    assert deserialise_milestones(stored)[0]["amount"] == Decimal("1.5")
    # The live objects are left alone: the contract keeps Decimal amounts.
    assert milestones[0]["amount"] == Decimal("1.5")


def test_the_new_columns_round_trip_through_the_table(session):
    cols = escrow_state_columns(buyer=BUYER, provider=PROVIDER, job_id="job-1", amount_units=LOCKED, created_at=T0)
    session.add(Escrow(job_id="job-1", chain_id=CHAIN, buyer=BUYER, provider=PROVIDER, amount=LOCKED, **cols))
    session.commit()
    session.expire_all()
    row = session.get(Escrow, "job-1")
    assert row is not None
    assert row.contract_id == cols["contract_id"]
    assert row.state == "funded"
    assert row.milestones == cols["milestones"]
    assert row.fee_bps == DEFAULT_FEE_BPS
    assert row.current_milestone == 0
    assert row.dispute_reason is None and row.dispute_evidence is None and row.resolution is None


def test_a_row_without_the_columns_still_loads_with_defaults(session):
    session.add(Escrow(job_id="legacy", chain_id=CHAIN, buyer=BUYER, provider=PROVIDER, amount=LOCKED))
    session.commit()
    row = session.get(Escrow, "legacy")
    assert row is not None
    assert row.contract_id is None and row.state is None and row.milestones is None
    assert row.current_milestone == 0


def test_contract_id_is_unique_but_null_is_not(session):
    session.add(Escrow(job_id="a", chain_id=CHAIN, buyer=BUYER, provider=PROVIDER, amount=1))
    session.add(Escrow(job_id="b", chain_id=CHAIN, buyer=BUYER, provider=PROVIDER, amount=1))
    session.commit()  # two NULL contract_ids coexist
    session.add(Escrow(job_id="c", chain_id=CHAIN, buyer=BUYER, provider=PROVIDER, amount=1, contract_id="escrow_x"))
    session.commit()
    session.add(Escrow(job_id="d", chain_id=CHAIN, buyer=BUYER, provider=PROVIDER, amount=1, contract_id="escrow_x"))
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.asyncio
async def test_a_row_rebuilt_from_the_chain_carries_the_columns(session):
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash="0xlock",
            sender=BUYER,
            recipient=PROVIDER,
            type="ESCROW_LOCK",
            value=LOCKED,
            created_at=T0,
            payload={"action": "escrow_lock", "job_id": "job-rebuilt", "buyer": BUYER, "provider": PROVIDER},
        )
    )
    session.commit()
    record = await EscrowManager()._reconstruct_escrow_from_chain(session, "job-rebuilt")
    assert record is not None
    assert record.contract_id == contract_id_for(BUYER, PROVIDER, "job-rebuilt")
    assert record.state == "funded"
    assert record.fee_bps == DEFAULT_FEE_BPS
    assert record.milestones[0]["amount"] == "0.1"


# --- the migration backfill ---------------------------------------------------------------


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(_APP_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


@pytest.fixture
def migrated_to_previous_head(tmp_path, monkeypatch):
    """A chain.db at the revision before the columns existed, plus the config to move it on."""
    db_path = tmp_path / "chain.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("CHAIN_ID", "ait-testchain.local")
    monkeypatch.chdir(_APP_ROOT)
    cfg = _alembic_config(db_path)
    command.upgrade(cfg, PREVIOUS_HEAD)
    return db_path, cfg


def _read_state_columns(db_path: Path, job_id: str) -> dict:
    """The new columns of one row, read raw: alembic alone does not build every ORM column
    (the rest arrive with the service-start column sync), so the ORM cannot load this table."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT contract_id, state, expires_at, fee_bps, milestones, current_milestone, "
            "dispute_reason, dispute_evidence, resolution FROM escrow WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    assert row is not None, job_id
    out = dict(row)
    out["expires_at"] = datetime.fromisoformat(out["expires_at"]) if out["expires_at"] else None
    out["milestones"] = json.loads(out["milestones"]) if out["milestones"] else None
    return out


def _insert_old_row(conn: sqlite3.Connection, job_id: str, buyer: str, **fields) -> None:
    row = {
        "job_id": job_id,
        "chain_id": CHAIN,
        "buyer": buyer,
        "provider": PROVIDER,
        "amount": LOCKED,
        "status": "locked",
        "created_at": "2026-09-02 21:16:05.000000",
        "protected": 0,
    }
    row.update(fields)
    conn.execute(
        f"INSERT INTO escrow ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",  # nosec B608 - test fixture, fixed keys
        list(row.values()),
    )


def test_migration_backfills_existing_rows_with_the_helpers_rules(migrated_to_previous_head):
    db_path, cfg = migrated_to_previous_head
    with sqlite3.connect(db_path) as conn:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(escrow)")}
        assert "contract_id" not in columns  # really the old shape
        _insert_old_row(conn, "job-funded", BUYER)
        # Stored in the spelling a pre-canonical writer used; the id must still be the
        # one the runtime derives from the EIP-55 form the column type hands back.
        _insert_old_row(conn, "job-lower", BUYER.lower())
        _insert_old_row(conn, "job-released", BUYER, status="released", released_at="2026-09-02 21:20:00.000000")
        _insert_old_row(conn, "job-refunded", BUYER, status="refunded", refunded_at="2026-09-02 21:20:00.000000")
        _insert_old_row(conn, "job-protected", BUYER, protected=1, energy_fee_basis_points=300)

    command.upgrade(cfg, "head")

    for job_id, released_at, refunded_at, protected, bps in (
        ("job-funded", None, None, False, None),
        ("job-lower", None, None, False, None),
        ("job-released", T0 + timedelta(minutes=4), None, False, None),
        ("job-refunded", None, T0 + timedelta(minutes=4), False, None),
        ("job-protected", None, None, True, 300),
    ):
        row = _read_state_columns(db_path, job_id)
        expected = escrow_state_columns(
            buyer=BUYER,
            provider=PROVIDER,
            job_id=job_id,
            amount_units=LOCKED,
            created_at=T0,
            protected=protected,
            energy_fee_basis_points=bps,
            released_at=released_at,
            refunded_at=refunded_at,
        )
        for column, value in expected.items():
            assert row[column] == value, f"{job_id}.{column}"
        assert row["dispute_reason"] is None and row["resolution"] is None

    with sqlite3.connect(db_path) as conn:
        indexes = {r[1]: r[2] for r in conn.execute("PRAGMA index_list(escrow)")}
        assert indexes.get("uq_escrow_contract_id") == 1  # unique


def test_the_backfill_fills_only_what_is_null(migrated_to_previous_head):
    db_path, cfg = migrated_to_previous_head
    # A service start added the columns and a new row wrote real values before alembic ran.
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE escrow ADD COLUMN contract_id VARCHAR")
        conn.exec_driver_sql("ALTER TABLE escrow ADD COLUMN state VARCHAR")
    with sqlite3.connect(db_path) as conn:
        _insert_old_row(conn, "job-live", BUYER, contract_id="escrow_kept", state="job_started")

    command.upgrade(cfg, "head")

    row = _read_state_columns(db_path, "job-live")
    assert row["contract_id"] == "escrow_kept"
    assert row["state"] == "job_started"
    assert row["milestones"] is not None and row["fee_bps"] == DEFAULT_FEE_BPS  # the rest was filled


def test_the_migration_downgrades_and_upgrades_again(migrated_to_previous_head):
    db_path, cfg = migrated_to_previous_head
    with sqlite3.connect(db_path) as conn:
        _insert_old_row(conn, "job-1", BUYER)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, PREVIOUS_HEAD)
    with sqlite3.connect(db_path) as conn:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(escrow)")}
        assert not columns & {"contract_id", "state", "milestones", "current_milestone"}
        assert conn.execute("SELECT COUNT(*) FROM escrow").fetchone()[0] == 1
    command.upgrade(cfg, "head")
    assert _read_state_columns(db_path, "job-1")["contract_id"] == contract_id_for(BUYER, PROVIDER, "job-1")


def test_the_revision_follows_the_previous_head_and_is_on_the_path_to_head():
    from alembic.script import ScriptDirectory

    scripts = ScriptDirectory.from_config(Config(str(_APP_ROOT / "alembic.ini")))
    assert scripts.get_revision("d4e8b2f61a39").down_revision == PREVIOUS_HEAD
    ancestors = {rev.revision for rev in scripts.iterate_revisions("heads", "base")}
    assert "d4e8b2f61a39" in ancestors
