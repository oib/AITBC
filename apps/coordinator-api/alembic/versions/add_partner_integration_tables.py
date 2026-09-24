"""Add partner integration registry tables

Replaces the module-level in-memory PARTNERS_DB/WEBHOOKS_DB dicts in the
partners router with persistent storage shared across workers and restarts.

Revision ID: add_partner_integration_tables
Revises: e7f2a9c4b1d0
Create Date: 2026-09-25 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "add_partner_integration_tables"
down_revision = "e7f2a9c4b1d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_partner",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("website", sa.String(), nullable=False),
        sa.Column("contact", sa.String(), nullable=False),
        sa.Column("integration_type", sa.String(), nullable=False),
        sa.Column("api_key_hash", sa.String(), nullable=False),
        sa.Column("api_secret_hash", sa.String(), nullable=False),
        sa.Column("rate_limit", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_integration_partner_api_key_hash",
        "integration_partner",
        ["api_key_hash"],
        unique=False,
        if_not_exists=True,
    )

    op.create_table(
        "partner_webhook",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("partner_id", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=True),
        sa.Column("secret", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["integration_partner.id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_partner_webhook_partner_id",
        "partner_webhook",
        ["partner_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_partner_webhook_partner_id", table_name="partner_webhook", if_exists=True)
    op.drop_table("partner_webhook", if_exists=True)
    op.drop_index("ix_integration_partner_api_key_hash", table_name="integration_partner", if_exists=True)
    op.drop_table("integration_partner", if_exists=True)
