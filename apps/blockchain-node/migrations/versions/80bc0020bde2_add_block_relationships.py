"""add block relationships

Revision ID: 80bc0020bde2
Revises: e31f486f1484
Create Date: 2025-09-27 06:02:11.656859

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "80bc0020bde2"
down_revision: Union[str, Sequence[str], None] = "e31f486f1484"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Recreate transaction table with foreign key to block.height
    op.drop_table("transaction")
    op.create_table(
        "transaction",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tx_hash", sa.String(), nullable=False),
        sa.Column("block_height", sa.Integer(), sa.ForeignKey("block.height"), nullable=True),
        sa.Column("sender", sa.String(), nullable=False),
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_transaction_tx_hash", "transaction", ["tx_hash"], unique=True)
    op.create_index("ix_transaction_block_height", "transaction", ["block_height"], unique=False)
    op.create_index("ix_transaction_created_at", "transaction", ["created_at"], unique=False)

    # Recreate receipt table with foreign key to block.height
    op.drop_table("receipt")
    op.create_table(
        "receipt",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("receipt_id", sa.String(), nullable=False),
        sa.Column("block_height", sa.Integer(), sa.ForeignKey("block.height"), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("miner_signature", sa.JSON(), nullable=False),
        sa.Column("coordinator_attestations", sa.JSON(), nullable=False),
        sa.Column("minted_amount", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_receipt_job_id", "receipt", ["job_id"], unique=False)
    op.create_index("ix_receipt_receipt_id", "receipt", ["receipt_id"], unique=True)
    op.create_index("ix_receipt_block_height", "receipt", ["block_height"], unique=False)
    op.create_index("ix_receipt_recorded_at", "receipt", ["recorded_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    # Revert receipt table without foreign key
    op.drop_table("receipt")
    op.create_table(
        "receipt",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("receipt_id", sa.String(), nullable=False),
        sa.Column("block_height", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("miner_signature", sa.JSON(), nullable=False),
        sa.Column("coordinator_attestations", sa.JSON(), nullable=False),
        sa.Column("minted_amount", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_receipt_job_id", "receipt", ["job_id"], unique=False)
    op.create_index("ix_receipt_receipt_id", "receipt", ["receipt_id"], unique=True)
    op.create_index("ix_receipt_block_height", "receipt", ["block_height"], unique=False)
    op.create_index("ix_receipt_recorded_at", "receipt", ["recorded_at"], unique=False)

    # Revert transaction table without foreign key
    op.drop_table("transaction")
    op.create_table(
        "transaction",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tx_hash", sa.String(), nullable=False),
        sa.Column("block_height", sa.Integer(), nullable=True),
        sa.Column("sender", sa.String(), nullable=False),
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_transaction_tx_hash", "transaction", ["tx_hash"], unique=True)
    op.create_index("ix_transaction_block_height", "transaction", ["block_height"], unique=False)
    op.create_index("ix_transaction_created_at", "transaction", ["created_at"], unique=False)
