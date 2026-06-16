#!/usr/bin/env python3
"""blockchain-node service wrapper"""

import os
import sys
from pathlib import Path

# Add AITBC to path
REPO_DIR = Path("/opt/aitbc")
SERVICE_DIR = Path("/opt/aitbc/apps/blockchain-node")

sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(SERVICE_DIR))

# Import AITBC utilities
from aitbc import (  # noqa: E402
    LOG_DIR,
    configure_logging,
    get_logger,
)

# Configure logging
configure_logging(
    log_level="INFO",
    log_dir=LOG_DIR,
    service_name="blockchain-node",
)

logger = get_logger(__name__)
logger.info("Starting blockchain-node service")

# Execute service
exec_cmd = [
    sys.executable,
    "-m",
    "aitbc_chain.main",
]

logger.info(f"Executing: {' '.join(exec_cmd)}")
os.execvp(exec_cmd[0], exec_cmd)
