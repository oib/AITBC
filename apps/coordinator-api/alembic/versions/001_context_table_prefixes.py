"""Add context prefixes to table names

Revision ID: 001_context_prefixes
Revises: 
Create Date: 2026-05-12

This migration renames tables to use context-specific prefixes:
- marketplaceoffer -> marketplace_offer
- marketplacebid -> marketplace_bid
- job_payments -> payments_job_payment
- payment_escrows -> payments_escrow
- agent_identities -> agent_identity_identity
- cross_chain_mappings -> agent_identity_cross_chain_mapping
- identity_verifications -> agent_identity_verification

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '001_context_prefixes'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Marketplace context table renames
    op.rename_table('marketplaceoffer', 'marketplace_offer')
    op.rename_table('marketplacebid', 'marketplace_bid')

    # Payments context table renames
    op.rename_table('job_payments', 'payments_job_payment')
    op.rename_table('payment_escrows', 'payments_escrow')

    # Agent Identity context table renames
    op.rename_table('agent_identities', 'agent_identity_identity')
    op.rename_table('cross_chain_mappings', 'agent_identity_cross_chain_mapping')
    op.rename_table('identity_verifications', 'agent_identity_verification')


def downgrade() -> None:
    # Reverse the renames
    op.rename_table('marketplace_offer', 'marketplaceoffer')
    op.rename_table('marketplace_bid', 'marketplacebid')

    op.rename_table('payments_job_payment', 'job_payments')
    op.rename_table('payments_escrow', 'payment_escrows')

    op.rename_table('agent_identity_identity', 'agent_identities')
    op.rename_table('agent_identity_cross_chain_mapping', 'cross_chain_mappings')
    op.rename_table('agent_identity_verification', 'identity_verifications')
