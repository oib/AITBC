"""Add offer_id and provider_address to the job table.

G1 binds the price and payee to the marketplace offer a job is bought against.
D3 adds the same binding to dispatch: a job quoted against one provider's offer
must not be matched against another miner just because that miner happens to fit
the customer's capability constraints.

The new columns are nullable so existing jobs continue to dispatch exactly as
before.

Revision ID: 4e8b7c2d1f0a
Revises: d38eb9f3a80b
Create Date: 2026-08-24 00:00:00.000000
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "4e8b7c2d1f0a"
down_revision: str | None = "d38eb9f3a80b"
branch_labels: str | None = None
depends_on: str | None = None

_COLUMNS: list[tuple[str, sa.types.TypeEngine, bool]] = [
    ("offer_id", sa.String(255), True),
    ("provider_address", sa.String(255), True),
]


def upgrade() -> None:
    if context.is_offline_mode():
        existing_cols: set[str] = set()
        existing_indexes: set[str] = set()
    else:
        bind = op.get_bind()
        existing_cols = {str(c["name"]) for c in inspect(bind).get_columns("job") if c.get("name")}
        existing_indexes = {str(i["name"]) for i in inspect(bind).get_indexes("job") if i.get("name")}
    for col_name, col_type, has_index in _COLUMNS:
        if col_name not in existing_cols:
            op.add_column("job", sa.Column(col_name, col_type, nullable=True))
        if has_index:
            idx_name = f"ix_job_{col_name}"
            if idx_name not in existing_indexes:
                op.create_index(idx_name, "job", [col_name], if_not_exists=True)


def downgrade() -> None:
    for col_name, _col_type, has_index in reversed(_COLUMNS):
        if has_index:
            op.drop_index(f"ix_job_{col_name}", table_name="job", if_exists=True)
        op.drop_column("job", col_name)
