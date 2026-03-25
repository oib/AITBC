#!/usr/bin/env python3
"""
Simple FastAPI service for AITBC Multimodal GPU (Port 8010)
"""

import sys
import os
sys.path.insert(0, '/opt/aitbc/apps/coordinator-api/src')

import uvicorn
from fastapi import FastAPI

app = FastAPI(title='AITBC Multimodal GPU Service', version='1.0.0')

@app.get('/health')
def health():
    return {
        'status': 'ok', 
        'service': 'gpu-multimodal', 
        'port': 8010,
        'python_version': sys.version.split()[0]
    }

@app.get('/gpu/status')
def gpu_status():
    return {
        'gpu_available': True, 
        'cuda_available': False, 
        'service': 'multimodal-gpu',
        'capabilities': ['multimodal_processing', 'gpu_acceleration']
    }

@app.get('/')
def root():
    return {
        'service': 'AITBC Multimodal GPU Service',
        'port': 8010,
        'status': 'running',
        'endpoints': ['/health', '/gpu/status']
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8010))
    uvicorn.run(app, host='0.0.0.0', port=port)
