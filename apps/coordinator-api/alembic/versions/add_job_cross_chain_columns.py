"""Add cross-chain settlement columns to the job table

These columns support the cross-chain settlement hooks that track settlement
state, payment details, and refund status on jobs. All columns are nullable
since they are only populated when a job requires cross-chain settlement.

Revision ID: add_job_cross_chain_columns
Revises: add_marketplace_job_indexes
Create Date: 2026-07-07 00:00:01.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "add_job_cross_chain_columns"
down_revision = "add_marketplace_job_indexes"
branch_labels = None
depends_on = None


# (column_name, SQLAlchemy type, index?) for each new column.
_COLUMNS: list[tuple[str, sa.types.TypeEngine, bool]] = [
    ("cross_chain_payment_id", sa.String(255), True),
    ("target_chain", sa.Integer(), True),
    ("requires_cross_chain_settlement", sa.Boolean(), False),
    ("payment_chain", sa.Integer(), False),
    ("preferred_bridge", sa.String(50), False),
    ("settlement_priority", sa.String(20), False),
    ("payment_amount", sa.Numeric(36, 18), False),
    ("payment_token", sa.String(42), False),
    ("settlement_gas_limit", sa.BigInteger(), False),
    ("cross_chain_amount", sa.Numeric(36, 18), False),
    ("cross_chain_target_address", sa.String(255), False),
    ("cross_chain_settlement_id", sa.String(255), True),
    ("cross_chain_bridge", sa.String(50), False),
    ("cross_chain_settlement_status", sa.String(20), True),
    ("cross_chain_settlement_error", sa.Text(), False),
    ("cross_chain_refund_id", sa.String(255), False),
    ("cross_chain_refund_status", sa.String(20), False),
    ("completed_at", sa.DateTime(), False),
]


def upgrade() -> None:
    # Guard with inspect() so the migration is idempotent: existing DBs that
    # were built via create_all may already have some of these columns.
    bind = op.get_bind()
    existing_cols = {c["name"] for c in inspect(bind).get_columns("job")}
    existing_indexes = {i["name"] for i in inspect(bind).get_indexes("job")}
    for col_name, col_type, has_index in _COLUMNS:
        if col_name not in existing_cols:
            op.add_column("job", sa.Column(col_name, col_type, nullable=True))
        if has_index:
            idx_name = f"ix_job_{col_name}"
            if idx_name not in existing_indexes:
                op.create_index(idx_name, "job", [col_name])


def downgrade() -> None:
    for col_name, _col_type, has_index in reversed(_COLUMNS):
        if has_index:
            op.drop_index(f"ix_job_{col_name}", table_name="job", if_exists=True)
        op.drop_column("job", col_name)
