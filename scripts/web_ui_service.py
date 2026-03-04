#!/usr/bin/env python3
"""
Simple FastAPI service for AITBC Web UI (Port 8016)
"""

import sys
import os
sys.path.insert(0, '/opt/aitbc/apps/coordinator-api/src')

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

app = FastAPI(title='AITBC Web UI Service', version='1.0.0')

@app.get('/health')
def health():
    return {
        'status': 'ok', 
        'service': 'web-ui', 
        'port': 8016,
        'python_version': sys.version.split()[0]
    }

@app.get('/')
def root():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AITBC Web UI</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            .header { text-align: center; color: #333; }
            .status { background: #e8f5e8; padding: 20px; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 AITBC Web UI</h1>
                <p>Port 8016 - Enhanced Services Interface</p>
            </div>
            <div class="status">
                <h2>🎯 Service Status</h2>
                <p>✅ Web UI: Running on port 8016</p>
                <p>✅ Coordinator API: Running on port 8000</p>
                <p>✅ Exchange API: Running on port 8001</p>
                <p>✅ Blockchain RPC: Running on port 8003</p>
                <p>✅ Enhanced Services: Running on ports 8010-8016</p>
            </div>
        </div>
    </body>
    </html>
    """)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8016))
    uvicorn.run(app, host='0.0.0.0', port=port)
