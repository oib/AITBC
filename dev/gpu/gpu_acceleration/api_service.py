"""
Refactored FastAPI GPU Acceleration Service

Uses the new abstraction layer for backend-agnostic GPU acceleration.
"""

import logging

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .gpu_manager import create_gpu_manager

app = FastAPI(title="AITBC GPU Acceleration API")
logger = logging.getLogger(__name__)

# Initialize GPU manager
gpu_manager = create_gpu_manager()


class FieldOperation(BaseModel):
    a: list[int]
    b: list[int]


class MultiScalarOperation(BaseModel):
    scalars: list[list[int]]
    points: list[list[int]]


@app.post("/field/add")
async def field_add(op: FieldOperation):
    """Perform field addition."""
    try:
        a = np.array(op.a, dtype=np.uint64)
        b = np.array(op.b, dtype=np.uint64)
        result = gpu_manager.field_add(a, b)
        return {"result": result.tolist()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/field/mul")
async def field_mul(op: FieldOperation):
    """Perform field multiplication."""
    try:
        a = np.array(op.a, dtype=np.uint64)
        b = np.array(op.b, dtype=np.uint64)
        result = gpu_manager.field_mul(a, b)
        return {"result": result.tolist()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/backend/info")
async def backend_info():
    """Get backend information."""
    return gpu_manager.get_backend_info()


@app.get("/performance/metrics")
async def performance_metrics():
    """Get performance metrics."""
    return gpu_manager.get_performance_metrics()
