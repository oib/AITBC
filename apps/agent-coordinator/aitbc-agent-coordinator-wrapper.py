#!/usr/bin/env python3
"""
Wrapper script for aitbc-agent-coordinator service
Uses centralized aitbc utilities for path configuration
"""

import os

from aitbc.constants import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}:{REPO_DIR}/apps/agent-coordinator/src"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Create required directories
from aitbc.utils.paths import ensure_dir

ensure_dir(DATA_DIR / "agent-coordinator")
ensure_dir(LOG_DIR / "agent-coordinator")

log_level = os.getenv("LOG_LEVEL", "info").lower()
access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8107",
    "--log-level",
    log_level,
]
if access_log:
    exec_cmd.append("--access-log")
os.execvp(exec_cmd[0], exec_cmd)
