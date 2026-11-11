"""drop dead trade_feedback/trading_analytics tables (#1840)

The #1603 dead-table inventory flagged both as write-only/dead mirrors —
models existed and 003_v023 created them, but nothing in
apps/trading/src selects, inserts or updates them. Live-DB census
(pg_stat_user_tables, all 5 nodes) confirmed both empty.

``trade_settlements`` is deliberately NOT dropped — the orphan-pair
design decision is still open (#1840 HOLD).

Revision ID: 007_v1840_dead_table_drop
Revises: 006_v1554_settlement_expiry
Create Date: 2026-11-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "007_v1840_dead_table_drop"
down_revision = "006_v1554_settlement_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CASCADE on Postgres: the dead cohort FKs each other and drops together.
    # SQLite has no CASCADE clause; emit plain DROP there.
    cascade = " CASCADE" if op.get_bind().dialect.name == "postgresql" else ""
    for table in ("trade_feedback", "trading_analytics"):
        op.execute(f'DROP TABLE IF EXISTS "{table}"{cascade}')


def downgrade() -> None:
    # Recreate the empty shells so downgrade-to-base stays reversible:
    # 003's downgrade drops them unconditionally, and a pass-through here
    # would leave that drop pointing at missing tables. DDL mirrors
    # 003_v023_trading_domain_tables.py exactly; the fleet census confirmed
    # both tables empty, so there is no row data to restore.
    op.create_table(
        "trade_feedback",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agreement_id", sa.String(), nullable=False),
        sa.Column("reviewer_agent_id", sa.String(), nullable=False),
        sa.Column("reviewed_agent_id", sa.String(), nullable=False),
        sa.Column("reviewer_role", sa.String(), nullable=False),
        sa.Column("overall_rating", sa.Float(), nullable=False),
        sa.Column("communication_rating", sa.Float(), nullable=False),
        sa.Column("performance_rating", sa.Float(), nullable=False),
        sa.Column("timeliness_rating", sa.Float(), nullable=False),
        sa.Column("value_rating", sa.Float(), nullable=False),
        sa.Column("feedback_text", sa.String(1000), nullable=False),
        sa.Column("feedback_tags", sa.JSON(), nullable=True),
        sa.Column("trade_category", sa.String(), nullable=False),
        sa.Column("trade_complexity", sa.String(), nullable=False),
        sa.Column("trade_duration", sa.Integer(), nullable=True),
        sa.Column("verified_trade", sa.Boolean(), nullable=False),
        sa.Column("moderation_status", sa.String(), nullable=False),
        sa.Column("moderator_notes", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("trade_completed_at", sa.DateTime(), nullable=False),
        sa.Column("feedback_context", sa.JSON(), nullable=True),
        sa.Column("performance_metrics", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["agreement_id"],
            ["trade_agreements.agreement_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index("ix_trade_feedback_agreement_id", "trade_feedback", ["agreement_id"], unique=False, if_not_exists=True)
    op.create_index(
        "ix_trade_feedback_reviewed_agent_id", "trade_feedback", ["reviewed_agent_id"], unique=False, if_not_exists=True
    )
    op.create_index(
        "ix_trade_feedback_reviewer_agent_id", "trade_feedback", ["reviewer_agent_id"], unique=False, if_not_exists=True
    )
    op.create_table(
        "trading_analytics",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("period_type", sa.String(), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("total_trades", sa.Integer(), nullable=False),
        sa.Column("completed_trades", sa.Integer(), nullable=False),
        sa.Column("failed_trades", sa.Integer(), nullable=False),
        sa.Column("cancelled_trades", sa.Integer(), nullable=False),
        sa.Column("total_trade_volume", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("average_trade_value", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("total_platform_fees", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("trade_type_distribution", sa.JSON(), nullable=True),
        sa.Column("active_buyers", sa.Integer(), nullable=False),
        sa.Column("active_sellers", sa.Integer(), nullable=False),
        sa.Column("new_agents", sa.Integer(), nullable=False),
        sa.Column("average_matching_time", sa.Float(), nullable=False),
        sa.Column("average_negotiation_time", sa.Float(), nullable=False),
        sa.Column("average_settlement_time", sa.Float(), nullable=False),
        sa.Column("success_rate", sa.Float(), nullable=False),
        sa.Column("regional_distribution", sa.JSON(), nullable=True),
        sa.Column("average_rating", sa.Float(), nullable=False),
        sa.Column("dispute_rate", sa.Float(), nullable=False),
        sa.Column("repeat_trade_rate", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("analytics_data", sa.JSON(), nullable=True),
        sa.Column("trends_data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
