#!/usr/bin/env python3
"""
Database initialization script for AITBC Coordinator API
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from app.storage import init_db

if __name__ == "__main__":
    try:
        print("Initializing database...")
        init_db()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Database initialization failed: {e}")
        sys.exit(1)
