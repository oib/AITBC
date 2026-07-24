"""reconcile schema drift v0.10.18

Revision ID: 236edfbd9728
Revises: e9cf23ae4640
Create Date: 2026-07-22 16:17:59.018400+00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "236edfbd9728"
down_revision: str | Sequence[str] | None = "e9cf23ae4640"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop legacy tables/indexes that are not part of the current SQLModel metadata.

    ponytail: The original migration tried to recreate these tables, which caused
    conflicts with the initial SQLModel create_all baseline on fresh DBs. The
    current codebase does not import these SQLModel classes in coordinator_api.main,
    so SQLModel.metadata does not include them and alembic check wants them gone.
    """
    op.drop_index("ix_market_metrics_recorded_at", table_name="analytics_market_metrics", if_exists=True)

    for table in (
        "fusion_models",
        "consumer_gpu_profiles",
        "auction_config",
        "multi_chain_transaction",
        "rl_configurations",
        "edge_gpu_metrics",
    ):
        op.drop_table(table, if_exists=True)


def downgrade() -> None:
    """Downgrade is a no-op; these legacy tables are not recreated."""
    pass
