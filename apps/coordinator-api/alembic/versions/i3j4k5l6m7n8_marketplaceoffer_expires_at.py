"""add expires_at to marketplaceoffer (#1554)

The shared ``aitbc_shared.models.market.MarketOffer`` gained an optional
``expires_at`` column: NULL means the listing never expires (backward
compatible). The market service's sweeper flips past-due AVAILABLE offers
to 'expired'; the column is additive and nullable so existing rows are
unaffected.

Fresh databases already have the column — 001_initial_migration builds the
schema from SQLModel.metadata.create_all, which now includes it — so the
ADD COLUMN is guarded by an inspector check like the other late additions.

Revision ID: i3j4k5l6m7n8
Revises: h2c3d4e5f6a7
Create Date: 2026-11-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "i3j4k5l6m7n8"
down_revision: str | Sequence[str] | None = "h2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in inspect(bind).get_columns("marketplaceoffer")}
    if "expires_at" not in existing:
        op.add_column(
            "marketplaceoffer",
            sa.Column("expires_at", sa.DateTime(), nullable=True),
        )
    existing_indexes = {i["name"] for i in inspect(bind).get_indexes("marketplaceoffer")}
    if "ix_marketplaceoffer_expires_at" not in existing_indexes:
        op.create_index(
            "ix_marketplaceoffer_expires_at",
            "marketplaceoffer",
            ["expires_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing_indexes = {i["name"] for i in inspect(bind).get_indexes("marketplaceoffer")}
    if "ix_marketplaceoffer_expires_at" in existing_indexes:
        op.drop_index("ix_marketplaceoffer_expires_at", table_name="marketplaceoffer")
    existing = {c["name"] for c in inspect(bind).get_columns("marketplaceoffer")}
    if "expires_at" in existing:
        op.drop_column("marketplaceoffer", "expires_at")
