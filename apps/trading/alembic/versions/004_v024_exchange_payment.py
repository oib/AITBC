"""create exchange_payment table

Revision ID: 004_v024_exchange_payment
Revises: 003
Create Date: 2026-08-29 09:30:00.000000+00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "004_v024_exchange_payment"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the exchange_payment table."""
    op.create_table(
        "exchange_payment",
        sa.Column("payment_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("aitbc_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("eth_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("payment_address", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("confirmations", sa.Integer(), nullable=False),
        sa.Column("tx_hash", sa.String(length=128), nullable=True),
        sa.Column("confirmed_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("payment_id"),
    )
    op.create_index(
        op.f("ix_exchange_payment_idempotency_key"),
        "exchange_payment",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    """Drop the exchange_payment table."""
    op.drop_index(
        op.f("ix_exchange_payment_idempotency_key"),
        table_name="exchange_payment",
    )
    op.drop_table("exchange_payment")
