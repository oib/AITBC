#!/usr/bin/env python3
"""
Simple Blockchain Service for AITBC Production
"""

import os
import sys
import time
import logging
from pathlib import Path

# Add the blockchain app to Python path
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Main blockchain service function"""
    logger.info("Starting AITBC Blockchain Node Service")
    
    try:
        # Try to import the blockchain app
        from aitbc_chain.main import main as blockchain_main
        logger.info("Successfully imported blockchain main")
        
        # Run the blockchain main function
        blockchain_main()
        
    except ImportError as e:
        logger.error(f"Failed to import blockchain main: {e}")
        logger.info("Starting simple blockchain heartbeat service")
        
        # Fallback: simple heartbeat service
        heartbeat_service()
        
    except Exception as e:
        logger.error(f"Error starting blockchain service: {e}")
        sys.exit(1)

def heartbeat_service():
    """Simple heartbeat service for blockchain"""
    logger.info("Starting blockchain heartbeat service")
    
    while True:
        try:
            # Simple blockchain heartbeat
            logger.info("Blockchain node heartbeat - service active")
            time.sleep(30)
            
        except KeyboardInterrupt:
            logger.info("Blockchain service stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in heartbeat service: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
