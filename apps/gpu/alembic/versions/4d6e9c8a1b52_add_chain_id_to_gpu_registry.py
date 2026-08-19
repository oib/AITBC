"""Add chain_id to gpu_registry.

Revision ID: 4d6e9c8a1b52
Revises: b8f3a2c91d04
Create Date: 2026-08-19
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Column, String, text

# revision identifiers, used by Alembic.
revision = "4d6e9c8a1b52"
down_revision = "b8f3a2c91d04"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    return column in (row[1] for row in result)


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
        with op.batch_alter_table("gpu_registry") as batch_op:
            batch_op.drop_column("chain_id")
