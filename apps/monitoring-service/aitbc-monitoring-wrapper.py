#!/usr/bin/env python3
"""
Wrapper script for aitbc-monitoring service
Uses centralized aitbc utilities for path configuration
"""

import os
import sys
from pathlib import Path

# Add aitbc to path
sys.path.insert(0, str(Path("/opt/aitbc")))
sys.path.insert(0, str(Path("/opt/aitbc/aitbc")))


def build_cmd() -> list[str]:
    """Build the uvicorn argv for the monitoring dashboard.

    The bind host comes from ``BIND_HOST`` and defaults to ``127.0.0.1``
    — the same default ``main.py`` uses and the one
    ``aitbc-monitoring.service`` binds explicitly (#1482). The dashboard
    is unauthenticated: it exposes service topology, per-service health
    detail and host CPU/memory/disk/network metrics, so the old hardcoded
    ``0.0.0.0`` published it to every host that could route to port 8002.
    A deployment that deliberately wants an off-host bind sets
    ``BIND_HOST`` explicitly.
    """
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    cmd = [
        "/opt/aitbc/venv/bin/python",
        "-m",
        "uvicorn",
        "monitoring_service.main:app",
        "--host",
        os.getenv("BIND_HOST", "127.0.0.1"),
        "--port",
        "8002",
        "--log-level",
        log_level,
    ]
    if os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes"):
        cmd.append("--access-log")
    return cmd


def main() -> None:
    # Import AITBC utilities (deferred so importing this module for tests
    # does not require /opt/aitbc to be importable).
    from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR

    # Set up environment using aitbc constants
    os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
    os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
    os.environ["PYTHONPATH"] = f"{REPO_DIR}/apps/monitoring-service/src"
    os.environ["DATA_DIR"] = str(DATA_DIR)
    os.environ["LOG_DIR"] = str(LOG_DIR)

    # Execute the actual service
    exec_cmd = build_cmd()
    os.execvp(exec_cmd[0], exec_cmd)


if __name__ == "__main__":
    main()
