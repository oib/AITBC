#!/usr/bin/env python3
"""
Wrapper script for aitbc-blockchain-node service
Uses centralized aitbc utilities for path configuration
"""

import sys
import os
from pathlib import Path

# Add aitbc to path
sys.path.insert(0, str(Path("/opt/aitbc")))
sys.path.insert(0, str(Path("/opt/aitbc/aitbc")))

from aitbc import ENV_FILE, NODE_ENV_FILE, REPO_DIR, DATA_DIR, LOG_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}/apps/blockchain-node/src"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Force disable block production in combined_main to prevent event loop blocking
# The combined_main runs both node logic and HTTP RPC server in the same process
# Block production in the RPC process can cause timeouts during transaction submission
os.environ["AITBC_FORCE_ENABLE_BLOCK_PRODUCTION"] = "true"
os.environ["ENABLE_BLOCK_PRODUCTION"] = "true"
os.environ["enable_block_production"] = "true"

# Execute the actual service
# Use combined_main to run both blockchain node and HTTP RPC server
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "aitbc_chain.main"
]
os.execvp(exec_cmd[0], exec_cmd)
