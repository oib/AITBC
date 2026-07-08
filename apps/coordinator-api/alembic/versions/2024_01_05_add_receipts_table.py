"""Add receipts table — baseline stub

This is a stub representing the receipts table that was created via
``SQLModel.metadata.create_all`` before Alembic was wired up. It exists so the
migration graph is resolvable (referenced as down_revision by
2024_01_10_add_settlements_table). On databases that predate Alembic, this
revision is stamped (never run) — the table already exists.

Revision ID: 2024_01_05_add_receipts_table
Revises:
Create Date: 2024-01-05 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = "2024_01_05_add_receipts_table"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op: baseline schema was created by SQLModel.metadata.create_all.
    pass


def downgrade() -> None:
    # No-op: cannot undo the initial create_all baseline.
    pass
