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

# Import and run the main CLI
from core.main import main

if __name__ == '__main__':
    main()
