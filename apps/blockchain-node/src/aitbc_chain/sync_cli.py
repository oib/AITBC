#!/usr/bin/env python3
"""
Standalone bulk sync utility for fast catch-up.
Usage: python -m aitbc_chain.sync_cli --source http://10.1.223.40:8006 [--batch-size 100]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path for standalone execution
sys.path.insert(0, str(Path(__file__).parent))

from aitbc_chain.config import settings
from aitbc_chain.database import session_scope
from aitbc_chain.sync import ChainSync


async def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk import blocks from a leader to catch up quickly")
    parser.add_argument("--source", default="http://10.1.223.40:8006", help="Source RPC URL")
    parser.add_argument("--import-url", default="http://127.0.0.1:8006", help="Local RPC URL for import")
    parser.add_argument("--batch-size", type=int, default=100, help="Blocks per batch")
    parser.add_argument("--poll-interval", type=float, default=0.2, help="Seconds between batches")
    args = parser.parse_args()

    sync = ChainSync(
        session_factory=session_scope,
        chain_id=settings.chain_id,
        batch_size=args.batch_size,
        poll_interval=args.poll_interval,
    )
    try:
        imported = await sync.bulk_import_from(args.source, import_url=args.import_url)
        print(f"[+] Bulk sync complete: imported {imported} blocks")
    finally:
        await sync.close()


if __name__ == "__main__":
    asyncio.run(main())
