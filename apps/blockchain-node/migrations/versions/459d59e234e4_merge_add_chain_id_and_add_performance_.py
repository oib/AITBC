"""merge add_chain_id and add_performance_indexes heads

Revision ID: 459d59e234e4
Revises: 50fb6691025c, a1b2c3d4e5f6
Create Date: 2026-07-01 22:41:31.276184

"""

from __future__ import annotations

from collections.abc import Sequence


# revision identifiers, used by Alembic.
revision: str = "459d59e234e4"
down_revision: str | Sequence[str] | None = ("50fb6691025c", "a1b2c3d4e5f6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
