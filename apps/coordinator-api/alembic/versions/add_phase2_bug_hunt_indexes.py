"""Add indexes for Phase 2 bug hunt performance fixes

Revision ID: add_phase2_bug_hunt_indexes
Revises: add_query_performance_indexes
Create Date: 2025-01-08 14:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "add_phase2_bug_hunt_indexes"
down_revision: str | None = "add_query_performance_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add index on agent_workflows.is_public
    op.create_index(op.f("ix_agent_workflows_is_public"), "agent_workflows", ["is_public"], unique=False, if_not_exists=True)

    # Add indexes on agent_reputations timestamp fields
    op.create_index(
        op.f("ix_agent_reputations_created_at"), "agent_reputations", ["created_at"], unique=False, if_not_exists=True
    )
    op.create_index(
        op.f("ix_agent_reputations_updated_at"), "agent_reputations", ["updated_at"], unique=False, if_not_exists=True
    )
    op.create_index(
        op.f("ix_agent_reputations_last_activity"), "agent_reputations", ["last_activity"], unique=False, if_not_exists=True
    )

    # Add index on gpu_registry.price_per_hour
    op.create_index(
        op.f("ix_gpu_registry_price_per_hour"), "gpu_registry", ["price_per_hour"], unique=False, if_not_exists=True
    )

    # Add composite index on bounties.status + bounties.deadline
    op.create_index(op.f("idx_bounty_status_deadline"), "bounties", ["status", "deadline"], unique=False, if_not_exists=True)


def downgrade() -> None:
    # Remove composite index on bounties
    op.drop_index(op.f("idx_bounty_status_deadline"), table_name="bounties", if_exists=True)

    # Remove index on gpu_registry.price_per_hour
    op.drop_index(op.f("ix_gpu_registry_price_per_hour"), table_name="gpu_registry", if_exists=True)

    # Remove indexes on agent_reputations
    op.drop_index(op.f("ix_agent_reputations_last_activity"), table_name="agent_reputations", if_exists=True)
    op.drop_index(op.f("ix_agent_reputations_updated_at"), table_name="agent_reputations", if_exists=True)
    op.drop_index(op.f("ix_agent_reputations_created_at"), table_name="agent_reputations", if_exists=True)

    # Remove index on agent_workflows.is_public
    op.drop_index(op.f("ix_agent_workflows_is_public"), table_name="agent_workflows", if_exists=True)
