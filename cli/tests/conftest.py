"""Pytest configuration for CLI tests.

Ensures both the CLI directory and the project root are on sys.path so
that imports like `aitbc_cli.commands.explorer` and `aitbc.aitbc_logging`
resolve correctly.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CLI_DIR = Path(__file__).resolve().parent.parent

for p in (str(PROJECT_ROOT), str(CLI_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)
