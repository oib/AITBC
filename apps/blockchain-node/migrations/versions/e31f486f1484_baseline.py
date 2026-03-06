"""baseline

Revision ID: e31f486f1484
Revises: 
Create Date: 2025-09-27 05:58:27.490151

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e31f486f1484"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "block",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("hash", sa.String(), nullable=False),
        sa.Column("parent_hash", sa.String(), nullable=False),
        sa.Column("proposer", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("tx_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state_root", sa.String(), nullable=True),
    )
    op.create_index("ix_block_height", "block", ["height"], unique=True)
    op.create_index("ix_block_hash", "block", ["hash"], unique=True)
    op.create_index("ix_block_timestamp", "block", ["timestamp"], unique=False)

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
    op.create_index(
        "ix_transaction_block_height", "transaction", ["block_height"], unique=False
    )
    op.create_index(
        "ix_transaction_created_at", "transaction", ["created_at"], unique=False
    )

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

    op.create_table(
        "account",
        sa.Column("address", sa.String(), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nonce", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("address"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("account")

    op.drop_index("ix_receipt_recorded_at", table_name="receipt")
    op.drop_index("ix_receipt_block_height", table_name="receipt")
    op.drop_index("ix_receipt_receipt_id", table_name="receipt")
    op.drop_index("ix_receipt_job_id", table_name="receipt")
    op.drop_table("receipt")

    op.drop_index("ix_transaction_created_at", table_name="transaction")
    op.drop_index("ix_transaction_block_height", table_name="transaction")
    op.drop_index("ix_transaction_tx_hash", table_name="transaction")
    op.drop_table("transaction")

    op.drop_index("ix_block_timestamp", table_name="block")
    op.drop_index("ix_block_hash", table_name="block")
    op.drop_index("ix_block_height", table_name="block")
    op.drop_table("block")
