"""create financial compliance tables

Revision ID: 1a7d8e9b0c2f
Revises: 9b0d2e4a1f5c
Create Date: 2026-07-24 18:00:00.000000+00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1a7d8e9b0c2f"
down_revision: str | Sequence[str] | None = "9b0d2e4a1f5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create transaction_audit_record and non_repudiation_proof tables."""
    op.create_table(
        "transaction_audit_record",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("transaction_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("counterparty_id", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("asset", sa.String(length=32), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("policy_framework", sa.String(length=32), nullable=False),
        sa.Column("consent_required", sa.Boolean(), nullable=False),
        sa.Column("consent_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("proof_hash", sa.String(length=128), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_transaction_audit_record_transaction_id"),
        "transaction_audit_record",
        ["transaction_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_transaction_audit_record_actor_id"),
        "transaction_audit_record",
        ["actor_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_transaction_audit_record_counterparty_id"),
        "transaction_audit_record",
        ["counterparty_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_transaction_audit_record_asset"),
        "transaction_audit_record",
        ["asset"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_transaction_audit_record_classification"),
        "transaction_audit_record",
        ["classification"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_transaction_audit_record_policy_framework"),
        "transaction_audit_record",
        ["policy_framework"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_transaction_audit_record_status"),
        "transaction_audit_record",
        ["status"],
        unique=False,
        if_not_exists=True,
    )

    op.create_table(
        "non_repudiation_proof",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("transaction_id", sa.String(length=64), nullable=False),
        sa.Column("signer_id", sa.String(length=255), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_non_repudiation_proof_transaction_id"),
        "non_repudiation_proof",
        ["transaction_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_non_repudiation_proof_signer_id"),
        "non_repudiation_proof",
        ["signer_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop financial compliance tables."""
    op.drop_index(
        op.f("ix_non_repudiation_proof_signer_id"),
        table_name="non_repudiation_proof",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_non_repudiation_proof_transaction_id"),
        table_name="non_repudiation_proof",
        if_exists=True,
    )
    op.drop_table("non_repudiation_proof", if_exists=True)
    op.drop_index(
        op.f("ix_transaction_audit_record_status"),
        table_name="transaction_audit_record",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_transaction_audit_record_policy_framework"),
        table_name="transaction_audit_record",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_transaction_audit_record_classification"),
        table_name="transaction_audit_record",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_transaction_audit_record_asset"),
        table_name="transaction_audit_record",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_transaction_audit_record_counterparty_id"),
        table_name="transaction_audit_record",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_transaction_audit_record_actor_id"),
        table_name="transaction_audit_record",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_transaction_audit_record_transaction_id"),
        table_name="transaction_audit_record",
        if_exists=True,
    )
    op.drop_table("transaction_audit_record", if_exists=True)
