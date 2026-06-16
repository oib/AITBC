#!/usr/bin/env python3
"""
Wrapper script for gpu service
Uses centralized aitbc utilities for path configuration
"""

import os

from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = "REPO_DIR:REPO_DIR/gpu/src"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)


log_level = os.getenv("LOG_LEVEL", "info").lower()
access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")

# gpu bind configuration
# Use GPU_BIND_HOST for bind address (default: 127.0.0.1)
# Use GPU_BIND_PORT for port (default: 8102)
bind_host = os.getenv("GPU_BIND_HOST", "127.0.0.1")
bind_port = os.getenv("GPU_BIND_PORT", "8102")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "gpu_service.main:app",
    "--host",
    bind_host,
    "--port",
    bind_port,
    "--log-level",
    log_level,
]
if access_log:
    exec_cmd.append("--access-log")
os.execvp(exec_cmd[0], exec_cmd)
