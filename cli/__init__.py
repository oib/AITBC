#!/usr/bin/env python3
"""
AITBC CLI - Main entry point for CLI
Redirects to the core main module
"""

import sys
from pathlib import Path
import importlib.util

# Add CLI directory to Python path
CLI_DIR = Path(__file__).parent
sys.path.insert(0, str(CLI_DIR))

# Import and run the main CLI
_CLI_FILE = CLI_DIR / "aitbc_cli.py"
_CLI_SPEC = importlib.util.spec_from_file_location("aitbc_cli_file", _CLI_FILE)
_CLI_MODULE = importlib.util.module_from_spec(_CLI_SPEC)
_CLI_SPEC.loader.exec_module(_CLI_MODULE)
main = _CLI_MODULE.main

if __name__ == '__main__':
    main()
