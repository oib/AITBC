#!/usr/bin/env python3
"""
Standalone bulk sync utility for fast catch-up.
Usage: python -m aitbc_chain.sync_cli --source http://<peer>:8202 [--batch-size 100]

For island chains (or any chain whose unit env files carry chain-specific
settings like VALIDATOR_SET), pass --env-file so the settings singleton
loads them before the first import of aitbc_chain.config:

    python -m aitbc_chain.sync_cli --source https://peer/island \
        --env-file /etc/aitbc/blockchain-island.env --env-file /etc/aitbc/node-island.env
"""

import argparse
import asyncio
import os

from aitbc.aitbc_logging import configure_logging

configure_logging(level="INFO", service_name="blockchain-sync", to_file=True)


def _apply_env_files(env_files: list[str]) -> None:
    """Merge --env-file paths into AITBC_CHAIN_ENV_FILE before config import.

    aitbc_chain.config reads its env file list at import time, so this must
    run before any aitbc_chain.* import. Paths are comma-joined after any
    existing AITBC_CHAIN_ENV_FILE value; pydantic-settings gives later files
    precedence, so the unit's env file overrides blockchain.env where they
    overlap (e.g. the island's VALIDATOR_SET). When the var is unset the
    implicit /etc/aitbc/blockchain.env default is prepended — setting the
    var at all replaces that default.
    """
    if not env_files:
        return
    existing = os.environ.get("AITBC_CHAIN_ENV_FILE")
    if existing is None:
        existing = "/etc/aitbc/blockchain.env"
    merged = [p for p in (existing + "," + ",".join(env_files)).split(",") if p]
    os.environ["AITBC_CHAIN_ENV_FILE"] = ",".join(merged)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk import blocks from a leader to catch up quickly")
    parser.add_argument("--source", default=os.getenv("AITBC_SYNC_SOURCE", "http://127.0.0.1:8202"), help="Source RPC URL")
    parser.add_argument(
        "--import-url", default=os.getenv("AITBC_SYNC_IMPORT_URL", "http://127.0.0.1:8202"), help="Local RPC URL for import"
    )
    parser.add_argument("--batch-size", type=int, default=100, help="Blocks per batch")
    parser.add_argument("--poll-interval", type=float, default=0.2, help="Seconds between batches")
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        metavar="PATH",
        help="Env file to load into chain settings before startup (repeatable); "
        "use the unit's env files for island chains, e.g. /etc/aitbc/blockchain-island.env",
    )
    args = parser.parse_args()

    _apply_env_files(args.env_file)

    # Imported lazily: aitbc_chain.config snapshots env files at import time,
    # so settings must not exist before --env-file is applied.
    from aitbc_chain.config import settings
    from aitbc_chain.database import init_db, session_scope
    from aitbc_chain.logger import get_logger
    from aitbc_chain.sync import ChainSync

    logger = get_logger(__name__)

    # Ensure the chain DB schema is up to date (adds missing columns such as
    # block.signature to existing DBs). create_all only handles new tables.
    init_db(settings.chain_id)

    sync = ChainSync(
        session_factory=lambda: session_scope(settings.chain_id),
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
