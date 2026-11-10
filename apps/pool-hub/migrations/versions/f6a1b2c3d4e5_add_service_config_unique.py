"""Add UniqueConstraint(miner_id, service_type) to service_configs (#1397).

ServiceConfig's ``__table_args__`` was a no-op, so the create route's
select-then-insert could race into duplicate (miner_id, service_type) rows;
afterwards every ``scalar_one_or_none`` lookup for that pair raised
MultipleResultsFound and the miner's config endpoints 500'd permanently.

``service_configs`` is created by ``Base.metadata.create_all`` at app start,
not by an alembic revision — on a database where the table does not exist
yet this migration is a no-op and create_all builds it with the constraint
already declared on the model. Where the table does exist, duplicates are
collapsed first (freshest row per pair wins) so the constraint can be added.

Revision ID: f6a1b2c3d4e5
Revises: 21da5cfdcc95
"""

from alembic import op
from sqlalchemy import inspect

revision = "f6a1b2c3d4e5"
down_revision = "21da5cfdcc95"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "service_configs" not in inspect(bind).get_table_names():
        return
    # Dedup: keep the freshest row per (miner_id, service_type). Window
    # functions are supported by both PostgreSQL and the sqlite versions
    # used in tests/development.
    op.execute(
        """
        DELETE FROM service_configs
        WHERE id NOT IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY miner_id, service_type
                           ORDER BY updated_at DESC, created_at DESC
                       ) AS rn
                FROM service_configs
            ) ranked
            WHERE rn = 1
        )
        """
    )
    op.create_unique_constraint("uq_service_config_miner_type", "service_configs", ["miner_id", "service_type"])


def downgrade() -> None:
    bind = op.get_bind()
    if "service_configs" not in inspect(bind).get_table_names():
        return
    op.drop_constraint("uq_service_config_miner_type", "service_configs", type_="unique")
