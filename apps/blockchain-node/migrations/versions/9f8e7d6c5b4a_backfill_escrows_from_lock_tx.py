"""Back-fill missing Escrow rows from on-chain ESCROW_LOCK transactions.

The escrow lock path silently failed to persist the Escrow row until the
session.get(Escrow, job_id) primary-key fix. This migration reconstructs the
missing rows from the authoritative ESCROW_LOCK transactions on the chain.

A row is only inserted when:
  - an ESCROW_LOCK transaction exists for the job_id,
  - no Escrow row exists for that job_id,
  - no ESCROW_RELEASE or ESCROW_REFUND transaction exists for that job_id.

This makes the historical escrowed jobs refundable through the existing
/rpc/escrow/{job_id}/refund path without any source-code changes.

Revision ID: 9f8e7d6c5b4a
Revises: fix_transaction_block_foreign_key
Create Date: 2026-08-25 00:00:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f8e7d6c5b4a"
down_revision: str | None = "fix_transaction_block_foreign_key"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # Find the earliest ESCROW_LOCK for each job_id that has no Escrow row.
    rows = bind.execute(
        sa.text(
            """
            SELECT t.chain_id, t.tx_hash, t.sender, t.value, t.created_at,
                   json_extract(t.payload, '$.job_id') AS job_id,
                   json_extract(t.payload, '$.provider') AS provider
            FROM "transaction" t
            WHERE t.type = 'ESCROW_LOCK'
              AND json_extract(t.payload, '$.job_id') IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM escrow e
                  WHERE e.job_id = json_extract(t.payload, '$.job_id')
              )
            ORDER BY t.created_at ASC, t.id ASC
            """
        )
    ).fetchall()

    for chain_id, tx_hash, buyer_raw, amount, created_at, job_id, provider_raw in rows:
        # Skip anything that has already settled or been refunded on-chain.
        released = bind.execute(
            sa.text(
                """
                SELECT 1 FROM "transaction"
                WHERE type = 'ESCROW_RELEASE'
                  AND json_extract(payload, '$.job_id') = :job_id
                LIMIT 1
                """
            ),
            {"job_id": job_id},
        ).first()
        refunded = bind.execute(
            sa.text(
                """
                SELECT 1 FROM "transaction"
                WHERE type = 'ESCROW_REFUND'
                  AND json_extract(payload, '$.job_id') = :job_id
                LIMIT 1
                """
            ),
            {"job_id": job_id},
        ).first()

        if released or refunded:
            continue

        # Canonicalize addresses so the rows match the EvmAddress column/FK.
        try:
            from aitbc.crypto.signature_recovery import canonical_address

            buyer = canonical_address(buyer_raw)
            provider = canonical_address(provider_raw)
        except Exception:
            # Cannot reliably reconstruct this one; skip it.
            continue

        # Satisfy the FKs to the account table.
        for addr in (buyer, provider):
            bind.execute(
                sa.text(
                    """
                    INSERT OR IGNORE INTO account
                    (chain_id, address, balance, nonce, updated_at)
                    VALUES (:chain_id, :address, 0, 0, :updated_at)
                    """
                ),
                {
                    "chain_id": chain_id,
                    "address": addr,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )

        # Use the transaction timestamp if it is available.
        if created_at is None:
            created = datetime.now(UTC)
        elif isinstance(created_at, str):
            try:
                created = datetime.fromisoformat(created_at)
            except ValueError:
                created = datetime.now(UTC)
        else:
            created = created_at

        bind.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO escrow
                (job_id, chain_id, buyer, provider, amount, status,
                 created_at, lock_tx_hash)
                VALUES
                (:job_id, :chain_id, :buyer, :provider, :amount, 'locked',
                 :created_at, :lock_tx_hash)
                """
            ),
            {
                "job_id": job_id,
                "chain_id": chain_id,
                "buyer": buyer,
                "provider": provider,
                "amount": amount,
                "created_at": created.isoformat(),
                "lock_tx_hash": tx_hash,
            },
        )


def downgrade() -> None:
    """Downgrade is not supported for this data repair."""
    raise NotImplementedError("Downgrade not supported: would remove repaired escrow rows.")
