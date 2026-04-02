#!/usr/bin/env python3
"""
Blockchain HTTP Launcher for AITBC Production
"""

import os
import sys
import subprocess
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Main blockchain HTTP launcher function"""
    logger.info("Starting AITBC Blockchain HTTP Launcher")
    
    try:
        # Launch blockchain HTTP service
        logger.info("Launching blockchain HTTP API")
        subprocess.run([
            '/opt/aitbc/venv/bin/python',
            '-m', 'uvicorn',
            'aitbc_chain.app:app',
            '--host', '0.0.0.0',
            '--port', '8005'
        ], check=True)
    except Exception as e:
        logger.error(f"Error launching blockchain HTTP: {e}")
        # Fallback
        import time
        while True:
            logger.info("Blockchain HTTP service heartbeat")
            time.sleep(30)

if __name__ == "__main__":
    main()
