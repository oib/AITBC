#!/usr/bin/env python3
"""blockchain-sync service wrapper"""

import os
import sys
from pathlib import Path

# Add AITBC to path
REPO_DIR = Path("/opt/aitbc")
SERVICE_DIR = Path("/opt/aitbc/apps/blockchain-node")

sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(SERVICE_DIR / "src"))

# Import AITBC utilities
from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402

# Configure logging
configure_logging(
    level="INFO",
    service_name="blockchain-sync",
    to_file=True,
)

logger = get_logger(__name__)
logger.info("Starting blockchain-sync service")

# Execute service
exec_cmd = [
    sys.executable,
    "-m",
    "aitbc_chain.sync_cli",
    "--source",
    os.getenv("AITBC_SYNC_SOURCE", "http://127.0.0.1:8202"),
    "--import-url",
    os.getenv("AITBC_SYNC_IMPORT_URL", "http://127.0.0.1:8202"),
]

logger.info(f"Executing: {' '.join(exec_cmd)}")

# Ensure PYTHONPATH is set for the child process
env = os.environ.copy()
env["PYTHONPATH"] = "/opt/aitbc:/opt/aitbc/apps/blockchain-node/src"

os.execvpe(exec_cmd[0], exec_cmd, env)
