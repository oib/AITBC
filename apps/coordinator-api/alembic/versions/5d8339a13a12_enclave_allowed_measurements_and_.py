"""enclave_allowed_measurements_and_attestation_registered

Revision ID: 5d8339a13a12
Revises: 4e8b7c2d1f0a
Create Date: 2026-08-25 18:39:44.924717+00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "5d8339a13a12"
down_revision: str | Sequence[str] | None = "4e8b7c2d1f0a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add allowed_measurements to enclave_identity and registered to tee_attestation."""
    bind = op.get_bind()
    existing_tee_cols = {c["name"] for c in inspect(bind).get_columns("tee_attestation")}
    existing_enclave_cols = {c["name"] for c in inspect(bind).get_columns("enclave_identity")}

    if "allowed_measurements" not in existing_enclave_cols:
        op.add_column(
            "enclave_identity",
            sa.Column("allowed_measurements", sa.JSON(), nullable=False, server_default=sa.text("[]")),
        )
    if "registered" not in existing_tee_cols:
        op.add_column(
            "tee_attestation",
            sa.Column("registered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    # Backfill existing attestations: mark as registered only when an ACTIVE
    # EnclaveIdentity exists for the same enclave_id.
    op.execute(
        """
        UPDATE tee_attestation
        SET registered = true
        WHERE status != rejected
          AND enclave_id IN (
              SELECT enclave_id FROM enclave_identity WHERE status = active
          )
        """
    )


def downgrade() -> None:
    """Remove the new columns."""
    op.drop_column("tee_attestation", "registered")
    op.drop_column("enclave_identity", "allowed_measurements")
