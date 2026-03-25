#!/usr/bin/env python3
"""
Simple FastAPI service for AITBC GPU Multimodal (Port 8011)
"""

import sys
import os
sys.path.insert(0, '/opt/aitbc/apps/coordinator-api/src')

import uvicorn
from fastapi import FastAPI

app = FastAPI(title='AITBC GPU Multimodal Service', version='1.0.0')

@app.get('/health')
def health():
    return {
        'status': 'ok', 
        'service': 'gpu-multimodal', 
        'port': 8011,
        'python_version': sys.version.split()[0]
    }

@app.get('/gpu/multimodal')
def gpu_multimodal():
    return {
        'gpu_available': True, 
        'multimodal_capabilities': True,
        'service': 'gpu-multimodal',
        'features': ['text_processing', 'image_processing', 'audio_processing']
    }

@app.get('/')
def root():
    return {
        'service': 'AITBC GPU Multimodal Service',
        'port': 8011,
        'status': 'running',
        'endpoints': ['/health', '/gpu/multimodal']
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8011))
    uvicorn.run(app, host='0.0.0.0', port=port)
