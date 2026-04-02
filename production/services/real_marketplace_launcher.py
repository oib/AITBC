#!/usr/bin/env python3
"""
Real Marketplace Service Launcher
"""

import os
import sys

# Add production services to path
sys.path.insert(0, '/opt/aitbc/production/services')

# Import and run the real marketplace app
from real_marketplace import app
import uvicorn

# Run the app
uvicorn.run(
    app,
    host='0.0.0.0',
    port=int(os.getenv('REAL_MARKETPLACE_PORT', 8009)),
    log_level='info'
)
