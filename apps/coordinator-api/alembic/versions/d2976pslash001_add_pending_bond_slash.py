"""add pending_bond_slash table

Revision ID: d2976pslash001
Revises: d5e6f7a8b9c0
Create Date: 2026-11-27 00:00:00.000000+00:00

#2976 (SLASH-AUTO-APPEAL-WINDOW-1): durable queue for automatic bond slashes
inside their pre-burn appeal window. Detection writes a row + freezes bond
eligibility via the suspension meta flag; the sweeper submits BOND_SLASH only
after ``window_ends_at``. All timestamps are naive UTC (DATETIME carries no
timezone).
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2976pslash001"
down_revision: str | Sequence[str] | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the pending_bond_slash table."""
    op.create_table(
        "pending_bond_slash",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("bond_id", sa.String(length=255), nullable=False),
        sa.Column("bond_pk", sa.String(length=40), nullable=False),
        sa.Column("provider_id", sa.String(length=255), nullable=False),
        sa.Column("condition", sa.String(length=32), nullable=False),
        sa.Column("slash_rate", sa.String(length=32), nullable=False),
        sa.Column("slash_amount_units", sa.Integer(), nullable=False),
        sa.Column("pre_slash_amount_units", sa.Integer(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("suspension_event_id", sa.String(length=64), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("window_ends_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("appeal_id", sa.String(length=40), nullable=False),
        sa.Column("submitted_tx_hash", sa.String(length=128), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_pending_bond_slash_job_id"),
        "pending_bond_slash",
        ["job_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_pending_bond_slash_provider_id"),
        "pending_bond_slash",
        ["provider_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_pending_bond_slash_status_window",
        "pending_bond_slash",
        ["status", "window_ends_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_pending_bond_slash_bond",
        "pending_bond_slash",
        ["bond_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the pending_bond_slash table."""
    op.drop_index("ix_pending_bond_slash_bond", table_name="pending_bond_slash", if_exists=True)
    op.drop_index(
        "ix_pending_bond_slash_status_window",
        table_name="pending_bond_slash",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_pending_bond_slash_provider_id"),
        table_name="pending_bond_slash",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_pending_bond_slash_job_id"),
        table_name="pending_bond_slash",
        if_exists=True,
    )
    op.drop_table("pending_bond_slash", if_exists=True)
