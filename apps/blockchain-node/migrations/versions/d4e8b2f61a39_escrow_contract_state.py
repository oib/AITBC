"""Give the escrow row the contract's lifecycle state (#780 step b).

Revision ID: d4e8b2f61a39
Revises: a7c3d9e2f184
Create Date: 2026-11-03 00:00:00.000000

Refs #780 (RPC-ESCROW-PER-WORKER-1, ruling 2026-11-02 card 5A).

Until now the escrow table held only the money facts; the contract's
lifecycle (state, milestones, dispute, resolution) lived in each RPC worker's
EscrowManager, one copy per ``--workers`` process, under a contract_id that
was not even the same across workers. This revision adds the columns that
move that state into chain.db, and backfills every existing row:

* ``contract_id``   deterministic ``escrow_`` + sha256(buyer:provider:job_id)[:16]
                    (``contracts.escrow.contract_id_for``), unique-indexed.
* ``state``         released_at set -> released, refunded_at set -> refunded,
                    otherwise funded.
* ``expires_at``    created_at + 30 days, the ceiling a contract is capped at.
* ``fee_bps``       energy_fee_basis_points for a protected row, else 250.
* ``milestones``    the single "Complete job" milestone, amount in AIT as a
                    string, completed only for a released row.
* ``current_milestone`` 0; ``dispute_*`` / ``resolution`` stay NULL.

The service start (``init_db`` -> ``_migrate_existing_columns``) also adds any
missing nullable column, so every add is existence-guarded and the backfill
fills only what is still NULL: re-running it, or running it on a database a
newer service already touched, changes nothing. The backfill restates the
rules of ``contracts.escrow.escrow_state_columns`` instead of importing them,
so a later change to that helper cannot rewrite what this revision does; a
test holds the two together.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "d4e8b2f61a39"
down_revision: str | None = "a7c3d9e2f184"
branch_labels: str | None = None
depends_on: str | None = None

_CONTRACT_ID_INDEX = "uq_escrow_contract_id"
_DEFAULT_FEE_BPS = 250
_CONTRACT_LIFETIME = timedelta(days=30)
_UNITS_PER_AIT = 36_000_000

_NEW_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("contract_id", sa.String()),
    ("state", sa.String()),
    ("expires_at", sa.DateTime()),
    ("fee_bps", sa.Integer()),
    ("milestones", sa.JSON()),
    ("dispute_reason", sa.String()),
    ("dispute_evidence", sa.JSON()),
    ("resolution", sa.JSON()),
)


def _columns(bind: sa.engine.Connection) -> set[str]:
    if context.is_offline_mode():
        return set()
    inspector = sa.inspect(bind)
    if "escrow" not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns("escrow")}


def _units_to_ait_str(units: int) -> str:
    """Decimal string of ``units`` compute-units in AIT, as ``units_to_ait`` renders it."""
    from aitbc.utils.units import units_to_ait

    return str(units_to_ait(int(units)))


def _backfill(bind: sa.engine.Connection) -> None:
    from aitbc.crypto.signature_recovery import canonical_address

    # Typed lightweight table: the DateTime / JSON types do the sqlite string
    # parsing on the way out and the serialisation on the way in.
    escrow = sa.table(
        "escrow",
        sa.column("job_id", sa.String),
        sa.column("buyer", sa.String),
        sa.column("provider", sa.String),
        sa.column("amount", sa.BigInteger),
        sa.column("created_at", sa.DateTime),
        sa.column("released_at", sa.DateTime),
        sa.column("refunded_at", sa.DateTime),
        sa.column("protected", sa.Boolean),
        sa.column("energy_fee_basis_points", sa.Integer),
        sa.column("contract_id", sa.String),
        sa.column("state", sa.String),
        sa.column("expires_at", sa.DateTime),
        sa.column("fee_bps", sa.Integer),
        sa.column("milestones", sa.JSON),
        sa.column("current_milestone", sa.Integer),
    )
    missing = sa.or_(
        escrow.c.contract_id.is_(None),
        escrow.c.state.is_(None),
        escrow.c.expires_at.is_(None),
        escrow.c.fee_bps.is_(None),
        escrow.c.milestones.is_(None),
    )
    rows = bind.execute(sa.select(escrow).where(missing)).mappings().all()
    for row in rows:
        values: dict[str, object] = {}
        job_id = row["job_id"]
        if row["contract_id"] is None:
            # The runtime reads buyer/provider through the EIP-55 column type, so the
            # id is derived from the canonical spelling, not whatever was stored.
            buyer = canonical_address(row["buyer"])
            provider = canonical_address(row["provider"])
            values["contract_id"] = "escrow_" + sha256(f"{buyer}:{provider}:{job_id}".encode()).hexdigest()[:16]
        if row["state"] is None:
            if row["released_at"] is not None:
                values["state"] = "released"
            elif row["refunded_at"] is not None:
                values["state"] = "refunded"
            else:
                values["state"] = "funded"
        state = values.get("state", row["state"])
        if row["expires_at"] is None:
            created_at = row["created_at"] or datetime.now(UTC).replace(tzinfo=None)
            values["expires_at"] = created_at + _CONTRACT_LIFETIME
        if row["fee_bps"] is None:
            protected = bool(row["protected"])
            fee = row["energy_fee_basis_points"]
            values["fee_bps"] = fee if protected and fee is not None else _DEFAULT_FEE_BPS
        if row["milestones"] is None:
            values["milestones"] = [
                {
                    "milestone_id": "milestone_1",
                    "description": "Complete job",
                    "amount": _units_to_ait_str(row["amount"]),
                    "completed": state == "released",
                }
            ]
        bind.execute(sa.update(escrow).where(escrow.c.job_id == job_id).values(**values))


def upgrade() -> None:
    """Add the contract-state columns, backfill existing rows, index contract_id."""
    bind = op.get_bind()
    existing = _columns(bind)
    if not existing:
        # No escrow table to extend (offline SQL generation, or a database whose
        # tables a later create_all builds with the current schema).
        return
    for name, type_ in _NEW_COLUMNS:
        if name not in existing:
            op.add_column("escrow", sa.Column(name, type_, nullable=True))
    if "current_milestone" not in existing:
        op.add_column("escrow", sa.Column("current_milestone", sa.Integer(), nullable=False, server_default="0"))

    _backfill(bind)

    indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("escrow")}
    if _CONTRACT_ID_INDEX not in indexes:
        op.create_index(_CONTRACT_ID_INDEX, "escrow", ["contract_id"], unique=True)


def downgrade() -> None:
    """Drop the contract-state columns (the lifecycle goes back to worker memory)."""
    bind = op.get_bind()
    existing = _columns(bind)
    if not existing:
        return
    if _CONTRACT_ID_INDEX in {ix["name"] for ix in sa.inspect(bind).get_indexes("escrow")}:
        op.drop_index(_CONTRACT_ID_INDEX, table_name="escrow")
    for name in ("current_milestone", *(name for name, _ in reversed(_NEW_COLUMNS))):
        if name in existing:
            op.drop_column("escrow", name)
