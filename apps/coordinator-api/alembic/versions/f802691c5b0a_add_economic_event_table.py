"""add economic event table

Revision ID: f802691c5b0a
Revises: bf44ceb6e4ee
Create Date: 2026-07-24 14:09:10.638893+00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f802691c5b0a"
down_revision: str | Sequence[str] | None = "bf44ceb6e4ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the economic_event table."""
    op.create_table(
        "economic_event",
        sa.Column("event_id", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(28, 18), nullable=False, server_default=sa.text("'0'")),
        sa.Column("chain_id", sa.String(length=64), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_economic_event_actor_id"),
        "economic_event",
        ["actor_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_economic_event_event_type"),
        "economic_event",
        ["event_type"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the economic_event table."""
    op.drop_index(
        op.f("ix_economic_event_event_type"),
        table_name="economic_event",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_economic_event_actor_id"),
        table_name="economic_event",
        if_exists=True,
    )
    op.drop_table("economic_event", if_exists=True)
