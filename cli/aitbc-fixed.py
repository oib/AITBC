#!/usr/bin/env python3
"""
AITBC CLI - Fixed entry point
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the CLI
from core.main import cli

if __name__ == "__main__":
    cli()
