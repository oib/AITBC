"""Add context prefixes to table names

Revision ID: 001_context_prefixes
Revises: add_phase2_bug_hunt_indexes
Create Date: 2026-05-12

This revision was intended to rename tables to use context-specific prefixes:
- marketplaceoffer -> marketplace_offer
- marketplacebid -> marketplace_bid
- job_payments -> payments_job_payment
- payment_escrows -> payments_escrow
- agent_identities -> agent_identity_identity
- cross_chain_mappings -> agent_identity_cross_chain_mapping
- identity_verifications -> agent_identity_verification

These renames are not applied because the current SQLModel definitions still use
the original table names. The revision is preserved as a no-op so the migration
graph remains linear and `alembic upgrade head` is well-defined.

"""

# revision identifiers, used by Alembic.
revision = "001_context_prefixes"
down_revision = "add_phase2_bug_hunt_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ponytail: no-op. The table renames are intentionally skipped because the
    # current model definitions still use the original table names.
    pass


def downgrade() -> None:
    # ponytail: no-op. See upgrade() above.
    pass
