"""Pytest configuration for exchange service tests.

The exchange service runs via ``apps.exchange.simple_exchange.server``.
Tests import from ``apps.exchange.simple_exchange.*`` modules.
"""

import sys
from pathlib import Path

# Ensure the repo root is on sys.path so `apps.exchange.simple_exchange.*` imports work
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
