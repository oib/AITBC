"""drop dead economic_event table (#2176)

``economic_event`` was created by 001_initial_migration and
f802691c5b0a_add_economic_event_table for the analytics
``EconomicEvent``/``EventStore`` model, but nothing in
apps/*/src selected, inserted or updated it — the model module and its
test were removed in the same change, so the table is dead schema.

``DROP TABLE IF EXISTS`` keeps it a no-op on databases that never
created it. Downgrade is a no-op: the table carried no live data.

Revision ID: b3c4d5e6f7a8
Revises: d4e5f6a7b8c9
Create Date: 2026-11-19

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "b3c4d5e6f7a8"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CASCADE on Postgres so dependent FK constraints (if any) drop with it;
    # SQLite has no CASCADE clause — emit plain DROP.
    cascade = " CASCADE" if op.get_bind().dialect.name == "postgresql" else ""
    op.execute(f'DROP TABLE IF EXISTS "economic_event"{cascade}')


def downgrade() -> None:
    # Dead table carried no live data; nothing to restore.
    pass
