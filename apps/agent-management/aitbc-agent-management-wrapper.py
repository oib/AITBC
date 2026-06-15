#!/usr/bin/env python3
"""
Wrapper script for aitbc-agent-management service
Uses centralized aitbc utilities for path configuration
"""

import os

from aitbc.constants import DATA_DIR, LOG_DIR, REPO_DIR

# Set up environment
os.environ["PYTHONPATH"] = f"{REPO_DIR}:{REPO_DIR}/apps/agent-management/src:{REPO_DIR}/apps/coordinator-api/src"
os.environ["DATA_DIR"] = str(DATA_DIR / "agent-management")
os.environ["LOG_DIR"] = str(LOG_DIR / "agent-management")

# Create required directories
from aitbc.utils.paths import ensure_dir

ensure_dir(DATA_DIR / "agent-management")
ensure_dir(LOG_DIR / "agent-management")

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
    "8012",
    "--log-level",
    log_level,
]
if access_log:
    exec_cmd.append("--access-log")
os.execvp(exec_cmd[0], exec_cmd)
