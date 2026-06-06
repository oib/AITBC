#!/usr/bin/env python3
"""
Wrapper script for aitbc-blockchain-node service
Uses centralized aitbc utilities for path configuration
"""

import os
import sys
from pathlib import Path

# Add aitbc to path
sys.path.insert(0, str(Path("/opt/aitbc")))
sys.path.insert(0, str(Path("/opt/aitbc/aitbc")))

from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}/apps/blockchain-node/src"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Block production is controlled by env file settings (enable_block_production)
# The proposer runs in the event loop without blocking - no force-enable needed

# Execute the actual service
# Use main.py to run blockchain node only (RPC is handled by separate service)
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "aitbc_chain.main"
]
os.execvp(exec_cmd[0], exec_cmd)
