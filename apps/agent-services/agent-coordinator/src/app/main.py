#!/usr/bin/env python3
"""
Main entry point for AITBC Agent Coordinator Service
"""

import sys
from pathlib import Path

# Add parent directory to path to import coordinator
sys.path.insert(0, str(Path(__file__).parent.parent))

from coordinator import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9001)
