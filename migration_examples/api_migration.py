#!/usr/bin/env python3
"""
API Migration Example

Shows how to migrate FastAPI endpoints to use the new abstraction layer.
"""

# BEFORE (CUDA-specific API)
# from fastapi_cuda_zk_api import ProductionCUDAZKAPI
# 
# cuda_api = ProductionCUDAZKAPI()
# if not cuda_api.initialized:
#     raise HTTPException(status_code=500, detail="CUDA not available")

# AFTER (Backend-agnostic API)
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from gpu_acceleration import GPUAccelerationManager, create_gpu_manager
import numpy as np

app = FastAPI(title="Refactored GPU API")

# Initialize GPU manager (auto-detects best backend)
gpu_manager = create_gpu_manager()

class FieldOperation(BaseModel):
    a: list[int]
    b: list[int]

@app.post("/field/add")
async def field_add(op: FieldOperation):
    """Perform field addition with any available backend."""
    try:
        a = np.array(op.a, dtype=np.uint64)
        b = np.array(op.b, dtype=np.uint64)
        result = gpu_manager.field_add(a, b)
        return {"result": result.tolist()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/backend/info")
async def backend_info():
    """Get current backend information."""
    return gpu_manager.get_backend_info()

@app.get("/performance/metrics")
async def performance_metrics():
    """Get performance metrics."""
    return gpu_manager.get_performance_metrics()
