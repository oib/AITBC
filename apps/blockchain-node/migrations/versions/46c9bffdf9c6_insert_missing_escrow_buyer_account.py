"""Insert the missing escrow buyer account.

Four released escrow rows on hub point to buyer
0x35DABA990a37177398e0E0C1670BAa316a032417, who has a coordinator user
and wallet record but never had an on-chain `account` row created because the
escrow path does not debit the buyer or create the account.  Inserting the
account with zero balance makes the schema checkable without hiding the
underlying unbacked-payout finding: the account balance is 0 and the escrow
rows still record the released payouts.

Revision ID: 46c9bffdf9c6
Revises: f2b6c9d1e8a4
Create Date: 2026-08-23 00:00:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "46c9bffdf9c6"
down_revision: str | None = "f2b6c9d1e8a4"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT DISTINCT e.chain_id, e.buyer
            FROM escrow e
            LEFT JOIN account a
              ON e.chain_id = a.chain_id AND e.buyer = a.address
            WHERE a.address IS NULL
              AND e.buyer IS NOT NULL
            """
        )
    ).fetchall()
    for chain_id, buyer in rows:
        bind.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO account (chain_id, address, balance, nonce, updated_at)
                VALUES (:chain_id, :address, 0, 0, :updated_at)
                """
            ),
            {
                "chain_id": chain_id,
                "address": buyer,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )


def downgrade() -> None:
    """Downgrade is not supported for this data repair."""
    raise NotImplementedError("Downgrade not supported: it would re-delete a repaired account row.")
