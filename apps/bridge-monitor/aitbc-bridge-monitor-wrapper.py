#!/usr/bin/env python3
"""Wrapper script for AITBC Bridge Monitor service."""

import os
import sys

# Set up Python path
sys.path.insert(0, "/opt/aitbc")
sys.path.insert(0, "/opt/aitbc/apps/bridge-monitor/src")

# Set environment
os.environ.setdefault("PYTHONPATH", "/opt/aitbc")
os.environ.setdefault("DATA_DIR", "/var/lib/aitbc")

if __name__ == "__main__":
    from bridge_monitor.main import main
    main()
