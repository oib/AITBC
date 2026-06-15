#!/usr/bin/env python3
"""
Wrapper script for aitbc-blockchain-rpc service
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
os.environ["AITBC_FORCE_ENABLE_BLOCK_PRODUCTION"] = "false"
os.environ["ENABLE_BLOCK_PRODUCTION"] = "false"
os.environ["enable_block_production"] = "false"

# Get RPC configuration from environment or use defaults
rpc_host = os.getenv("RPC_BIND_HOST") or os.getenv("rpc_bind_host") or "127.0.0.1"
rpc_port = os.getenv("RPC_BIND_PORT") or os.getenv("rpc_bind_port") or "8202"

log_level = os.getenv("LOG_LEVEL", "info").lower()
access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "aitbc_chain.app:app",
    "--host",
    rpc_host,
    "--port",
    rpc_port,
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
