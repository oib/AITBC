#!/usr/bin/env python3
"""
Initialize genesis block for AITBC blockchain
"""

import sys

sys.path.insert(0, "src")

from aitbc.aitbc_logging import configure_logging, get_logger
from aitbc_chain.consensus.poa import PoAProposer, ProposerConfig
from aitbc_chain.database import session_scope
from aitbc_chain.models import Block

logger = get_logger(__name__)


def init_genesis():
    """Initialize the genesis block"""
    logger.info("Initializing genesis block...")

    # Check if genesis already exists
    with session_scope() as session:
        existing = session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()
        if existing:
            logger.info(f"Genesis block already exists: #{existing.height}")
            return

    # Create proposer config
    config = ProposerConfig(
        chain_id="ait-devnet",
        proposer_id="ait-devnet-proposer",
        interval_seconds=2,
    )

    # Create proposer and initialize genesis
    proposer = PoAProposer(config=config, session_factory=session_scope)

    # The _ensure_genesis_block method is called during proposer initialization
    # but we need to trigger it manually
    proposer._ensure_genesis_block()

    logger.info("Genesis block created successfully!")

    # Verify
    with session_scope() as session:
        genesis = session.exec(select(Block).where(Block.height == 0)).first()
        if genesis:
            logger.info(f"Genesis block: #{genesis.height}")
            logger.info(f"Hash: {genesis.hash}")
            logger.info(f"Proposer: {genesis.proposer}")
            logger.info(f"Timestamp: {genesis.timestamp}")


if __name__ == "__main__":
    from sqlmodel import select

    configure_logging(level="INFO")
    init_genesis()
