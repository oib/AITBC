#!/usr/bin/env python3
"""
Wrapper script for aitbc-blockchain-rpc service
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

# Get RPC configuration from environment or use defaults
rpc_host = os.getenv("rpc_bind_host", "0.0.0.0")
rpc_port = os.getenv("rpc_bind_port", "8006")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "aitbc_chain.app:app",
    "--host",
    rpc_host,
    "--port",
    rpc_port
]
os.execvp(exec_cmd[0], exec_cmd)
