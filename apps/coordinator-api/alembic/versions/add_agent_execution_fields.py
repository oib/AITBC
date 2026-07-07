"""Add verification_level to agent_executions and step_type to agent_step_executions

These columns are required by the aitbc-agent-core protocol adapters but were
missing from the SQLModel definitions. Both default to their enum's base value
so existing rows backfill cleanly.

Revision ID: add_agent_execution_fields
Revises: add_job_cross_chain_columns
Create Date: 2026-07-07 00:00:02.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "add_agent_execution_fields"
down_revision = "add_job_cross_chain_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_executions",
        sa.Column("verification_level", sa.String(20), nullable=False, server_default="basic"),
    )
    op.add_column(
        "agent_step_executions",
        sa.Column("step_type", sa.String(20), nullable=False, server_default="inference"),
    )


def downgrade() -> None:
    op.drop_column("agent_step_executions", "step_type")
    op.drop_column("agent_executions", "verification_level")
