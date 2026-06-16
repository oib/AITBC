#!/usr/bin/env python3
"""edge service wrapper"""

import os
import sys
from pathlib import Path

# Add AITBC to path
REPO_DIR = Path("/opt/aitbc")
SERVICE_DIR = Path("/opt/aitbc/apps/edge")

sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(SERVICE_DIR))

# Import AITBC utilities
from aitbc import (
    DATA_DIR,
    LOG_DIR,
    REPO_DIR as AITBC_REPO_DIR,
    configure_logging,
    get_logger,
)

# Configure logging
configure_logging(
    log_level="INFO",
    log_dir=LOG_DIR,
    service_name="edge",
)

logger = get_logger(__name__)
logger.info("Starting edge service")

# Execute service
exec_cmd = [
    sys.executable,
    "-m",
    "edge_service.main",
]

logger.info(f"Executing: {' '.join(exec_cmd)}")
os.execvp(exec_cmd[0], exec_cmd)