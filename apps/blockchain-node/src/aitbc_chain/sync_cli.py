#!/usr/bin/env python3
"""
Standalone bulk sync utility for fast catch-up.
Usage: python -m aitbc_chain.sync_cli --source http://10.1.223.40:8006 [--batch-size 100]
"""

import argparse
import asyncio
import os

from aitbc_chain.config import settings
from aitbc_chain.database import init_db, session_scope
from aitbc_chain.logger import get_logger
from aitbc_chain.sync import ChainSync

from aitbc.aitbc_logging import configure_logging

configure_logging(level="INFO", service_name="blockchain-sync", to_file=True)
logger = get_logger(__name__)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk import blocks from a leader to catch up quickly")
    parser.add_argument("--source", default=os.getenv("AITBC_SYNC_SOURCE", "http://127.0.0.1:8202"), help="Source RPC URL")
    parser.add_argument(
        "--import-url", default=os.getenv("AITBC_SYNC_IMPORT_URL", "http://127.0.0.1:8202"), help="Local RPC URL for import"
    )
    parser.add_argument("--batch-size", type=int, default=100, help="Blocks per batch")
    parser.add_argument("--poll-interval", type=float, default=0.2, help="Seconds between batches")
    args = parser.parse_args()

    # Ensure the chain DB schema is up to date (adds missing columns such as
    # block.signature to existing DBs). create_all only handles new tables.
    init_db(settings.chain_id)

    sync = ChainSync(
        session_factory=session_scope,  # type: ignore[arg-type]
        chain_id=settings.chain_id,
        batch_size=args.batch_size,
        poll_interval=args.poll_interval,
    )
    try:
        imported = await sync.bulk_import_from(args.source)
        logger.info("Bulk sync complete", extra={"blocks_imported": imported})
    finally:
        await sync.close()


if __name__ == "__main__":
    asyncio.run(main())
