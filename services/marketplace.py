#!/usr/bin/env python3
"""
Marketplace Service for AITBC Production
"""

import sys
import os
import logging

# Add paths
sys.path.insert(0, '/opt/aitbc/production/services')  # Keep old path for compatibility
sys.path.insert(0, '/opt/aitbc/services')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting AITBC Marketplace Service")
    # Try to import the original marketplace service
    try:
        import marketplace
        logger.info("Marketplace service started")
    except ImportError as e:
        logger.error(f"Failed to import marketplace: {e}")
        logger.info("Marketplace service running in standby mode")
        import time
        while True:
            time.sleep(60)
            logger.info("Marketplace service heartbeat")
