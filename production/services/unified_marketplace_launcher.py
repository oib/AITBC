#!/usr/bin/env python3
"""
Unified Marketplace Service Launcher
"""

import os
import sys

# Add production services to path
sys.path.insert(0, '/opt/aitbc/production/services')

# Import and run the unified marketplace app
from marketplace import app
import uvicorn

# Run the app
uvicorn.run(
    app,
    host='0.0.0.0',
    port=int(os.getenv('MARKETPLACE_PORT', 8002)),
    log_level='info'
)
