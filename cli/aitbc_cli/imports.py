"""Import setup for AITBC CLI to access coordinator-api services."""

import sys
from pathlib import Path

def ensure_coordinator_api_imports():
    """Ensure coordinator-api src directory is on sys.path."""
    _src_path = Path(__file__).resolve().parent.parent.parent / 'apps' / 'coordinator-api' / 'src'
    if str(_src_path) not in sys.path:
        sys.path.insert(0, str(_src_path))
