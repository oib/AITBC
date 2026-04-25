#!/usr/bin/env python3
"""
AITBC Monitor Service
"""

import time
import json
from pathlib import Path
import psutil

from aitbc import get_logger, DATA_DIR

def main():
    logger = get_logger('aitbc-monitor')
    
    while True:
        try:
            # System stats
            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent
            logger.info(f'System: CPU {cpu_percent}%, Memory {memory_percent}%')
            
            # Blockchain stats
            blockchain_file = DATA_DIR / 'data/blockchain/aitbc/blockchain.json'
            if blockchain_file.exists():
                with open(blockchain_file, 'r') as f:
                    data = json.load(f)
                    logger.info(f'Blockchain: {len(data.get("blocks", []))} blocks')
            
            # Marketplace stats
            marketplace_dir = DATA_DIR / 'data/marketplace'
            if marketplace_dir.exists():
                listings_file = marketplace_dir / 'gpu_listings.json'
                if listings_file.exists():
                    with open(listings_file, 'r') as f:
                        listings = json.load(f)
                        logger.info(f'Marketplace: {len(listings)} GPU listings')
            
            time.sleep(30)
        except (json.JSONDecodeError, FileNotFoundError, PermissionError, IOError) as e:
            logger.error(f'Monitoring error: {type(e).__name__}: {e}')
            time.sleep(60)
        except psutil.Error as e:
            logger.error(f'System monitoring error: {type(e).__name__}: {e}')
            time.sleep(60)

if __name__ == "__main__":
    main()
