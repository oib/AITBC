"""add economic parameter proposal table

Revision ID: bf44ceb6e4ee
Revises: e8cc4d5738ef
Create Date: 2026-07-24 13:01:46.442106+00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bf44ceb6e4ee"
down_revision: str | Sequence[str] | None = "e8cc4d5738ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the economic_parameter_proposal table."""
    op.create_table(
        "economic_parameter_proposal",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("proposer_id", sa.String(length=255), nullable=False),
        sa.Column("parameter_name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("current_value", sa.Numeric(28, 18), nullable=False, server_default=sa.text("'0'")),
        sa.Column("proposed_value", sa.Numeric(28, 18), nullable=False, server_default=sa.text("'0'")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("votes_for", sa.Float(), nullable=False, server_default=sa.text("'0.0'")),
        sa.Column("votes_against", sa.Float(), nullable=False, server_default=sa.text("'0.0'")),
        sa.Column("votes_abstain", sa.Float(), nullable=False, server_default=sa.text("'0.0'")),
        sa.Column("quorum", sa.Float(), nullable=False, server_default=sa.text("'0.0'")),
        sa.Column("passing_threshold", sa.Float(), nullable=False, server_default=sa.text("'0.5'")),
        sa.Column("voting_starts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voting_ends", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proposal_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_economic_parameter_proposal_parameter_name"),
        "economic_parameter_proposal",
        ["parameter_name"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_economic_parameter_proposal_proposer_id"),
        "economic_parameter_proposal",
        ["proposer_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_economic_parameter_proposal_status"),
        "economic_parameter_proposal",
        ["status"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the economic_parameter_proposal table."""
    op.drop_index(
        op.f("ix_economic_parameter_proposal_status"),
        table_name="economic_parameter_proposal",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_economic_parameter_proposal_proposer_id"),
        table_name="economic_parameter_proposal",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_economic_parameter_proposal_parameter_name"),
        table_name="economic_parameter_proposal",
        if_exists=True,
    )
    op.drop_table("economic_parameter_proposal", if_exists=True)
