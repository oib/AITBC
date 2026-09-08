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


def _load_model_metadata() -> None:
    """Import the coordinator API entry point and any model modules not pulled in by it.

    SQLModel.metadata is global; models are only registered when their module is
    imported. `coordinator_api.main` imports the routers, but some model modules
    (e.g. `models.multitenant`) are only reached through service-side code, so
    importing them explicitly here keeps the migration graph in sync with the
    full declared schema.
    """
    import coordinator_api.main  # noqa: F401
    import coordinator_api.models.multitenant  # noqa: F401


def upgrade() -> None:
    _load_model_metadata()
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    _load_model_metadata()
    from sqlmodel import SQLModel

    SQLModel.metadata.drop_all(op.get_bind())
