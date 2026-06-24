"""Pytest configuration for exchange service tests.

The exchange service uses a flat layout (no src/ package), so
exchange_api.py, database.py, and models.py are top-level modules.
Add the exchange app directory to sys.path so tests can import them.
"""

import sys
from pathlib import Path

_EXCHANGE_DIR = str(Path(__file__).resolve().parent.parent)
if _EXCHANGE_DIR not in sys.path:
    sys.path.insert(0, _EXCHANGE_DIR)
