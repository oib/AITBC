#!/usr/bin/env python3
"""
FastAPI Integration for Production CUDA ZK Accelerator
Provides REST API endpoints for GPU-accelerated ZK circuit operations
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
import asyncio
import logging
import time
import os
import sys

# Add GPU acceleration path
sys.path.append('/home/oib/windsurf/aitbc/gpu_acceleration')

try:
    from production_cuda_zk_api import ProductionCUDAZKAPI, ZKOperationRequest, ZKOperationResult
    CUDA_AVAILABLE = True
except ImportError as e:
    CUDA_AVAILABLE = False
    print(f"⚠️  CUDA API import failed: {e}")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CUDA_ZK_FASTAPI")

# Initialize FastAPI app
app = FastAPI(
    title="AITBC CUDA ZK Acceleration API",
    description="Production-ready GPU acceleration for zero-knowledge circuit operations",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize CUDA API
cuda_api = ProductionCUDAZKAPI()

# Pydantic models for API
class FieldAdditionRequest(BaseModel):
    num_elements: int = Field(..., ge=1, le=10000000, description="Number of field elements")
    modulus: Optional[List[int]] = Field(default=[0xFFFFFFFFFFFFFFFF] * 4, description="Field modulus")
    optimization_level: str = Field(default="high", pattern="^(low|medium|high)$")
    use_gpu: bool = Field(default=True, description="Use GPU acceleration")

class ConstraintVerificationRequest(BaseModel):
    num_constraints: int = Field(..., ge=1, le=10000000, description="Number of constraints")
    constraints: Optional[List[Dict[str, Any]]] = Field(default=None, description="Constraint data")
    optimization_level: str = Field(default="high", pattern="^(low|medium|high)$")
    use_gpu: bool = Field(default=True, description="Use GPU acceleration")

class WitnessGenerationRequest(BaseModel):
    num_inputs: int = Field(..., ge=1, le=1000000, description="Number of inputs")
    witness_size: int = Field(..., ge=1, le=10000000, description="Witness size")
    optimization_level: str = Field(default="high", pattern="^(low|medium|high)$")
    use_gpu: bool = Field(default=True, description="Use GPU acceleration")

class BenchmarkRequest(BaseModel):
    max_elements: int = Field(default=1000000, ge=1000, le=10000000, description="Maximum elements to benchmark")

class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    execution_time: Optional[float] = None
    gpu_used: Optional[bool] = None
    speedup: Optional[float] = None

# Health check endpoint
@app.get("/health", response_model=Dict[str, Any])
async def health_check():
    """Health check endpoint"""
    try:
        stats = cuda_api.get_performance_statistics()
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "cuda_available": stats["cuda_available"],
            "cuda_initialized": stats["cuda_initialized"],
            "gpu_device": stats["gpu_device"]
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Performance statistics endpoint
@app.get("/stats", response_model=Dict[str, Any])
async def get_performance_stats():
    """Get comprehensive performance statistics"""
    try:
        return cuda_api.get_performance_statistics()
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Field addition endpoint
@app.post("/field-addition", response_model=APIResponse)
async def field_addition(request: FieldAdditionRequest):
    """Perform GPU-accelerated field addition"""
    start_time = time.time()
    
    try:
        zk_request = ZKOperationRequest(
            operation_type="field_addition",
            circuit_data={
                "num_elements": request.num_elements,
                "modulus": request.modulus
            },
            optimization_level=request.optimization_level,
            use_gpu=request.use_gpu
        )
        
        result = await cuda_api.process_zk_operation(zk_request)
        
        return APIResponse(
            success=result.success,
            message="Field addition completed successfully" if result.success else "Field addition failed",
            data=result.result_data,
            execution_time=result.execution_time,
            gpu_used=result.gpu_used,
            speedup=result.speedup
        )
        
    except Exception as e:
        logger.error(f"Field addition failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Constraint verification endpoint
@app.post("/constraint-verification", response_model=APIResponse)
async def constraint_verification(request: ConstraintVerificationRequest):
    """Perform GPU-accelerated constraint verification"""
    start_time = time.time()
    
    try:
        zk_request = ZKOperationRequest(
            operation_type="constraint_verification",
            circuit_data={"num_constraints": request.num_constraints},
            constraints=request.constraints,
            optimization_level=request.optimization_level,
            use_gpu=request.use_gpu
        )
        
        result = await cuda_api.process_zk_operation(zk_request)
        
        return APIResponse(
            success=result.success,
            message="Constraint verification completed successfully" if result.success else "Constraint verification failed",
            data=result.result_data,
            execution_time=result.execution_time,
            gpu_used=result.gpu_used,
            speedup=result.speedup
        )
        
    except Exception as e:
        logger.error(f"Constraint verification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Witness generation endpoint
@app.post("/witness-generation", response_model=APIResponse)
async def witness_generation(request: WitnessGenerationRequest):
    """Perform GPU-accelerated witness generation"""
    start_time = time.time()
    
    try:
        zk_request = ZKOperationRequest(
            operation_type="witness_generation",
            circuit_data={"num_inputs": request.num_inputs},
            witness_data={"num_inputs": request.num_inputs, "witness_size": request.witness_size},
            optimization_level=request.optimization_level,
            use_gpu=request.use_gpu
        )
        
        result = await cuda_api.process_zk_operation(zk_request)
        
        return APIResponse(
            success=result.success,
            message="Witness generation completed successfully" if result.success else "Witness generation failed",
            data=result.result_data,
            execution_time=result.execution_time,
            gpu_used=result.gpu_used,
            speedup=result.speedup
        )
        
    except Exception as e:
        logger.error(f"Witness generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Comprehensive benchmark endpoint
@app.post("/benchmark", response_model=Dict[str, Any])
async def comprehensive_benchmark(request: BenchmarkRequest, background_tasks: BackgroundTasks):
    """Run comprehensive performance benchmark"""
    try:
        logger.info(f"Starting comprehensive benchmark up to {request.max_elements:,} elements")
        
        # Run benchmark asynchronously
        results = await cuda_api.benchmark_comprehensive_performance(request.max_elements)
        
        return {
            "success": True,
            "message": "Comprehensive benchmark completed",
            "data": results,
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Quick benchmark endpoint
@app.get("/quick-benchmark", response_model=Dict[str, Any])
async def quick_benchmark():
    """Run quick performance benchmark"""
    try:
        logger.info("Running quick benchmark")
        
        # Test field addition with 100K elements
        field_request = ZKOperationRequest(
            operation_type="field_addition",
            circuit_data={"num_elements": 100000},
            use_gpu=True
        )
        field_result = await cuda_api.process_zk_operation(field_request)
        
        # Test constraint verification with 50K constraints
        constraint_request = ZKOperationRequest(
            operation_type="constraint_verification",
            circuit_data={"num_constraints": 50000},
            use_gpu=True
        )
        constraint_result = await cuda_api.process_zk_operation(constraint_request)
        
        return {
            "success": True,
            "message": "Quick benchmark completed",
            "data": {
                "field_addition": {
                    "success": field_result.success,
                    "execution_time": field_result.execution_time,
                    "gpu_used": field_result.gpu_used,
                    "speedup": field_result.speedup,
                    "throughput": field_result.throughput
                },
                "constraint_verification": {
                    "success": constraint_result.success,
                    "execution_time": constraint_result.execution_time,
                    "gpu_used": constraint_result.gpu_used,
                    "speedup": constraint_result.speedup,
                    "throughput": constraint_result.throughput
                }
            },
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Quick benchmark failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# GPU information endpoint
@app.get("/gpu-info", response_model=Dict[str, Any])
async def get_gpu_info():
    """Get GPU information and capabilities"""
    try:
        stats = cuda_api.get_performance_statistics()
        
        return {
            "cuda_available": stats["cuda_available"],
            "cuda_initialized": stats["cuda_initialized"],
            "gpu_device": stats["gpu_device"],
            "total_operations": stats["total_operations"],
            "gpu_operations": stats["gpu_operations"],
            "cpu_operations": stats["cpu_operations"],
            "gpu_usage_rate": stats.get("gpu_usage_rate", 0),
            "average_speedup": stats.get("average_speedup", 0),
            "average_execution_time": stats.get("average_execution_time", 0)
        }
        
    except Exception as e:
        logger.error(f"Failed to get GPU info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Reset statistics endpoint
@app.post("/reset-stats", response_model=Dict[str, str])
async def reset_statistics():
    """Reset performance statistics"""
    try:
        # Reset the statistics in the CUDA API
        cuda_api.operation_stats = {
            "total_operations": 0,
            "gpu_operations": 0,
            "cpu_operations": 0,
            "total_time": 0.0,
            "average_speedup": 0.0
        }
        
        return {"success": True, "message": "Statistics reset successfully"}
        
    except Exception as e:
        logger.error(f"Failed to reset stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Root endpoint
@app.get("/", response_model=Dict[str, Any])
async def root():
    """Root endpoint with API information"""
    return {
        "name": "AITBC CUDA ZK Acceleration API",
        "version": "1.0.0",
        "description": "Production-ready GPU acceleration for zero-knowledge circuit operations",
        "endpoints": {
            "health": "/health",
            "stats": "/stats",
            "gpu_info": "/gpu-info",
            "field_addition": "/field-addition",
            "constraint_verification": "/constraint-verification",
            "witness_generation": "/witness-generation",
            "quick_benchmark": "/quick-benchmark",
            "comprehensive_benchmark": "/benchmark",
            "docs": "/docs",
            "redoc": "/redoc"
        },
        "cuda_available": CUDA_AVAILABLE,
        "timestamp": time.time()
    }

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting AITBC CUDA ZK Acceleration API Server")
    print("=" * 50)
    print(f"   CUDA Available: {CUDA_AVAILABLE}")
    print(f"   API Documentation: http://localhost:8001/docs")
    print(f"   ReDoc Documentation: http://localhost:8001/redoc")
    print("=" * 50)
    
    uvicorn.run(
        "fastapi_cuda_zk_api:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )
