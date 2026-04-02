#!/usr/bin/env python3
"""
Blockchain HTTP Service Launcher
"""

import os
import sys

# Add production services to path
sys.path.insert(0, '/opt/aitbc/production/services')

# Import blockchain manager and create FastAPI app
from mining_blockchain import MultiChainManager
from fastapi import FastAPI

app = FastAPI(title='AITBC Blockchain HTTP API')

@app.get('/health')
async def health():
    return {'status': 'ok', 'service': 'blockchain-http', 'port': 8005}

@app.get('/info')
async def info():
    manager = MultiChainManager()
    return manager.get_all_chains_info()

@app.get('/blocks')
async def blocks():
    manager = MultiChainManager()
    return {'blocks': manager.get_all_chains_info()}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('BLOCKCHAIN_HTTP_PORT', 8005)),
        log_level='info'
    )
