"""enclave_allowed_measurements_and_attestation_registered

Revision ID: 5d8339a13a12
Revises: 4e8b7c2d1f0a
Create Date: 2026-08-25 18:39:44.924717+00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5d8339a13a12"
down_revision: str | Sequence[str] | None = "4e8b7c2d1f0a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add allowed_measurements to enclave_identity and registered to tee_attestation."""
    op.add_column(
        "enclave_identity",
        sa.Column("allowed_measurements", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "tee_attestation",
        sa.Column("registered", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    # Backfill existing attestations: mark as registered only when an ACTIVE
    # EnclaveIdentity exists for the same enclave_id.
    op.execute(
        """
        UPDATE tee_attestation
        SET registered = 1
        WHERE status != 'rejected'
          AND enclave_id IN (
              SELECT enclave_id FROM enclave_identity WHERE status = 'active'
          )
        """
    )


def downgrade() -> None:
    """Remove the new columns."""
    op.drop_column("tee_attestation", "registered")
    op.drop_column("enclave_identity", "allowed_measurements")
