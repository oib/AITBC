#!/usr/bin/env python3
"""
Wallet Daemon Entry Point

This module provides the entry point for running the AITBC wallet daemon
with multi-chain support.
"""

import uvicorn
from pathlib import Path

from aitbc import get_logger
from app.main import app
from app.settings import settings

logger = get_logger(__name__)

def main():
    """Main entry point for the wallet daemon"""
    logger.info("Starting AITBC Wallet Daemon with Multi-Chain Support")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Coordinator URL: {settings.coordinator_base_url}")
    logger.info(f"Ledger DB Path: {settings.ledger_db_path}")
    
    # Create data directory if it doesn't exist
    data_dir = settings.ledger_db_path.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize chain manager
    try:
        from app.chain.manager import chain_manager
        logger.info("Initializing chain manager...")
        
        # Load chains from configuration
        chain_manager.load_chains()
        
        # Log chain information
        chains = chain_manager.list_chains()
        logger.info(f"Loaded {len(chains)} chains:")
        for chain in chains:
            logger.info(f"  - {chain.chain_id}: {chain.name} ({chain.status.value})")
        
        logger.info(f"Default chain: {chain_manager.default_chain_id}")
        
    except Exception as e:
        logger.error(f"Failed to initialize chain manager: {e}")
        logger.info("Continuing without multi-chain support...")
    
    # Start the server
    logger.info(f"Starting server on {settings.host}:{settings.port}")
    
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info" if not settings.debug else "debug"
    )

if __name__ == "__main__":
    main()
