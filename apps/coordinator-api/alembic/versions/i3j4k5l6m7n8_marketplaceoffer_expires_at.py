"""add expires_at to marketplaceoffer (#1554)

The shared ``aitbc_shared.models.market.MarketOffer`` gained an optional
``expires_at`` column: NULL means the listing never expires (backward
compatible). The market service's sweeper flips past-due AVAILABLE offers
to 'expired'; the column is additive and nullable so existing rows are
unaffected.

Fresh databases already have the column — 001_initial_migration builds the
schema from SQLModel.metadata.create_all, which now includes it — so the
ADD COLUMN is guarded by an inspector check like the other late additions.
In offline SQL mode there is no bind to inspect (``inspect()`` raises
``NoInspectionAvailable`` on the MockConnection), so the historical state is
assumed and the DDL is emitted unconditionally — same pattern as
``h2c3d4e5f6a7`` and ``1c58c844d95e``.

Revision ID: i3j4k5l6m7n8
Revises: h2c3d4e5f6a7
Create Date: 2026-11-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "i3j4k5l6m7n8"
down_revision: str | Sequence[str] | None = "h2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns_and_indexes() -> tuple[set[str], set[str]]:
    """Return (column names, index names) for marketplaceoffer.

    In offline SQL generation mode there is no live bind, so the table is
    assumed to be in the pre-migration historical state: no columns or
    indexes reported, which makes upgrade() emit both ADD statements and
    downgrade() emit both DROP statements.
    """
    if context.is_offline_mode():
        return set(), set()
    bind = op.get_bind()
    inspector = inspect(bind)
    if "marketplaceoffer" not in inspector.get_table_names():
        return set(), set()
    columns = {c["name"] for c in inspector.get_columns("marketplaceoffer")}
    indexes = {i["name"] for i in inspector.get_indexes("marketplaceoffer")}
    return columns, indexes


def upgrade() -> None:
    existing, existing_indexes = _columns_and_indexes()
    if "expires_at" not in existing:
        op.add_column(
            "marketplaceoffer",
            sa.Column("expires_at", sa.DateTime(), nullable=True),
        )
    if "ix_marketplaceoffer_expires_at" not in existing_indexes:
        op.create_index(
            "ix_marketplaceoffer_expires_at",
            "marketplaceoffer",
            ["expires_at"],
            unique=False,
        )


def downgrade() -> None:
    existing, existing_indexes = _columns_and_indexes()
    if "ix_marketplaceoffer_expires_at" in existing_indexes or context.is_offline_mode():
        op.drop_index("ix_marketplaceoffer_expires_at", table_name="marketplaceoffer")
    if "expires_at" in existing or context.is_offline_mode():
        op.drop_column("marketplaceoffer", "expires_at")
