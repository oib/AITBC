"""Add chain_id to gpu_registry.

Revision ID: 4d6e9c8a1b52
Revises: b8f3a2c91d04
Create Date: 2026-08-19
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Column, String, inspect

# revision identifiers, used by Alembic.
revision = "4d6e9c8a1b52"
down_revision = "b8f3a2c91d04"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    # Inspector, not `PRAGMA table_info`: the pragma is SQLite-only and this
    # revision has to run on PostgreSQL too. A missing table reads as "no
    # columns", matching the pragma's old behaviour.
    inspector = inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    """Add chain_id column to gpu_registry if it does not already exist."""
    if not _has_column("gpu_registry", "chain_id"):
        op.add_column(
            "gpu_registry",
            Column(
                "chain_id",
                String,
                nullable=True,
                server_default="ait-hub",
                index=True,
            ),
        )


def downgrade() -> None:
    """Remove the chain_id column from gpu_registry if it exists."""
    if _has_column("gpu_registry", "chain_id"):
        # The column's own index must go first: SQLite batch mode rebuilds
        # the table and then re-issues CREATE INDEX for every index it saw,
        # which fails on a column that no longer exists.
        op.drop_index("ix_gpu_registry_chain_id", table_name="gpu_registry", if_exists=True)
        with op.batch_alter_table("gpu_registry") as batch_op:
            batch_op.drop_column("chain_id")
