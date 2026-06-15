#!/usr/bin/env python3
"""Wrapper script for AITBC Bridge Monitor service."""

import os

# Set environment
os.environ.setdefault("PYTHONPATH", "/opt/aitbc")
os.environ.setdefault("DATA_DIR", "/var/lib/aitbc")

if __name__ == "__main__":
    from bridge_monitor.main import main

    main()
