"""add ipfs_memory_owner table

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-11-23 08:30:00.000000+00:00

Durable cid -> agent_id mapping for IPFS memories (#2711): the service's
process-local registries lose ownership on restart/eviction and the #1882
bind then 403s the legitimate owner.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ipfs_memory_owner table."""
    op.create_table(
        "ipfs_memory_owner",
        sa.Column("cid", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("cid"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_ipfs_memory_owner_agent_id"),
        "ipfs_memory_owner",
        ["agent_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the ipfs_memory_owner table."""
    op.drop_index(
        op.f("ix_ipfs_memory_owner_agent_id"),
        table_name="ipfs_memory_owner",
        if_exists=True,
    )
    op.drop_table("ipfs_memory_owner", if_exists=True)
