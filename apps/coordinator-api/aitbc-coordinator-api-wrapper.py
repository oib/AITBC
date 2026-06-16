#!/usr/bin/env python3
"""
Wrapper script for coordinator-api service
Uses centralized aitbc utilities for path configuration
"""

import os

from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = "REPO_DIR:REPO_DIR/coordinator-api/src"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)


log_level = os.getenv("LOG_LEVEL", "info").lower()
access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")

# coordinator-api bind configuration
# Use COORDINATOR_API_BIND_HOST for bind address (default: 127.0.0.1)
# Use COORDINATOR_API_PORT for port (default: 8203)
bind_host = os.getenv("COORDINATOR_API_BIND_HOST", "127.0.0.1")
bind_port = os.getenv("COORDINATOR_API_PORT", "8203")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    bind_host,
    "--port",
    bind_port,
    "--workers",
    "1",
    "--timeout-keep-alive",
    "30",
    "--limit-concurrency",
    "100",
    "--backlog",
    "256",
    "--log-level",
    log_level,
]
if access_log:
    exec_cmd.append("--access-log")
os.execvp(exec_cmd[0], exec_cmd)
