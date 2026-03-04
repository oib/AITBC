#!/usr/bin/env python3
"""
Simple FastAPI service for AITBC Modality Optimization (Port 8012)
"""

import sys
import os
sys.path.insert(0, '/opt/aitbc/apps/coordinator-api/src')

import uvicorn
from fastapi import FastAPI

app = FastAPI(title='AITBC Modality Optimization Service', version='1.0.0')

@app.get('/health')
def health():
    return {
        'status': 'ok', 
        'service': 'modality-optimization', 
        'port': 8012,
        'python_version': sys.version.split()[0]
    }

@app.get('/optimization/modality')
def modality_optimization():
    return {
        'optimization_active': True,
        'service': 'modality-optimization',
        'modalities': ['text', 'image', 'audio', 'video'],
        'optimization_level': 'high'
    }

@app.get('/')
def root():
    return {
        'service': 'AITBC Modality Optimization Service',
        'port': 8012,
        'status': 'running',
        'endpoints': ['/health', '/optimization/modality']
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8012))
    uvicorn.run(app, host='0.0.0.0', port=port)
