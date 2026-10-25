"""add escrow_relay table

Revision ID: b1e2f3a4c5d6
Revises: c3a91f7e5b02
Create Date: 2026-10-26 00:00:00.000000+00:00

ESCROW-ROUTE-1: idempotency + audit rows for POST /v1/escrow/relay. One row
per relayed lock — the dedup key (lock_hash) is unique, and (client_id,
job_id) is indexed for the second dedup lookup.

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1e2f3a4c5d6"
down_revision: str | Sequence[str] | None = "c3a91f7e5b02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the escrow_relay table."""
    op.create_table(
        "escrow_relay",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("lock_hash", sa.String(length=64), nullable=False),
        sa.Column("contract_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lock_hash"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_escrow_relay_client_id"),
        "escrow_relay",
        ["client_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_escrow_relay_job_id"),
        "escrow_relay",
        ["job_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_escrow_relay_lock_hash"),
        "escrow_relay",
        ["lock_hash"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the escrow_relay table."""
    op.drop_index(op.f("ix_escrow_relay_lock_hash"), table_name="escrow_relay", if_exists=True)
    op.drop_index(op.f("ix_escrow_relay_job_id"), table_name="escrow_relay", if_exists=True)
    op.drop_index(op.f("ix_escrow_relay_client_id"), table_name="escrow_relay", if_exists=True)
    op.drop_table("escrow_relay", if_exists=True)
