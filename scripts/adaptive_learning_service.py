#!/usr/bin/env python3
"""
Simple FastAPI service for AITBC Adaptive Learning (Port 8013)
"""

import sys
import os
sys.path.insert(0, '/opt/aitbc/apps/coordinator-api/src')

import uvicorn
from fastapi import FastAPI

app = FastAPI(title='AITBC Adaptive Learning Service', version='1.0.0')

@app.get('/health')
def health():
    return {
        'status': 'ok', 
        'service': 'adaptive-learning', 
        'port': 8013,
        'python_version': sys.version.split()[0]
    }

@app.get('/learning/status')
def learning_status():
    return {
        'learning_active': True,
        'service': 'adaptive-learning',
        'learning_mode': 'online',
        'models_trained': 5,
        'accuracy': 0.95
    }

@app.get('/')
def root():
    return {
        'service': 'AITBC Adaptive Learning Service',
        'port': 8013,
        'status': 'running',
        'endpoints': ['/health', '/learning/status']
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8013))
    uvicorn.run(app, host='0.0.0.0', port=port)
