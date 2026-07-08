"""Initial migration — baseline schema created by SQLModel.metadata.create_all

This is a stub representing the initial schema that was created via
``SQLModel.metadata.create_all`` before Alembic was wired up. It exists so the
migration graph is resolvable. On databases that predate Alembic, this revision
is stamped (never run) — the tables already exist.

Revision ID: initial_migration
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = "initial_migration"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op: baseline schema was created by SQLModel.metadata.create_all.
    pass


def downgrade() -> None:
    # No-op: cannot undo the initial create_all baseline.
    pass
