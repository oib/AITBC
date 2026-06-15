#!/usr/bin/env python3
"""
Wrapper script for aitbc-blockchain-event-bridge service
Uses centralized aitbc utilities for path configuration
"""

import os

from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}/apps/blockchain-event-bridge/src:{REPO_DIR}"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "blockchain_event_bridge.main:app",
    "--host",
    os.getenv("bind_host", "0.0.0.0"),
    "--port",
    os.getenv("bind_port", "8205"),
]
os.execvp(exec_cmd[0], exec_cmd)
