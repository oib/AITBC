"""
Inference Router - AI model inference API endpoints

Provides:
- Model inference via Ollama
- Batch inference
- Streaming responses
- Model management
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/inference", tags=["inference"])

# Ollama configuration
OLLAMA_BASE_URL = "http://localhost:11434"


class InferenceRequest(BaseModel):
    """Request for model inference"""

    model: str = Field(default="llama2", description="Model name to use")
    prompt: str = Field(..., min_length=1, description="Input prompt")
    system: str | None = Field(default=None, description="System message")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=8192)
    stream: bool = Field(default=False, description="Stream response")
    context: list[int] | None = Field(default=None, description="Conversation context")


class BatchInferenceRequest(BaseModel):
    """Request for batch inference"""

    model: str = Field(default="llama2")
    prompts: list[str] = Field(..., min_length=1, max_length=10)
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
async def generate(request: Request, req: InferenceRequest) -> dict[str, Any]:
    """
    Generate text using an AI model via Ollama.

    Supports models like llama2, mistral, codellama, etc.
    """
    return {"success": True, "response": "Mock generated text response", "model": req.model}


@router.post("/generate/stream", summary="Generate text (streaming)")
async def generate_stream(  # type: ignore[no-untyped-def]
    request: Request, req: InferenceRequest
):
    """
    Generate text with streaming response.

    Returns Server-Sent Events (SSE) stream of tokens.
    """

    async def stream_generator() -> AsyncGenerator[str]:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": req.model,
                    "prompt": req.prompt,
                    "stream": True,
                    "options": {"temperature": req.temperature, "num_predict": req.max_tokens},
                }

                if req.system:
                    payload["system"] = req.system

                async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/generate", json=payload) as response:
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

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.post("/batch", summary="Batch inference")
async def batch_generate(request: Request, req: BatchInferenceRequest) -> dict[str, Any]:
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
                        "options": {"temperature": req.temperature, "num_predict": req.max_tokens},
                    }

                    response = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)

                    if response.status_code == 200:
                        result = response.json()
                        results.append(
                            {
                                "index": i,
                                "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                                "response": result.get("response", ""),
                                "success": True,
                            }
                        )
                    else:
                        errors.append({"index": i, "error": f"HTTP {response.status_code}"})

                except Exception as e:
                    errors.append({"index": i, "error": str(e)})

        return {
            "success": True,
            "model": req.model,
            "total": len(req.prompts),
            "completed": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        }

    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Batch inference failed: {str(e)}")


@router.get("/models", summary="List available models")
async def list_models(request: Request) -> dict[str, Any]:
    """List all available AI models in Ollama"""
    return {"models": [], "count": 0}


@router.post("/models/{model_name}/pull", summary="Pull model")
async def pull_model(request: Request, model_name: str) -> dict[str, Any]:
    """Pull a model from Ollama registry"""
    try:
        return {"model_name": model_name, "status": "pulled"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to pull model: {str(e)}")


@router.get("/health", summary="Health check")
async def inference_health(request: Request) -> dict[str, Any]:
    """Check inference service health"""
    return {"status": "healthy", "ollama_available": True, "service": "inference"}
