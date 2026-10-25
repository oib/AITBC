"""add escrow_release_relay table

Revision ID: c2d3e4f5a6b7
Revises: b1e2f3a4c5d6
Create Date: 2026-10-27 00:00:00.000000+00:00

ESCROW-RELEASE-1: idempotency + audit rows for POST /v1/escrow/release.
One row per relayed release — unlike the create relay there is no
caller-signed payload to hash, so job_id alone is the unique dedup key
(the chain signs the release internally and dedups a second release
itself).

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: str | Sequence[str] | None = "b1e2f3a4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the escrow_release_relay table."""
    op.create_table(
        "escrow_release_relay",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("tx_hash", sa.String(length=128), nullable=True),
        sa.Column("contract_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_escrow_release_relay_client_id"),
        "escrow_release_relay",
        ["client_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_escrow_release_relay_job_id"),
        "escrow_release_relay",
        ["job_id"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the escrow_release_relay table."""
    op.drop_index(op.f("ix_escrow_release_relay_job_id"), table_name="escrow_release_relay", if_exists=True)
    op.drop_index(op.f("ix_escrow_release_relay_client_id"), table_name="escrow_release_relay", if_exists=True)
    op.drop_table("escrow_release_relay", if_exists=True)
