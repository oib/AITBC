"""add sla and capacity tables

Revision ID: b2a1c4d5e6f7
Revises: a58c1f3b3e87
Create Date: 2026-04-22 15:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b2a1c4d5e6f7"
down_revision = "a58c1f3b3e87"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to miner_status table
    op.add_column(
        "miner_status",
        sa.Column("uptime_pct", sa.Float(), nullable=True),
    )
    op.add_column(
        "miner_status",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create sla_metrics table
    op.create_table(
        "sla_metrics",
        sa.Column(
            "id",
            sa.String(36),
            primary_key=True,
        ),
        sa.Column(
            "miner_id",
            sa.String(length=64),
            sa.ForeignKey("miners.miner_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_type", sa.String(length=32), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("is_violation", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("meta_data", sa.JSON(), server_default=sa.text("'{}'")),
    )
    op.create_index("ix_sla_metrics_miner_id", "sla_metrics", ["miner_id"])
    op.create_index("ix_sla_metrics_timestamp", "sla_metrics", ["timestamp"])
    op.create_index("ix_sla_metrics_metric_type", "sla_metrics", ["metric_type"])

    # Create sla_violations table
    op.create_table(
        "sla_violations",
        sa.Column(
            "id",
            sa.String(36),
            primary_key=True,
        ),
        sa.Column(
            "miner_id",
            sa.String(length=64),
            sa.ForeignKey("miners.miner_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("violation_type", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("violation_duration_ms", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("meta_data", sa.JSON(), server_default=sa.text("'{}'")),
    )
    op.create_index("ix_sla_violations_miner_id", "sla_violations", ["miner_id"])
    op.create_index("ix_sla_violations_created_at", "sla_violations", ["created_at"])
    op.create_index("ix_sla_violations_severity", "sla_violations", ["severity"])

    # Create capacity_snapshots table
    op.create_table(
        "capacity_snapshots",
        sa.Column(
            "id",
            sa.String(36),
            primary_key=True,
        ),
        sa.Column("total_miners", sa.Integer(), nullable=False),
        sa.Column("active_miners", sa.Integer(), nullable=False),
        sa.Column("total_parallel_capacity", sa.Integer(), nullable=False),
        sa.Column("total_queue_length", sa.Integer(), nullable=False),
        sa.Column("capacity_utilization_pct", sa.Float(), nullable=False),
        sa.Column("forecast_capacity", sa.Integer(), nullable=False),
        sa.Column("recommended_scaling", sa.String(length=32), nullable=False),
        sa.Column("scaling_reason", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("meta_data", sa.JSON(), server_default=sa.text("'{}'")),
    )
    op.create_index("ix_capacity_snapshots_timestamp", "capacity_snapshots", ["timestamp"])


def downgrade() -> None:
    # Drop capacity_snapshots table
    op.drop_index("ix_capacity_snapshots_timestamp", table_name="capacity_snapshots")
    op.drop_table("capacity_snapshots")

    # Drop sla_violations table
    op.drop_index("ix_sla_violations_severity", table_name="sla_violations")
    op.drop_index("ix_sla_violations_created_at", table_name="sla_violations")
    op.drop_index("ix_sla_violations_miner_id", table_name="sla_violations")
    op.drop_table("sla_violations")

    # Drop sla_metrics table
    op.drop_index("ix_sla_metrics_metric_type", table_name="sla_metrics")
    op.drop_index("ix_sla_metrics_timestamp", table_name="sla_metrics")
    op.drop_index("ix_sla_metrics_miner_id", table_name="sla_metrics")
    op.drop_table("sla_metrics")

    # Remove columns from miner_status table
    op.drop_column("miner_status", "last_heartbeat_at")
    op.drop_column("miner_status", "uptime_pct")
