"""create consent_record and phi_access_log tables

Revision ID: 9b0d2e4a1f5c
Revises: 8a9c1d2e3f4b
Create Date: 2026-07-24 17:00:00.000000+00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b0d2e4a1f5c"
down_revision: str | Sequence[str] | None = "8a9c1d2e3f4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create consent_record and phi_access_log tables."""
    op.create_table(
        "consent_record",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.String(length=255), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_consent_record_subject_id"),
        "consent_record",
        ["subject_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_consent_record_status"),
        "consent_record",
        ["status"],
        unique=False,
        if_not_exists=True,
    )

    op.create_table(
        "phi_access_log",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=1024), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_phi_access_log_subject_id"),
        "phi_access_log",
        ["subject_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_phi_access_log_actor_id"),
        "phi_access_log",
        ["actor_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_phi_access_log_action"),
        "phi_access_log",
        ["action"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_phi_access_log_resource_id"),
        "phi_access_log",
        ["resource_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_phi_access_log_outcome"),
        "phi_access_log",
        ["outcome"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop consent_record and phi_access_log tables."""
    op.drop_index(
        op.f("ix_phi_access_log_outcome"),
        table_name="phi_access_log",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_phi_access_log_resource_id"),
        table_name="phi_access_log",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_phi_access_log_action"),
        table_name="phi_access_log",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_phi_access_log_actor_id"),
        table_name="phi_access_log",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_phi_access_log_subject_id"),
        table_name="phi_access_log",
        if_exists=True,
    )
    op.drop_table("phi_access_log", if_exists=True)
    op.drop_index(
        op.f("ix_consent_record_status"),
        table_name="consent_record",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_consent_record_subject_id"),
        table_name="consent_record",
        if_exists=True,
    )
    op.drop_table("consent_record", if_exists=True)
