"""drop tee_attestation and enclave_identity tables (#2375)

The TEE/enclave feature is removed: no enclave hardware exists on the
fleet, so the attestation quote path, enclave registration endpoints and
the settlement-side TEE gate are all deleted. The SQLModel classes that
backed these tables lived in ``contexts/tee`` and are gone with it; this
revision drops the now-orphaned tables so fresh deploys and existing
databases converge through the migration chain (coordinator-api runs
``alembic upgrade head`` in ExecStartPre).

``DROP TABLE IF EXISTS`` keeps it a no-op for databases that never ran
the original TEE migrations.

Revision ID: b2375tee0drop
Revises: a2317b2c3d4e
Create Date: 2026-11-21

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2375tee0drop"
down_revision = "a2317b2c3d4e"
branch_labels = None
depends_on = None

_TEE_TABLES = [
    "tee_attestation",
    "enclave_identity",
]


def upgrade() -> None:
    cascade = " CASCADE" if op.get_bind().dialect.name == "postgresql" else ""
    for table in _TEE_TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{table}"{cascade}')


def downgrade() -> None:
    # The TEE feature is gone; re-creating empty tables would only preserve
    # a schema no code reads. Intentionally a no-op.
    pass
