#!/usr/bin/env python3
"""wallet service wrapper"""

import os
import sys
from pathlib import Path

# Add AITBC to path
REPO_DIR = Path("/opt/aitbc")
SERVICE_DIR = Path("/opt/aitbc/apps/wallet")

sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(SERVICE_DIR))

# Import AITBC utilities
from aitbc import (  # noqa: E402
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
    service_name="wallet",
)

logger = get_logger(__name__)
logger.info("Starting wallet service")

# Execute service
exec_cmd = [
    sys.executable,
    "-m",
    "app.main",
]

logger.info(f"Executing: {' '.join(exec_cmd)}")
os.execvp(exec_cmd[0], exec_cmd)