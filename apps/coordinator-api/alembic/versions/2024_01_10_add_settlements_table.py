"""Add settlements table for cross-chain settlements

Revision ID: 2024_01_10_add_settlements_table
Revises: 2024_01_05_add_receipts_table
Create Date: 2025-01-10 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "2024_01_10_add_settlements_table"
down_revision = "2024_01_05_add_receipts_table"
branch_labels = None
depends_on = None


def upgrade():
    # Create settlements table
    op.create_table(
        "settlements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("source_chain_id", sa.Integer(), nullable=False),
        sa.Column("target_chain_id", sa.Integer(), nullable=False),
        sa.Column("receipt_hash", sa.String(length=66), nullable=True),
        sa.Column("proof_data", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
        sa.Column("payment_amount", sa.Numeric(precision=36, scale=18), nullable=True),
        sa.Column("payment_token", sa.String(length=42), nullable=True),
        sa.Column("nonce", sa.BigInteger(), nullable=False),
        sa.Column("signature", sa.String(length=132), nullable=True),
        sa.Column("bridge_name", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("transaction_hash", sa.String(length=66), nullable=True),
        sa.Column("gas_used", sa.BigInteger(), nullable=True),
        sa.Column("fee_paid", sa.Numeric(precision=36, scale=18), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"], ondelete="CASCADE"),
        if_not_exists=True,
    )

    # Create indexes
    op.create_index("ix_settlements_job_id", "settlements", ["job_id"], if_not_exists=True)
    op.create_index("ix_settlements_status", "settlements", ["status"], if_not_exists=True)
    op.create_index("ix_settlements_bridge_name", "settlements", ["bridge_name"], if_not_exists=True)
    op.create_index("ix_settlements_created_at", "settlements", ["created_at"], if_not_exists=True)
    op.create_index("ix_settlements_message_id", "settlements", ["message_id"], if_not_exists=True)


def downgrade():
    # Drop indexes (the table and its FK are dropped together, so the explicit
    # drop_constraint is omitted for SQLite compatibility)
    op.drop_index("ix_settlements_message_id", table_name="settlements", if_exists=True)
    op.drop_index("ix_settlements_created_at", table_name="settlements", if_exists=True)
    op.drop_index("ix_settlements_bridge_name", table_name="settlements", if_exists=True)
    op.drop_index("ix_settlements_status", table_name="settlements", if_exists=True)
    op.drop_index("ix_settlements_job_id", table_name="settlements", if_exists=True)

    # Drop table
    op.drop_table("settlements", if_exists=True)
