from sqlalchemy.orm import Session
from typing import Annotated
"""
Advanced AI Service - Phase 5.2 Implementation
Integrates enhanced RL, multi-modal fusion, and GPU optimization
Port: 8009
"""

import asyncio
import torch
import torch.nn as nn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional, Union
import numpy as np
from datetime import datetime
import uuid
import json
import logging
logger = logging.getLogger(__name__)

from .advanced_reinforcement_learning import AdvancedReinforcementLearningEngine
from .multi_modal_fusion import MultiModalFusionEngine
from .gpu_multimodal import GPUAcceleratedMultiModal
from .advanced_learning import AdvancedLearningService
from ..storage import get_session



# Pydantic models for API
class RLTrainingRequest(BaseModel):
    agent_id: str = Field(..., description="Unique agent identifier")
    environment_type: str = Field(..., description="Environment type for training")
    algorithm: str = Field(default="ppo", description="RL algorithm to use")
    training_config: Optional[Dict[str, Any]] = Field(default=None, description="Training configuration")
    training_data: List[Dict[str, Any]] = Field(..., description="Training data")

class MultiModalFusionRequest(BaseModel):
    modal_data: Dict[str, Any] = Field(..., description="Multi-modal input data")
    fusion_strategy: str = Field(default="transformer_fusion", description="Fusion strategy")
    fusion_config: Optional[Dict[str, Any]] = Field(default=None, description="Fusion configuration")

class GPUOptimizationRequest(BaseModel):
    modality_features: Dict[str, np.ndarray] = Field(..., description="Features for each modality")
    attention_config: Optional[Dict[str, Any]] = Field(default=None, description="Attention configuration")

class AdvancedAIRequest(BaseModel):
    request_type: str = Field(..., description="Type of AI processing")
    input_data: Dict[str, Any] = Field(..., description="Input data for processing")
    config: Optional[Dict[str, Any]] = Field(default=None, description="Processing configuration")

class PerformanceMetrics(BaseModel):
    processing_time_ms: float
    gpu_utilization: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    accuracy: Optional[float] = None
    model_complexity: Optional[int] = None

# FastAPI application
app = FastAPI(
    title="Advanced AI Service",
    description="Enhanced AI capabilities with RL, multi-modal fusion, and GPU optimization",
    version="5.2.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service instances
rl_engine = AdvancedReinforcementLearningEngine()
fusion_engine = MultiModalFusionEngine()
advanced_learning = AdvancedLearningService()

@app.on_event("startup")
async def startup_event():
    """Initialize the Advanced AI Service"""
    logger.info("Starting Advanced AI Service on port 8009")
    
    # Check GPU availability
    if torch.cuda.is_available():
        logger.info(f"CUDA available: {torch.cuda.get_device_name()}")
        logger.info(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        logger.warning("CUDA not available, using CPU fallback")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Advanced AI Service",
        "version": "5.2.0",
        "port": 8009,
        "capabilities": [
            "Advanced Reinforcement Learning",
            "Multi-Modal Fusion",
            "GPU-Accelerated Processing",
            "Meta-Learning",
            "Performance Optimization"
        ],
        "status": "operational"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "gpu_available": torch.cuda.is_available(),
        "services": {
            "rl_engine": "operational",
            "fusion_engine": "operational", 
            "advanced_learning": "operational"
        }
    }

@app.post("/rl/train")
async def train_rl_agent(request: RLTrainingRequest, background_tasks: BackgroundTasks):
    """Train a reinforcement learning agent"""
    
    try:
        # Start training in background
        training_id = str(uuid.uuid4())
        
        background_tasks.add_task(
            _train_rl_agent_background,
            training_id,
            request.agent_id,
            request.environment_type,
            request.algorithm,
            request.training_config,
            request.training_data
        )
        
        return {
            "training_id": training_id,
            "status": "training_started",
            "agent_id": request.agent_id,
            "algorithm": request.algorithm,
            "environment": request.environment_type
        }
        
    except Exception as e:
        logger.error(f"RL training failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def _train_rl_agent_background(
    training_id: str,
    agent_id: str,
    environment_type: str,
    algorithm: str,
    training_config: Optional[Dict[str, Any]],
    training_data: List[Dict[str, Any]]
):
    """Background task for RL training"""
    
    try:
        # Simulate database session
        from sqlmodel import Session
        from ..database import get_session
        
        async with get_session() as session:
            result = await rl_engine.create_rl_agent(
                session=session,
                agent_id=agent_id,
                environment_type=environment_type,
                algorithm=algorithm,
                training_config=training_config
            )
            
            # Store training result (in production, save to database)
            logger.info(f"RL training completed: {training_id}")
            
    except Exception as e:
        logger.error(f"Background RL training failed: {e}")

@app.post("/fusion/process")
async def process_multi_modal_fusion(request: MultiModalFusionRequest):
    """Process multi-modal fusion"""
    
    try:
        start_time = datetime.utcnow()
        
        # Simulate database session
        from sqlmodel import Session
        from ..database import get_session
        
        async with get_session() as session:
            if request.fusion_strategy == "transformer_fusion":
                result = await fusion_engine.transformer_fusion(
                    session=session,
                    modal_data=request.modal_data,
                    fusion_config=request.fusion_config
                )
            elif request.fusion_strategy == "cross_modal_attention":
                result = await fusion_engine.cross_modal_attention(
                    session=session,
                    modal_data=request.modal_data,
                    fusion_config=request.fusion_config
                )
            else:
                result = await fusion_engine.adaptive_fusion_selection(
                    modal_data=request.modal_data,
                    performance_requirements=request.fusion_config or {}
                )
        
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return {
            "fusion_result": result,
            "processing_time_ms": processing_time,
            "strategy_used": request.fusion_strategy,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Multi-modal fusion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/gpu/optimize")
async def optimize_gpu_processing(request: GPUOptimizationRequest):
    """Perform GPU-optimized processing"""
    
    try:
        # Simulate database session
        from sqlmodel import Session
        from ..database import get_session
        
        async with get_session() as session:
            gpu_processor = GPUAcceleratedMultiModal(session)
            
            result = await gpu_processor.accelerated_cross_modal_attention(
                modality_features=request.modality_features,
                attention_config=request.attention_config
            )
        
        return {
            "optimization_result": result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"GPU optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process")
async def advanced_ai_processing(request: AdvancedAIRequest):
    """Unified advanced AI processing endpoint"""
    
    try:
        start_time = datetime.utcnow()
        
        if request.request_type == "rl_training":
            # Convert to RL training request
            return await _handle_rl_training(request.input_data, request.config)
        
        elif request.request_type == "multi_modal_fusion":
            # Convert to fusion request
            return await _handle_fusion_processing(request.input_data, request.config)
        
        elif request.request_type == "gpu_optimization":
            # Convert to GPU optimization request
            return await _handle_gpu_optimization(request.input_data, request.config)
        
        elif request.request_type == "meta_learning":
            # Handle meta-learning
            return await _handle_meta_learning(request.input_data, request.config)
        
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported request type: {request.request_type}")
        
    except Exception as e:
        logger.error(f"Advanced AI processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def _handle_rl_training(input_data: Dict[str, Any], config: Optional[Dict[str, Any]]):
    """Handle RL training request"""
    # Implementation for unified RL training
    return {"status": "rl_training_initiated", "details": input_data}

async def _handle_fusion_processing(input_data: Dict[str, Any], config: Optional[Dict[str, Any]]):
    """Handle fusion processing request"""
    # Implementation for unified fusion processing
    return {"status": "fusion_processing_initiated", "details": input_data}

async def _handle_gpu_optimization(input_data: Dict[str, Any], config: Optional[Dict[str, Any]]):
    """Handle GPU optimization request"""
    # Implementation for unified GPU optimization
    return {"status": "gpu_optimization_initiated", "details": input_data}

async def _handle_meta_learning(input_data: Dict[str, Any], config: Optional[Dict[str, Any]]):
    """Handle meta-learning request"""
    # Implementation for meta-learning
    return {"status": "meta_learning_initiated", "details": input_data}

@app.get("/metrics")
async def get_performance_metrics():
    """Get service performance metrics"""
    
    try:
        # GPU metrics
        gpu_metrics = {}
        if torch.cuda.is_available():
            gpu_metrics = {
                "gpu_available": True,
                "gpu_name": torch.cuda.get_device_name(),
                "gpu_memory_total_gb": torch.cuda.get_device_properties(0).total_memory / 1e9,
                "gpu_memory_allocated_gb": torch.cuda.memory_allocated() / 1e9,
                "gpu_memory_cached_gb": torch.cuda.memory_reserved() / 1e9
            }
        else:
            gpu_metrics = {"gpu_available": False}
        
        # Service metrics
        service_metrics = {
            "rl_models_trained": len(rl_engine.agents),
            "fusion_models_created": len(fusion_engine.fusion_models),
            "gpu_utilization": gpu_metrics.get("gpu_memory_allocated_gb", 0) / gpu_metrics.get("gpu_memory_total_gb", 1) * 100 if gpu_metrics.get("gpu_available") else 0
        }
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "gpu_metrics": gpu_metrics,
            "service_metrics": service_metrics,
            "system_health": "operational"
        }
        
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/models")
async def list_available_models():
    """List available trained models"""
    
    try:
        rl_models = list(rl_engine.agents.keys())
        fusion_models = list(fusion_engine.fusion_models.keys())
        
        return {
            "rl_models": rl_models,
            "fusion_models": fusion_models,
            "total_models": len(rl_models) + len(fusion_models)
        }
        
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/models/{model_id}")
async def delete_model(model_id: str):
    """Delete a trained model"""
    
    try:
        # Try to delete from RL models
        if model_id in rl_engine.agents:
            del rl_engine.agents[model_id]
            return {"status": "model_deleted", "model_id": model_id, "type": "rl"}
        
        # Try to delete from fusion models
        if model_id in fusion_engine.fusion_models:
            del fusion_engine.fusion_models[model_id]
            return {"status": "model_deleted", "model_id": model_id, "type": "fusion"}
        
        raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")
        
    except Exception as e:
        logger.error(f"Failed to delete model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)
