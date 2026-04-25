#!/usr/bin/env python3
"""
Wrapper script for aitbc-agent-daemon service
Uses centralized aitbc utilities for path configuration
"""

import sys
import os
from pathlib import Path

# Add aitbc to path
sys.path.insert(0, str(Path("/opt/aitbc")))
sys.path.insert(0, str(Path("/opt/aitbc/aitbc")))

from aitbc import ENV_FILE, NODE_ENV_FILE, REPO_DIR, DATA_DIR, LOG_DIR, KEYSTORE_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}:{REPO_DIR}/packages/py/aitbc-agent-sdk/src:{REPO_DIR}/apps/agent-coordinator/scripts:{REPO_DIR}"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    f"{REPO_DIR}/apps/agent-coordinator/scripts/agent_daemon.py",
    "--wallet", "temp-agent",
    "--address", "ait1d18e286fc0c12888aca94732b5507c8787af71a5",
    "--password-file", str(KEYSTORE_DIR / ".agent_daemon_password"),
    "--keystore-dir", str(KEYSTORE_DIR),
    "--db-path", str(DATA_DIR / "chain.db"),
    "--rpc-url", "http://localhost:8006",
    "--poll-interval", "2",
    "--reply-message", "pong",
    "--trigger-message", "ping"
]
os.execvp(exec_cmd[0], exec_cmd)
