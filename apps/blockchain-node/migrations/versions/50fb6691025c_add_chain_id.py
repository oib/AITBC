"""add_chain_id

Revision ID: 50fb6691025c
Revises: fix_transaction_block_foreign_key
Create Date: 2026-03-03 17:48:48.141666

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '50fb6691025c'
down_revision: Union[str, Sequence[str], None] = 'fix_transaction_block_foreign_key'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('account', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chain_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='ait-testnet'))
        
    with op.batch_alter_table('block', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chain_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='ait-testnet'))
        batch_op.drop_index('ix_block_height')
        batch_op.create_index('ix_block_height', ['height'], unique=False)
        batch_op.create_index('ix_block_chain_id', ['chain_id'], unique=False)
        batch_op.create_unique_constraint('uix_block_chain_height', ['chain_id', 'height'])

    with op.batch_alter_table('receipt', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chain_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='ait-testnet'))
        batch_op.drop_index('ix_receipt_receipt_id')
        batch_op.create_index('ix_receipt_receipt_id', ['receipt_id'], unique=False)
        batch_op.create_index('ix_receipt_chain_id', ['chain_id'], unique=False)
        batch_op.create_unique_constraint('uix_receipt_chain_id', ['chain_id', 'receipt_id'])
        # Drop foreign key constraint using naming convention if needed, 
        # but since SQLite doesn't support it directly, batch_alter_table handles it
        # batch_op.drop_constraint(None, type_='foreignkey') 

    with op.batch_alter_table('transaction', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chain_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='ait-testnet'))
        batch_op.drop_index('ix_transaction_tx_hash')
        batch_op.create_index('ix_transaction_tx_hash', ['tx_hash'], unique=False)
        batch_op.create_index('ix_transaction_chain_id', ['chain_id'], unique=False)
        batch_op.create_unique_constraint('uix_tx_chain_hash', ['chain_id', 'tx_hash'])

def downgrade() -> None:
    pass
