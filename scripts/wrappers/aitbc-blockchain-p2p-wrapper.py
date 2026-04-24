#!/usr/bin/env python3
"""
Wrapper script for aitbc-blockchain-p2p service
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
os.environ["PYTHONPATH"] = f"{REPO_DIR}/apps/blockchain-node/src:{REPO_DIR}/apps/blockchain-node/scripts"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Get P2P configuration from environment
p2p_host = os.getenv("p2p_bind_host", "0.0.0.0")
p2p_port = os.getenv("p2p_bind_port", "7000")
p2p_peers = os.getenv("p2p_peers", "")
p2p_node_id = os.getenv("p2p_node_id", "")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "aitbc_chain.p2p_network",
    "--host", p2p_host,
    "--port", p2p_port,
    "--peers", p2p_peers,
    "--node-id", p2p_node_id
]
os.execvp(exec_cmd[0], exec_cmd)
