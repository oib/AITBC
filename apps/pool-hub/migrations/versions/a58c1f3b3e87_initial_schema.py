"""initial schema

Revision ID: a58c1f3b3e87
Revises: 
Create Date: 2025-09-27 12:07:40.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a58c1f3b3e87"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "miners",
        sa.Column("miner_id", sa.String(length=64), primary_key=True),
        sa.Column("api_key_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("addr", sa.String(length=256)),
        sa.Column("proto", sa.String(length=32)),
        sa.Column("gpu_vram_gb", sa.Float()),
        sa.Column("gpu_name", sa.String(length=128)),
        sa.Column("cpu_cores", sa.Integer()),
        sa.Column("ram_gb", sa.Float()),
        sa.Column("max_parallel", sa.Integer()),
        sa.Column("base_price", sa.Float()),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("trust_score", sa.Float(), server_default="0.5"),
        sa.Column("region", sa.String(length=64)),
    )

    op.create_table(
        "miner_status",
        sa.Column("miner_id", sa.String(length=64), sa.ForeignKey("miners.miner_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("queue_len", sa.Integer(), server_default="0"),
        sa.Column("busy", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("avg_latency_ms", sa.Integer()),
        sa.Column("temp_c", sa.Integer()),
        sa.Column("mem_free_gb", sa.Float()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    op.create_table(
        "match_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("hints", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb")),
        sa.Column("top_k", sa.Integer(), server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    op.create_table(
        "match_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("match_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("miner_id", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("explain", sa.Text()),
        sa.Column("eta_ms", sa.Integer()),
        sa.Column("price", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_match_results_request_id", "match_results", ["request_id"])

    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("miner_id", sa.String(length=64), sa.ForeignKey("miners.miner_id", ondelete="CASCADE"), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("fail_code", sa.String(length=64)),
        sa.Column("tokens_spent", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_feedback_miner_id", "feedback", ["miner_id"])
    op.create_index("ix_feedback_job_id", "feedback", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_job_id", table_name="feedback")
    op.drop_index("ix_feedback_miner_id", table_name="feedback")
    op.drop_table("feedback")

    op.drop_index("ix_match_results_request_id", table_name="match_results")
    op.drop_table("match_results")

    op.drop_table("match_requests")

    op.drop_table("miner_status")

    op.drop_table("miners")
