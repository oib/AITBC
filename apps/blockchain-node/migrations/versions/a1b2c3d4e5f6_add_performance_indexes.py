"""add performance indexes

Revision ID: a1b2c3d4e5f6
Revises: fix_transaction_block_foreign_key
Create Date: 2026-06-28 14:00:00.000000

Adds missing database indexes for query performance (v0.6.0):
- block.parent_hash (sync parent lookups)
- transaction.sender (balance queries)
- transaction.recipient (incoming transfer queries)
- transaction (chain_id, block_height) composite (block tx fetches)
- cross_chain_transfer.status (pending transfer queries)
- stake.status (active validator filtering)
- governance_proposal.status (proposal filtering)
- mempool (chain_id, fee) composite (fee-priority queries)
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "fix_transaction_block_foreign_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    """Check if a table exists in the current database."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists on a table."""
    if not _table_exists(table_name):
        return False
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add performance indexes with if_not_exists=True (safe for existing DBs).

    Some tables (cross_chain_transfer, stake, governance_proposal, mempool) may
    not exist yet if only the baseline migrations ran — they are created by
    SQLModel.metadata.create_all at service startup. Guard each index creation
    with a table/column existence check.
    """
    # Single-column indexes (guard for tables/columns that may not exist yet)
    if _column_exists("block", "parent_hash"):
        op.create_index("idx_block_parent_hash", "block", ["parent_hash"], if_not_exists=True)
    if _column_exists("transaction", "sender"):
        op.create_index("idx_tx_sender", "transaction", ["sender"], if_not_exists=True)
    if _column_exists("transaction", "recipient"):
        op.create_index("idx_tx_recipient", "transaction", ["recipient"], if_not_exists=True)
    if _table_exists("cross_chain_transfer"):
        op.create_index("idx_cct_status", "cross_chain_transfer", ["status"], if_not_exists=True)
    if _table_exists("stake"):
        op.create_index("idx_stake_status", "stake", ["status"], if_not_exists=True)
    if _table_exists("governance_proposal"):
        op.create_index("idx_gov_proposal_status", "governance_proposal", ["status"], if_not_exists=True)

    # Composite indexes
    if _column_exists("transaction", "chain_id") and _column_exists("transaction", "block_height"):
        op.create_index("idx_tx_chain_height", "transaction", ["chain_id", "block_height"], if_not_exists=True)
    if _table_exists("mempool") and _column_exists("mempool", "chain_id") and _column_exists("mempool", "fee"):
        op.create_index("idx_mempool_chain_fee", "mempool", ["chain_id", "fee"], if_not_exists=True)


def downgrade() -> None:
    """Remove performance indexes."""
    op.drop_index("idx_mempool_chain_fee", table_name="mempool")
    op.drop_index("idx_tx_chain_height", table_name="transaction")
    op.drop_index("idx_gov_proposal_status", table_name="governance_proposal")
    op.drop_index("idx_stake_status", table_name="stake")
    op.drop_index("idx_cct_status", table_name="cross_chain_transfer")
    op.drop_index("idx_tx_recipient", table_name="transaction")
    op.drop_index("idx_tx_sender", table_name="transaction")
    op.drop_index("idx_block_parent_hash", table_name="block")
