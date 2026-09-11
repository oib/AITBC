"""Migrate legacy IpfsRentalToken rows to MarketplaceJob/Payment.

This script is idempotent.  It creates `MarketplaceJob` and
`MarketplaceJobPayment` records for every `IpfsRentalToken` that does not
already have a corresponding `MarketplaceJob` with the same `rental_id`.
It never deletes the legacy tokens.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "apps" / "marketplace" / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from marketplace_service.domain.marketplace import IpfsRentalToken, MarketplaceJob, MarketplaceJobPayment
from marketplace_service.storage import get_session_context, init_db


async def main() -> None:
    os.environ.setdefault("AITBC_DATA_DIR", "/var/lib/aitbc")
    await init_db()

    migrated = 0
    skipped = 0

    async with get_session_context() as session:
        from sqlalchemy import select

        result = await session.execute(select(IpfsRentalToken))
        tokens = list(result.scalars().all())

        for token in tokens:
            # Idempotency: skip if a marketplace job with the same id exists.
            existing = await session.get(MarketplaceJob, token.rental_id)
            if existing:
                skipped += 1
                continue

            payment_status = {
                "active": "escrowed",
                "expired": "released",
                "released": "released",
                "refunded": "refunded",
                "refund_pending": "refund_pending",
            }.get(token.status, "pending")

            job = MarketplaceJob(
                id=token.rental_id,
                offer_id=token.offer_id,
                service_type="ipfs",
                buyer_address=token.buyer_address,
                provider_address=token.provider_address,
                state="RUNNING" if token.status == "active" else token.status.upper(),
                access_key=token.access_key,
                escrow_contract_id=token.escrow_contract_id,
                tx_hash=token.tx_hash,
                payload={
                    "cid": token.cid,
                    "ipfs_api": token.ipfs_api,
                    "public_endpoint": token.public_endpoint,
                    "disk_quota_mb": token.disk_quota_mb,
                    "size": token.size,
                    "pinned": token.pinned,
                    "access_key": token.access_key,
                    "access_secret": token.access_secret,
                },
                constraints={"disk_quota_mb": token.disk_quota_mb},
                expires_at=token.expires_at,
                created_at=token.created_at,
                updated_at=token.updated_at,
                payment_status=payment_status,
            )

            payment = MarketplaceJobPayment(
                job_id=job.id,
                amount=Decimal("0"),  # Legacy tokens did not store price separately.
                currency="AITBC",
                status=payment_status,
                payment_method="aitbc_token",
                escrow_address=token.provider_address,
                transaction_hash=token.tx_hash,
                created_at=token.created_at,
                updated_at=token.updated_at,
                escrowed_at=token.created_at,
                expires_at=token.expires_at,
                meta_data={"migrated_from": "ipfs_rental_token"},
            )

            session.add(job)
            session.add(payment)
            job.payment_id = payment.id
            job.payment_amount = payment.amount
            migrated += 1

        await session.commit()

    print(f"Migrated {migrated} IPFS rental tokens; skipped {skipped}.")


if __name__ == "__main__":
    asyncio.run(main())
