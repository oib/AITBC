"""add provider_bond and slash_appeal tables

Revision ID: 79e94b77d6bd
Revises: f802691c5b0a
Create Date: 2026-07-24 15:42:45.501908+00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "79e94b77d6bd"
down_revision: str | Sequence[str] | None = "f802691c5b0a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create provider_bond and slash_appeal tables."""
    op.create_table(
        "provider_bond",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("provider_id", sa.String(length=255), nullable=False),
        sa.Column("bond_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("required_amount", sa.Float(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_provider_bond_provider_id"),
        "provider_bond",
        ["provider_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_provider_bond_status"),
        "provider_bond",
        ["status"],
        unique=False,
        if_not_exists=True,
    )

    op.create_table(
        "slash_appeal",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("bond_id", sa.String(length=255), nullable=False),
        sa.Column("provider_id", sa.String(length=255), nullable=False),
        sa.Column("slash_event_id", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reviewer_notes", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_slash_appeal_bond_id"),
        "slash_appeal",
        ["bond_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_slash_appeal_provider_id"),
        "slash_appeal",
        ["provider_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_slash_appeal_status"),
        "slash_appeal",
        ["status"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop provider_bond and slash_appeal tables."""
    op.drop_index(
        op.f("ix_slash_appeal_status"),
        table_name="slash_appeal",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_slash_appeal_provider_id"),
        table_name="slash_appeal",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_slash_appeal_bond_id"),
        table_name="slash_appeal",
        if_exists=True,
    )
    op.drop_table("slash_appeal", if_exists=True)
    op.drop_index(
        op.f("ix_provider_bond_status"),
        table_name="provider_bond",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_provider_bond_provider_id"),
        table_name="provider_bond",
        if_exists=True,
    )
    op.drop_table("provider_bond", if_exists=True)
