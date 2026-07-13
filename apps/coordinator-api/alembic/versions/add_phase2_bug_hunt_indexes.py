"""Add indexes for Phase 2 bug hunt performance fixes

Revision ID: add_phase2_bug_hunt_indexes
Revises: add_query_performance_indexes
Create Date: 2025-01-08 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op


# revision identifiers, used by Alembic.
revision: str = "add_phase2_bug_hunt_indexes"
down_revision: str | None = "add_agent_execution_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # Add index on agent_workflows.is_public
    if _table_exists("agent_workflows"):
        op.create_index(
            op.f("ix_agent_workflows_is_public"), "agent_workflows", ["is_public"], unique=False, if_not_exists=True
        )

    # Add indexes on agent_reputations timestamp fields
    if _table_exists("agent_reputations"):
        op.create_index(
            op.f("ix_agent_reputations_created_at"), "agent_reputations", ["created_at"], unique=False, if_not_exists=True
        )
        op.create_index(
            op.f("ix_agent_reputations_updated_at"), "agent_reputations", ["updated_at"], unique=False, if_not_exists=True
        )
        op.create_index(
            op.f("ix_agent_reputations_last_activity"),
            "agent_reputations",
            ["last_activity"],
            unique=False,
            if_not_exists=True,
        )

    # Add index on gpu_registry.price_per_hour
    if _table_exists("gpu_registry"):
        op.create_index(
            op.f("ix_gpu_registry_price_per_hour"), "gpu_registry", ["price_per_hour"], unique=False, if_not_exists=True
        )

    # Add composite index on bounties.status + bounties.deadline
    if _table_exists("bounties"):
        op.create_index(
            op.f("idx_bounty_status_deadline"), "bounties", ["status", "deadline"], unique=False, if_not_exists=True
        )


def downgrade() -> None:
    # Remove composite index on bounties
    if _table_exists("bounties"):
        op.drop_index(op.f("idx_bounty_status_deadline"), table_name="bounties", if_exists=True)

    # Remove index on gpu_registry.price_per_hour
    if _table_exists("gpu_registry"):
        op.drop_index(op.f("ix_gpu_registry_price_per_hour"), table_name="gpu_registry", if_exists=True)

    # Remove indexes on agent_reputations
    if _table_exists("agent_reputations"):
        op.drop_index(op.f("ix_agent_reputations_last_activity"), table_name="agent_reputations", if_exists=True)
        op.drop_index(op.f("ix_agent_reputations_updated_at"), table_name="agent_reputations", if_exists=True)
        op.drop_index(op.f("ix_agent_reputations_created_at"), table_name="agent_reputations", if_exists=True)

    # Remove index on agent_workflows.is_public
    if _table_exists("agent_workflows"):
        op.drop_index(op.f("ix_agent_workflows_is_public"), table_name="agent_workflows", if_exists=True)
