"""Miner test configuration.

production_miner validates environment variables at import time, so these must be
set before the module is first imported by the test files.
"""

import os

os.environ.setdefault("MINER_ID", "test-miner")
os.environ.setdefault("MINER_AUTH_TOKEN", "test-auth-token")
