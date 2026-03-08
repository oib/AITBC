#!/usr/bin/env python3
"""
Initialize database for AITBC Coordinator API
"""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from app.database import init_db

async def main():
    await init_db()
    print("Database initialized successfully")

if __name__ == "__main__":
    asyncio.run(main())
