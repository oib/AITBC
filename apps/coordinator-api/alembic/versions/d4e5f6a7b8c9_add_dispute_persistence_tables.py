"""add dispute persistence tables

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f7
Create Date: 2026-11-16 00:00:00.000000+00:00

#2161: ``DisputeResolutionService`` kept all dispute state in memory, so
every coordinator-api restart destroyed open disputes (evidence,
arbitrator votes, refund/payout amounts). These tables back the service's
write-through cache: one ``dispute_cases`` row per dispute plus child
``dispute_evidence`` / ``dispute_votes`` rows and a ``dispute_arbitrators``
registry. Amounts are BigInteger — dispute/stake amounts are integer
compute units that can exceed int4 on Postgres.

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the dispute persistence tables."""
    op.create_table(
        "dispute_cases",
        sa.Column("dispute_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("client", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("filed_by", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("evidence_deadline", sa.DateTime(), nullable=True),
        sa.Column("voting_deadline", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("refund_amount", sa.BigInteger(), nullable=False),
        sa.Column("payout_amount", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("dispute_id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_dispute_cases_job_id"),
        "dispute_cases",
        ["job_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_dispute_cases_status"),
        "dispute_cases",
        ["status"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "dispute_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dispute_id", sa.String(length=64), nullable=False),
        sa.Column("submitted_by", sa.String(length=128), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("ipfs_hash", sa.String(length=128), nullable=True),
        sa.Column("tx_hash", sa.String(length=128), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["dispute_id"], ["dispute_cases.dispute_id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_dispute_evidence_dispute_id"),
        "dispute_evidence",
        ["dispute_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "dispute_votes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dispute_id", sa.String(length=64), nullable=False),
        sa.Column("arbitrator", sa.String(length=128), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reasoning", sa.String(), nullable=False),
        sa.Column("stake_amount", sa.BigInteger(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["dispute_id"], ["dispute_cases.dispute_id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_dispute_votes_dispute_id"),
        "dispute_votes",
        ["dispute_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "dispute_arbitrators",
        sa.Column("address", sa.String(length=128), nullable=False),
        sa.Column("registered_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("address"),
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the dispute persistence tables."""
    op.drop_table("dispute_arbitrators", if_exists=True)
    op.drop_index(op.f("ix_dispute_votes_dispute_id"), table_name="dispute_votes", if_exists=True)
    op.drop_table("dispute_votes", if_exists=True)
    op.drop_index(op.f("ix_dispute_evidence_dispute_id"), table_name="dispute_evidence", if_exists=True)
    op.drop_table("dispute_evidence", if_exists=True)
    op.drop_index(op.f("ix_dispute_cases_status"), table_name="dispute_cases", if_exists=True)
    op.drop_index(op.f("ix_dispute_cases_job_id"), table_name="dispute_cases", if_exists=True)
    op.drop_table("dispute_cases", if_exists=True)
