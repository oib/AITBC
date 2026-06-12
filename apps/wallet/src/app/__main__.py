"""
Wallet Daemon Entry Point

This module provides the entry point for running the AITBC wallet daemon
with multi-chain support.
"""
import uvicorn
from aitbc import get_logger
from app.main import app
from app.settings import settings
logger = get_logger(__name__)

def main():
    """Main entry point for the wallet daemon"""
    logger.info('Starting AITBC Wallet Daemon with Multi-Chain Support')
    logger.info('Debug mode: %s', settings.debug)
    logger.info('Coordinator URL: %s', settings.coordinator_base_url)
    logger.info('Ledger DB Path: %s', settings.ledger_db_path)
    data_dir = settings.ledger_db_path.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        from app.chain.manager import chain_manager
        logger.info('Initializing chain manager...')
        chain_manager.load_chains()
        chains = chain_manager.list_chains()
        logger.info('Loaded %s chains:', len(chains))
        for chain in chains:
            logger.info('  - %s: %s (%s)', chain.chain_id, chain.name, chain.status.value)
        logger.info('Default chain: %s', chain_manager.default_chain_id)
    except Exception as e:
        logger.error('Failed to initialize chain manager: %s', e)
        logger.info('Continuing without multi-chain support...')
    logger.info('Starting server on %s:%s', settings.host, settings.port)
    uvicorn.run(app, host=settings.host, port=settings.port, reload=settings.debug, log_level='info' if not settings.debug else 'debug')
if __name__ == '__main__':
    main()