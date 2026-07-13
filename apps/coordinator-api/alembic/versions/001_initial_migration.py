"""Initial migration — baseline schema created by SQLModel.metadata.create_all

This revision bootstraps the baseline schema by importing all coordinator API
models and calling ``SQLModel.metadata.create_all``. The import is done inside
the function so the module can be parsed without loading the entire application.

Revision ID: initial_migration
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "initial_migration"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Importing main triggers imports of all routers, which in turn import the
    # domain models. After that, SQLModel.metadata contains the full schema.
    import coordinator_api.main  # noqa: F401
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    import coordinator_api.main  # noqa: F401
    from sqlmodel import SQLModel

    SQLModel.metadata.drop_all(op.get_bind())
