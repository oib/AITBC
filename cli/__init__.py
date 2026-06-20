#!/usr/bin/env python3
"""
AITBC CLI - Main entry point for CLI
Redirects to the core main module
"""

import sys
from pathlib import Path

# Add CLI directory to Python path
CLI_DIR = Path(__file__).parent
sys.path.insert(0, str(CLI_DIR))

if __name__ == "__main__":
    from aitbc_cli.core.main import main  # noqa: E402

    main()
