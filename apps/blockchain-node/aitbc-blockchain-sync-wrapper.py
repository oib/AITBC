#!/usr/bin/env python3
"""
Wrapper script for aitbc-blockchain-sync service
Uses centralized aitbc utilities for path configuration
"""

import os

from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}/apps/blockchain-node/src:{REPO_DIR}/apps/blockchain-node/scripts"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Get sync configuration from environment
redis_url = os.getenv("SYNC_REDIS_URL", "redis://localhost:6379")
node_id = os.getenv("SYNC_NODE_ID") or os.getenv("proposer_id")
if not node_id:
    raise ValueError("SYNC_NODE_ID or proposer_id environment variable is required")
rpc_port = os.getenv("SYNC_RPC_PORT", "8202")
leader_host = os.getenv("SYNC_LEADER_HOST", "127.0.0.1")
source_host = os.getenv("SYNC_SOURCE_HOST", "127.0.0.1")
source_port = os.getenv("SYNC_SOURCE_PORT", "8202")
import_host = os.getenv("SYNC_IMPORT_HOST", "127.0.0.1")
import_port = os.getenv("SYNC_IMPORT_PORT", "8202")
chain_id = os.getenv("SYNC_CHAIN_ID") or os.getenv("CHAIN_ID")
if not chain_id:
    raise ValueError("SYNC_CHAIN_ID or CHAIN_ID environment variable is required")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "aitbc_chain.chain_sync",
    "--redis",
    redis_url,
    "--node-id",
    node_id,
    "--rpc-port",
    rpc_port,
    "--leader-host",
    leader_host,
    "--source-host",
    source_host,
    "--source-port",
    source_port,
    "--import-host",
    import_host,
    "--import-port",
    import_port,
    "--chain-id",
    chain_id,
]
os.execvp(exec_cmd[0], exec_cmd)
