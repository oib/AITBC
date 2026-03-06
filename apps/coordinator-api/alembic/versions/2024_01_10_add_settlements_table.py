"""Add settlements table for cross-chain settlements

Revision ID: 2024_01_10_add_settlements_table
Revises: 2024_01_05_add_receipts_table
Create Date: 2025-01-10 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2024_01_10_add_settlements_table'
down_revision = '2024_01_05_add_receipts_table'
branch_labels = None
depends_on = None


def upgrade():
    # Create settlements table
    op.create_table(
        'settlements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.String(length=255), nullable=False),
        sa.Column('job_id', sa.String(length=255), nullable=False),
        sa.Column('source_chain_id', sa.Integer(), nullable=False),
        sa.Column('target_chain_id', sa.Integer(), nullable=False),
        sa.Column('receipt_hash', sa.String(length=66), nullable=True),
        sa.Column('proof_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('payment_amount', sa.Numeric(precision=36, scale=18), nullable=True),
        sa.Column('payment_token', sa.String(length=42), nullable=True),
        sa.Column('nonce', sa.BigInteger(), nullable=False),
        sa.Column('signature', sa.String(length=132), nullable=True),
        sa.Column('bridge_name', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('transaction_hash', sa.String(length=66), nullable=True),
        sa.Column('gas_used', sa.BigInteger(), nullable=True),
        sa.Column('fee_paid', sa.Numeric(precision=36, scale=18), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id')
    )
    
    # Create indexes
    op.create_index('ix_settlements_job_id', 'settlements', ['job_id'])
    op.create_index('ix_settlements_status', 'settlements', ['status'])
    op.create_index('ix_settlements_bridge_name', 'settlements', ['bridge_name'])
    op.create_index('ix_settlements_created_at', 'settlements', ['created_at'])
    op.create_index('ix_settlements_message_id', 'settlements', ['message_id'])
    
    # Add foreign key constraint for jobs table
    op.create_foreign_key(
        'fk_settlements_job_id',
        'settlements', 'jobs',
        ['job_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade():
    # Drop foreign key
    op.drop_constraint('fk_settlements_job_id', 'settlements', type_='foreignkey')
    
    # Drop indexes
    op.drop_index('ix_settlements_message_id', table_name='settlements')
    op.drop_index('ix_settlements_created_at', table_name='settlements')
    op.drop_index('ix_settlements_bridge_name', table_name='settlements')
    op.drop_index('ix_settlements_status', table_name='settlements')
    op.drop_index('ix_settlements_job_id', table_name='settlements')
    
    # Drop table
    op.drop_table('settlements')
