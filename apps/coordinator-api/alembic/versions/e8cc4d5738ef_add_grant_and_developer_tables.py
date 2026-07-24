"""add grant and developer tables

Revision ID: e8cc4d5738ef
Revises: 236edfbd9728
Create Date: 2026-07-24 12:00:00.000000+00:00

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e8cc4d5738ef"
down_revision = "236edfbd9728"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create developer registry and grant proposal tables."""
    op.create_table(
        "developer",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("wallet_address", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("github_handle", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(op.f("ix_developer_wallet_address"), "developer", ["wallet_address"], unique=True, if_not_exists=True)

    op.create_table(
        "grant_proposal",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("developer_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requested_amount", sa.Numeric(28, 18), nullable=False, server_default=sa.text("'0'")),
        sa.Column("approved_amount", sa.Numeric(28, 18), nullable=False, server_default=sa.text("'0'")),
        sa.Column("disbursed_amount", sa.Numeric(28, 18), nullable=False, server_default=sa.text("'0'")),
        sa.Column("status", sa.String(length=32), nullable=False),
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
        sa.ForeignKeyConstraint(["developer_id"], ["developer.id"]),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_grant_proposal_developer_id"), "grant_proposal", ["developer_id"], unique=False, if_not_exists=True
    )
    op.create_index(op.f("ix_grant_proposal_status"), "grant_proposal", ["status"], unique=False, if_not_exists=True)

    op.create_table(
        "grant_milestone",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("grant_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(28, 18), nullable=False, server_default=sa.text("'0'")),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["grant_id"], ["grant_proposal.id"]),
        if_not_exists=True,
    )
    op.create_index(op.f("ix_grant_milestone_grant_id"), "grant_milestone", ["grant_id"], unique=False, if_not_exists=True)
    op.create_index(op.f("ix_grant_milestone_status"), "grant_milestone", ["status"], unique=False, if_not_exists=True)


def downgrade() -> None:
    """Drop grant and developer tables."""
    op.drop_index(op.f("ix_grant_milestone_status"), table_name="grant_milestone", if_exists=True)
    op.drop_index(op.f("ix_grant_milestone_grant_id"), table_name="grant_milestone", if_exists=True)
    op.drop_table("grant_milestone", if_exists=True)
    op.drop_index(op.f("ix_grant_proposal_status"), table_name="grant_proposal", if_exists=True)
    op.drop_index(op.f("ix_grant_proposal_developer_id"), table_name="grant_proposal", if_exists=True)
    op.drop_table("grant_proposal", if_exists=True)
    op.drop_index(op.f("ix_developer_wallet_address"), table_name="developer", if_exists=True)
    op.drop_table("developer", if_exists=True)
