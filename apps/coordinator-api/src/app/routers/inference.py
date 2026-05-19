"""
Inference Router - AI model inference API endpoints

Provides:
- Model inference via Ollama
- Batch inference
- Streaming responses
- Model management
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, AsyncGenerator
import httpx
import json

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..rate_limiting import rate_limit


router = APIRouter(prefix="/inference", tags=["inference"])

# Ollama configuration
OLLAMA_BASE_URL = "http://localhost:11434"


class InferenceRequest(BaseModel):
    """Request for model inference"""
    model: str = Field(default="llama2", description="Model name to use")
    prompt: str = Field(..., min_length=1, description="Input prompt")
    system: Optional[str] = Field(default=None, description="System message")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=8192)
    stream: bool = Field(default=False, description="Stream response")
    context: Optional[List[int]] = Field(default=None, description="Conversation context")


class BatchInferenceRequest(BaseModel):
    """Request for batch inference"""
    model: str = Field(default="llama2")
    prompts: List[str] = Field(..., min_length=1, max_length=10)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=8192)


class ModelInfo(BaseModel):
    """Model information"""
    name: str
    size: str
    parameter_size: str
    quantization: str
    format: str


@router.post("/generate", summary="Generate text")
@rate_limit(rate=50, per=60)
async def generate(
    request: Request,
    req: InferenceRequest
) -> Dict[str, Any]:
    """
    Generate text using an AI model via Ollama.
    
    Supports models like llama2, mistral, codellama, etc.
    """
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "model": req.model,
                "prompt": req.prompt,
                "stream": False,
                "options": {
                    "temperature": req.temperature,
                    "num_predict": req.max_tokens
                }
            }
            
            if req.system:
                payload["system"] = req.system
            
            if req.context:
                payload["context"] = req.context
            
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Ollama error: {response.text}"
                )
            
            result = response.json()
            
            return {
                "success": True,
                "model": req.model,
                "response": result.get("response", ""),
                "done": result.get("done", True),
                "context": result.get("context"),
                "total_duration": result.get("total_duration"),
                "load_duration": result.get("load_duration"),
                "prompt_eval_count": result.get("prompt_eval_count"),
                "eval_count": result.get("eval_count"),
                "eval_duration": result.get("eval_duration")
            }
            
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Ollama service not available. Please ensure Ollama is running."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference failed: {str(e)}"
        )


@router.post("/generate/stream", summary="Generate text (streaming)")
@rate_limit(rate=30, per=60)
async def generate_stream(
    request: Request,
    req: InferenceRequest
):
    """
    Generate text with streaming response.
    
    Returns Server-Sent Events (SSE) stream of tokens.
    """
    async def stream_generator() -> AsyncGenerator[str, None]:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": req.model,
                    "prompt": req.prompt,
                    "stream": True,
                    "options": {
                        "temperature": req.temperature,
                        "num_predict": req.max_tokens
                    }
                }
                
                if req.system:
                    payload["system"] = req.system
                
                async with client.stream(
                    "POST",
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json=payload
                ) as response:
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                token = data.get("response", "")
                                if token:
                                    yield f"data: {json.dumps({'token': token})}\n\n"
                                
                                if data.get("done"):
                                    yield f"data: {json.dumps({'done': True, 'context': data.get('context')})}\n\n"
                                    break
                            except json.JSONDecodeError:
                                continue
                            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream"
    )


@router.post("/batch", summary="Batch inference")
@rate_limit(rate=10, per=60)
async def batch_generate(
    request: Request,
    req: BatchInferenceRequest
) -> Dict[str, Any]:
    """
    Run inference on multiple prompts in batch.
    """
    results = []
    errors = []
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            for i, prompt in enumerate(req.prompts):
                try:
                    payload = {
                        "model": req.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": req.temperature,
                            "num_predict": req.max_tokens
                        }
                    }
                    
                    response = await client.post(
                        f"{OLLAMA_BASE_URL}/api/generate",
                        json=payload
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        results.append({
                            "index": i,
                            "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                            "response": result.get("response", ""),
                            "success": True
                        })
                    else:
                        errors.append({
                            "index": i,
                            "error": f"HTTP {response.status_code}"
                        })
                        
                except Exception as e:
                    errors.append({
                        "index": i,
                        "error": str(e)
                    })
        
        return {
            "success": True,
            "model": req.model,
            "total": len(req.prompts),
            "completed": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors
        }
        
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Ollama service not available"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch inference failed: {str(e)}"
        )


@router.get("/models", summary="List available models")
@rate_limit(rate=30, per=60)
async def list_models(request: Request) -> Dict[str, Any]:
    """List all available AI models in Ollama"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to fetch models"
                )
            
            data = response.json()
            models = data.get("models", [])
            
            return {
                "models": [
                    {
                        "name": m.get("name"),
                        "size": m.get("size"),
                        "parameter_size": m.get("details", {}).get("parameter_size"),
                        "quantization": m.get("details", {}).get("quantization_level"),
                        "format": m.get("details", {}).get("format"),
                        "family": m.get("details", {}).get("family")
                    }
                    for m in models
                ],
                "count": len(models)
            }
            
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Ollama service not available"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list models: {str(e)}"
        )


@router.post("/models/{model_name}/pull", summary="Pull model")
@rate_limit(rate=5, per=3600)
async def pull_model(
    request: Request,
    model_name: str
) -> Dict[str, Any]:
    """Pull a model from Ollama registry"""
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/pull",
                json={"name": model_name, "stream": False}
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to pull model: {response.text}"
                )
            
            return {
                "success": True,
                "model": model_name,
                "status": "pulled"
            }
            
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Ollama service not available"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pull model: {str(e)}"
        )


@router.get("/health", summary="Inference health check")
async def health_check(request: Request) -> Dict[str, Any]:
    """Check inference service health"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                
                return {
                    "status": "healthy",
                    "ollama_available": True,
                    "models_loaded": len(models),
                    "default_model": "llama2"
                }
            else:
                return {
                    "status": "degraded",
                    "ollama_available": False,
                    "error": f"HTTP {response.status_code}"
                }
                
    except httpx.ConnectError:
        return {
            "status": "unhealthy",
            "ollama_available": False,
            "error": "Ollama service not running"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
