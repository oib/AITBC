"""Add validator_deactivation table for on-chain slash deactivation (#1198).

Revision ID: b2c4d6e8f0a1
Revises: a8b9c0d1e2f3
Create Date: 2026-11-08 10:00:00.000000+00:00

Consensus-visible slashing state: VALIDATOR_DEACTIVATE transactions write
one row per (chain_id, validator_address) here at block apply, so the
slash-driven active-set predicate is a pure function of canonical chain
state on every node.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c4d6e8f0a1"
down_revision: str | Sequence[str] | None = "a8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "validator_deactivation" in inspector.get_table_names():
        return
    op.create_table(
        "validator_deactivation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain_id", sa.String(), nullable=False),
        sa.Column("validator_address", sa.String(), nullable=False),
        sa.Column("evidence_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("deactivation_tx_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("block_height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("chain_id", "validator_address", name="uix_validator_deactivation_chain_addr"),
    )
    op.create_index("ix_validator_deactivation_chain_id", "validator_deactivation", ["chain_id"])
    op.create_index("ix_validator_deactivation_validator_address", "validator_deactivation", ["validator_address"])
    op.create_index("ix_validator_deactivation_deactivation_tx_hash", "validator_deactivation", ["deactivation_tx_hash"])
    op.create_index("ix_validator_deactivation_block_height", "validator_deactivation", ["block_height"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "validator_deactivation" not in inspector.get_table_names():
        return
    op.drop_index("ix_validator_deactivation_block_height", table_name="validator_deactivation")
    op.drop_index("ix_validator_deactivation_deactivation_tx_hash", table_name="validator_deactivation")
    op.drop_index("ix_validator_deactivation_validator_address", table_name="validator_deactivation")
    op.drop_index("ix_validator_deactivation_chain_id", table_name="validator_deactivation")
    op.drop_table("validator_deactivation")
