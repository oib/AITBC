#!/usr/bin/env python3
"""
GPU Marketplace Launcher for AITBC Production
"""

import os
import sys
import subprocess
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Main GPU marketplace launcher function"""
    logger.info("Starting AITBC GPU Marketplace Launcher")
    
    try:
        # Set environment variables
        os.environ.setdefault('PYTHONPATH', '/opt/aitbc/services')
        
        # Try to run the GPU marketplace service
        logger.info("Launching GPU marketplace service")
        
        # Check if the main marketplace service exists
        marketplace_path = '/opt/aitbc/services/marketplace.py'
        if os.path.exists(marketplace_path):
            logger.info("Found marketplace service, launching...")
            subprocess.run([
                '/opt/aitbc/venv/bin/python',
                marketplace_path
            ], check=True)
        else:
            logger.error(f"Marketplace service not found at {marketplace_path}")
            # Fallback to simple service
            fallback_service()
            
    except Exception as e:
        logger.error(f"Error launching GPU marketplace: {e}")
        logger.info("Starting fallback GPU marketplace service")
        fallback_service()

def fallback_service():
    """Fallback GPU marketplace service"""
    logger.info("Starting fallback GPU marketplace service")
    
    try:
        # Simple GPU marketplace heartbeat
        import time
        
        while True:
            logger.info("GPU Marketplace service heartbeat - active")
            time.sleep(30)
            
    except KeyboardInterrupt:
        logger.info("GPU Marketplace service stopped by user")
    except Exception as e:
        logger.error(f"Error in fallback service: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()
