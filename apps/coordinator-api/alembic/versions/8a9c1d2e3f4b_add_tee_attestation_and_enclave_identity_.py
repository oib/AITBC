"""add tee_attestation and enclave_identity tables

Revision ID: 8a9c1d2e3f4b
Revises: 79e94b77d6bd
Create Date: 2026-07-24 16:30:00.000000+00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a9c1d2e3f4b"
down_revision: str | Sequence[str] | None = "79e94b77d6bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tee_attestation and enclave_identity tables."""
    op.create_table(
        "tee_attestation",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("enclave_id", sa.String(length=255), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("measurement", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_tee_attestation_enclave_id"),
        "tee_attestation",
        ["enclave_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_tee_attestation_measurement"),
        "tee_attestation",
        ["measurement"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_tee_attestation_status"),
        "tee_attestation",
        ["status"],
        unique=False,
        if_not_exists=True,
    )

    op.create_table(
        "enclave_identity",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("enclave_id", sa.String(length=255), nullable=False),
        sa.Column("public_key", sa.String(length=1024), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_enclave_identity_enclave_id"),
        "enclave_identity",
        ["enclave_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_enclave_identity_agent_id"),
        "enclave_identity",
        ["agent_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_enclave_identity_status"),
        "enclave_identity",
        ["status"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop tee_attestation and enclave_identity tables."""
    op.drop_index(
        op.f("ix_enclave_identity_status"),
        table_name="enclave_identity",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_enclave_identity_agent_id"),
        table_name="enclave_identity",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_enclave_identity_enclave_id"),
        table_name="enclave_identity",
        if_exists=True,
    )
    op.drop_table("enclave_identity", if_exists=True)
    op.drop_index(
        op.f("ix_tee_attestation_status"),
        table_name="tee_attestation",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_tee_attestation_measurement"),
        table_name="tee_attestation",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_tee_attestation_enclave_id"),
        table_name="tee_attestation",
        if_exists=True,
    )
    op.drop_table("tee_attestation", if_exists=True)
