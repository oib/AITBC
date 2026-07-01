"""v0.8.0 inter-chain trading tables (InterChainTrade + IslandRegistry)

Revision ID: 001
Revises:
Create Date: 2026-06-29 16:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inter_chain_trades",
        sa.Column("trade_id", sa.String(), nullable=False),
        sa.Column("source_chain", sa.String(), nullable=False),
        sa.Column("dest_chain", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("sender", sa.String(), nullable=False),
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=True),
        sa.Column("price", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_tx_hash", sa.String(), nullable=True),
        sa.Column("dest_tx_hash", sa.String(), nullable=True),
        sa.Column("matched_trade_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("trade_id"),
        if_not_exists=True,
    )
    op.create_index("idx_inter_chain_status", "inter_chain_trades", ["status"], if_not_exists=True)
    op.create_index("idx_inter_chain_chains", "inter_chain_trades", ["source_chain", "dest_chain"], if_not_exists=True)
    op.create_index("idx_inter_chain_sender", "inter_chain_trades", ["sender"], if_not_exists=True)
    op.create_index("idx_inter_chain_trades_source_chain", "inter_chain_trades", ["source_chain"], if_not_exists=True)
    op.create_index("idx_inter_chain_trades_dest_chain", "inter_chain_trades", ["dest_chain"], if_not_exists=True)

    op.create_table(
        "island_registry",
        sa.Column("chain_id", sa.String(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("block_height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("offers_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("registered_at", sa.DateTime(), nullable=False),
        sa.Column("last_sync", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("chain_id"),
        if_not_exists=True,
    )
    op.create_index("idx_island_status", "island_registry", ["status"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("idx_island_status", table_name="island_registry")
    op.drop_table("island_registry")
    op.drop_index("idx_inter_chain_trades_dest_chain", table_name="inter_chain_trades")
    op.drop_index("idx_inter_chain_trades_source_chain", table_name="inter_chain_trades")
    op.drop_index("idx_inter_chain_sender", table_name="inter_chain_trades")
    op.drop_index("idx_inter_chain_chains", table_name="inter_chain_trades")
    op.drop_index("idx_inter_chain_status", table_name="inter_chain_trades")
    op.drop_table("inter_chain_trades")
