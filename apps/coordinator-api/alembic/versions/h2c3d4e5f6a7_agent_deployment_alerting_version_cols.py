"""agent_deployment_configs alerting/version columns (#1312)

Revision ID: h2c3d4e5f6a7
Revises: g1b2c3d4e5f6
Create Date: 2026-11-09 00:00:00.000000+00:00

COORD-SVC-LAYER-DEFECTS-1: create_alerting_rules assigned
config.alerting_rules — a field that did not exist on the model, so every
call raised ValueError and deploy_to_production could never report
success. agent_version/previous_version give rollback_deployment the
version pair it already reads via getattr(); without the columns every
instance fell into rollback_errors and rollback could never succeed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "h2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "g1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("alerting_rules", sa.Column("alerting_rules", sa.JSON(), nullable=True)),
    (
        "agent_version",
        sa.Column("agent_version", sa.String(length=64), server_default="", nullable=False),
    ),
    (
        "previous_version",
        sa.Column("previous_version", sa.String(length=64), server_default="", nullable=False),
    ),
)


def upgrade() -> None:
    if context.is_offline_mode():
        existing: set[str] = set()
    else:
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        if "agent_deployment_configs" not in inspector.get_table_names():
            return
        existing = {c["name"] for c in inspector.get_columns("agent_deployment_configs")}
    for name, column in _COLUMNS:
        if name not in existing:
            op.add_column("agent_deployment_configs", column)


def downgrade() -> None:
    for name, _column in reversed(_COLUMNS):
        op.drop_column("agent_deployment_configs", name)
