#!/usr/bin/env python3
"""
Wrapper script for aitbc-agent-registry service
Uses centralized aitbc utilities for path configuration
"""

import os

from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "app:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8204",
    "--app-dir",
    f"{REPO_DIR}/aitbc/agent_registry/src",
]
os.execvp(exec_cmd[0], exec_cmd)
