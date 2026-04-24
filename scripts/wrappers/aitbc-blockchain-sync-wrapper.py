#!/usr/bin/env python3
"""
Wrapper script for aitbc-blockchain-sync service
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

# Get sync configuration from environment
redis_url = os.getenv("SYNC_REDIS_URL", "redis://localhost:6379")
node_id = os.getenv("SYNC_NODE_ID", "ait18yefwwclgmyu2a74zvv0hj3a3xw6gxsn4akrj963kp069j9xy5ns3kurun")
rpc_port = os.getenv("SYNC_RPC_PORT", "8006")
leader_host = os.getenv("SYNC_LEADER_HOST", "10.1.223.40")
source_host = os.getenv("SYNC_SOURCE_HOST", "10.1.223.40")
source_port = os.getenv("SYNC_SOURCE_PORT", "8006")
import_host = os.getenv("SYNC_IMPORT_HOST", "10.1.223.40")
import_port = os.getenv("SYNC_IMPORT_PORT", "8006")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "aitbc_chain.chain_sync",
    "--redis", redis_url,
    "--node-id", node_id,
    "--rpc-port", rpc_port,
    "--leader-host", leader_host,
    "--source-host", source_host,
    "--source-port", source_port,
    "--import-host", import_host,
    "--import-port", import_port
]
os.execvp(exec_cmd[0], exec_cmd)
