"""
Services router for specific GPU workloads
"""

from typing import Any, Dict, Union
from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.responses import StreamingResponse

from ..deps import require_client_key
from ..schemas import JobCreate, JobView, JobResult
from ..models.services import (
    ServiceType,
    ServiceRequest,
    ServiceResponse,
    WhisperRequest,
    StableDiffusionRequest,
    LLMRequest,
    FFmpegRequest,
    BlenderRequest,
)
# from ..models.registry import ServiceRegistry, service_registry
from ..services import JobService
from ..storage import SessionDep

router = APIRouter(tags=["services"])


@router.post(
    "/services/{service_type}",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a service-specific job",
    deprecated=True
)
async def submit_service_job(
    service_type: ServiceType,
    request_data: Dict[str, Any],
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
    user_agent: str = Header(None),
) -> ServiceResponse:
    """Submit a job for a specific service type
    
    DEPRECATED: Use /v1/registry/services/{service_id} endpoint instead.
    This endpoint will be removed in version 2.0.
    """
    
    # Add deprecation warning header
    from fastapi import Response
    response = Response()
    response.headers["X-Deprecated"] = "true"
    response.headers["X-Deprecation-Message"] = "Use /v1/registry/services/{service_id} instead"
    
    # Check if service exists in registry
    service = service_registry.get_service(service_type.value)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service {service_type} not found"
        )
    
    # Validate request against service schema
    validation_result = await validate_service_request(service_type.value, request_data)
    if not validation_result["valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request: {', '.join(validation_result['errors'])}"
        )
    
    # Create service request wrapper
    service_request = ServiceRequest(
        service_type=service_type,
        request_data=request_data
    )
    
    # Validate and parse service-specific request
    try:
        typed_request = service_request.get_service_request()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request for {service_type}: {str(e)}"
        )
    
    # Get constraints from service request
    constraints = typed_request.get_constraints()
    
    # Create job with service-specific payload
    job_payload = {
        "service_type": service_type.value,
        "service_request": request_data,
    }
    
    job_create = JobCreate(
        payload=job_payload,
        constraints=constraints,
        ttl_seconds=900  # Default 15 minutes
    )
    
    # Submit job
    service = JobService(session)
    job = service.create_job(client_id, job_create)
    
    return ServiceResponse(
        job_id=job.job_id,
        service_type=service_type,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat()
    )


# Whisper endpoints
@router.post(
    "/services/whisper/transcribe",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Transcribe audio using Whisper"
)
async def whisper_transcribe(
    request: WhisperRequest,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> ServiceResponse:
    """Transcribe audio file using Whisper"""
    
    job_payload = {
        "service_type": ServiceType.WHISPER.value,
        "service_request": request.dict(),
    }
    
    job_create = JobCreate(
        payload=job_payload,
        constraints=request.get_constraints(),
        ttl_seconds=900
    )
    
    service = JobService(session)
    job = service.create_job(client_id, job_create)
    
    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.WHISPER,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat()
    )


@router.post(
    "/services/whisper/translate",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Translate audio using Whisper"
)
async def whisper_translate(
    request: WhisperRequest,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> ServiceResponse:
    """Translate audio file using Whisper"""
    # Force task to be translate
    request.task = "translate"
    
    job_payload = {
        "service_type": ServiceType.WHISPER.value,
        "service_request": request.dict(),
    }
    
    job_create = JobCreate(
        payload=job_payload,
        constraints=request.get_constraints(),
        ttl_seconds=900
    )
    
    service = JobService(session)
    job = service.create_job(client_id, job_create)
    
    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.WHISPER,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat()
    )


# Stable Diffusion endpoints
@router.post(
    "/services/stable-diffusion/generate",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate images using Stable Diffusion"
)
async def stable_diffusion_generate(
    request: StableDiffusionRequest,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> ServiceResponse:
    """Generate images using Stable Diffusion"""
    
    job_payload = {
        "service_type": ServiceType.STABLE_DIFFUSION.value,
        "service_request": request.dict(),
    }
    
    job_create = JobCreate(
        payload=job_payload,
        constraints=request.get_constraints(),
        ttl_seconds=600  # 10 minutes for image generation
    )
    
    service = JobService(session)
    job = service.create_job(client_id, job_create)
    
    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.STABLE_DIFFUSION,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat()
    )


@router.post(
    "/services/stable-diffusion/img2img",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Image-to-image generation"
)
async def stable_diffusion_img2img(
    request: StableDiffusionRequest,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> ServiceResponse:
    """Image-to-image generation using Stable Diffusion"""
    # Add img2img specific parameters
    request_data = request.dict()
    request_data["mode"] = "img2img"
    
    job_payload = {
        "service_type": ServiceType.STABLE_DIFFUSION.value,
        "service_request": request_data,
    }
    
    job_create = JobCreate(
        payload=job_payload,
        constraints=request.get_constraints(),
        ttl_seconds=600
    )
    
    service = JobService(session)
    job = service.create_job(client_id, job_create)
    
    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.STABLE_DIFFUSION,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat()
    )


# LLM Inference endpoints
@router.post(
    "/services/llm/inference",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run LLM inference"
)
async def llm_inference(
    request: LLMRequest,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> ServiceResponse:
    """Run inference on a language model"""
    
    job_payload = {
        "service_type": ServiceType.LLM_INFERENCE.value,
        "service_request": request.dict(),
    }
    
    job_create = JobCreate(
        payload=job_payload,
        constraints=request.get_constraints(),
        ttl_seconds=300  # 5 minutes for text generation
    )
    
    service = JobService(session)
    job = service.create_job(client_id, job_create)
    
    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.LLM_INFERENCE,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat()
    )


@router.post(
    "/services/llm/stream",
    summary="Stream LLM inference"
)
async def llm_stream(
    request: LLMRequest,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
):
    """Stream LLM inference response"""
    # Force streaming mode
    request.stream = True
    
    job_payload = {
        "service_type": ServiceType.LLM_INFERENCE.value,
        "service_request": request.dict(),
    }
    
    job_create = JobCreate(
        payload=job_payload,
        constraints=request.get_constraints(),
        ttl_seconds=300
    )
    
    service = JobService(session)
    job = service.create_job(client_id, job_create)
    
    # Return streaming response
    # This would implement WebSocket or Server-Sent Events
    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.LLM_INFERENCE,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat()
    )


# FFmpeg endpoints
@router.post(
    "/services/ffmpeg/transcode",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Transcode video using FFmpeg"
)
async def ffmpeg_transcode(
    request: FFmpegRequest,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> ServiceResponse:
    """Transcode video using FFmpeg"""
    
    job_payload = {
        "service_type": ServiceType.FFMPEG.value,
        "service_request": request.dict(),
    }
    
    # Adjust TTL based on video length (would need to probe video)
    job_create = JobCreate(
        payload=job_payload,
        constraints=request.get_constraints(),
        ttl_seconds=1800  # 30 minutes for video transcoding
    )
    
    service = JobService(session)
    job = service.create_job(client_id, job_create)
    
    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.FFMPEG,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat()
    )


# Blender endpoints
@router.post(
    "/services/blender/render",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Render using Blender"
)
async def blender_render(
    request: BlenderRequest,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> ServiceResponse:
    """Render scene using Blender"""
    
    job_payload = {
        "service_type": ServiceType.BLENDER.value,
        "service_request": request.dict(),
    }
    
    # Adjust TTL based on frame count
    frame_count = request.frame_end - request.frame_start + 1
    estimated_time = frame_count * 30  # 30 seconds per frame estimate
    ttl_seconds = max(600, estimated_time)  # Minimum 10 minutes
    
    job_create = JobCreate(
        payload=job_payload,
        constraints=request.get_constraints(),
        ttl_seconds=ttl_seconds
    )
    
    service = JobService(session)
    job = service.create_job(client_id, job_create)
    
    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.BLENDER,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat()
    )


# Utility endpoints
@router.get(
    "/services",
    summary="List available services"
)
async def list_services() -> Dict[str, Any]:
    """List all available service types and their capabilities"""
    return {
        "services": [
            {
                "type": ServiceType.WHISPER.value,
                "name": "Whisper Speech Recognition",
                "description": "Transcribe and translate audio files",
                "models": [m.value for m in WhisperModel],
                "constraints": {
                    "gpu": "nvidia",
                    "min_vram_gb": 1,
                }
            },
            {
                "type": ServiceType.STABLE_DIFFUSION.value,
                "name": "Stable Diffusion",
                "description": "Generate images from text prompts",
                "models": [m.value for m in SDModel],
                "constraints": {
                    "gpu": "nvidia",
                    "min_vram_gb": 4,
                }
            },
            {
                "type": ServiceType.LLM_INFERENCE.value,
                "name": "LLM Inference",
                "description": "Run inference on large language models",
                "models": [m.value for m in LLMModel],
                "constraints": {
                    "gpu": "nvidia",
                    "min_vram_gb": 8,
                }
            },
            {
                "type": ServiceType.FFMPEG.value,
                "name": "FFmpeg Video Processing",
                "description": "Transcode and process video files",
                "codecs": [c.value for c in FFmpegCodec],
                "constraints": {
                    "gpu": "any",
                    "min_vram_gb": 0,
                }
            },
            {
                "type": ServiceType.BLENDER.value,
                "name": "Blender Rendering",
                "description": "Render 3D scenes using Blender",
                "engines": [e.value for e in BlenderEngine],
                "constraints": {
                    "gpu": "any",
                    "min_vram_gb": 4,
                }
            },
        ]
    }


@router.get(
    "/services/{service_type}/schema",
    summary="Get service request schema",
    deprecated=True
)
async def get_service_schema(service_type: ServiceType) -> Dict[str, Any]:
    """Get the JSON schema for a specific service type
    
    DEPRECATED: Use /v1/registry/services/{service_id}/schema instead.
    This endpoint will be removed in version 2.0.
    """
    # Get service from registry
    service = service_registry.get_service(service_type.value)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service {service_type} not found"
        )
    
    # Build schema from service definition
    properties = {}
    required = []
    
    for param in service.input_parameters:
        prop = {
            "type": param.type.value,
            "description": param.description
        }
        
        if param.default is not None:
            prop["default"] = param.default
        if param.min_value is not None:
            prop["minimum"] = param.min_value
        if param.max_value is not None:
            prop["maximum"] = param.max_value
        if param.options:
            prop["enum"] = param.options
        if param.validation:
            prop.update(param.validation)
        
        properties[param.name] = prop
        if param.required:
            required.append(param.name)
    
    schema = {
        "type": "object",
        "properties": properties,
        "required": required
    }
    
    return {
        "service_type": service_type.value,
        "schema": schema
    }


async def validate_service_request(service_id: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a service request against the service schema"""
    service = service_registry.get_service(service_id)
    if not service:
        return {"valid": False, "errors": [f"Service {service_id} not found"]}
    
    validation_result = {
        "valid": True,
        "errors": [],
        "warnings": []
    }
    
    # Check required parameters
    provided_params = set(request_data.keys())
    required_params = {p.name for p in service.input_parameters if p.required}
    missing_params = required_params - provided_params
    
    if missing_params:
        validation_result["valid"] = False
        validation_result["errors"].extend([
            f"Missing required parameter: {param}"
            for param in missing_params
        ])
    
    # Validate parameter types and constraints
    for param in service.input_parameters:
        if param.name in request_data:
            value = request_data[param.name]
            
            # Type validation (simplified)
            if param.type == "integer" and not isinstance(value, int):
                validation_result["valid"] = False
                validation_result["errors"].append(
                    f"Parameter {param.name} must be an integer"
                )
            elif param.type == "float" and not isinstance(value, (int, float)):
                validation_result["valid"] = False
                validation_result["errors"].append(
                    f"Parameter {param.name} must be a number"
                )
            elif param.type == "boolean" and not isinstance(value, bool):
                validation_result["valid"] = False
                validation_result["errors"].append(
                    f"Parameter {param.name} must be a boolean"
                )
            elif param.type == "array" and not isinstance(value, list):
                validation_result["valid"] = False
                validation_result["errors"].append(
                    f"Parameter {param.name} must be an array"
                )
            
            # Value constraints
            if param.min_value is not None and value < param.min_value:
                validation_result["valid"] = False
                validation_result["errors"].append(
                    f"Parameter {param.name} must be >= {param.min_value}"
                )
            
            if param.max_value is not None and value > param.max_value:
                validation_result["valid"] = False
                validation_result["errors"].append(
                    f"Parameter {param.name} must be <= {param.max_value}"
                )
            
            # Enum options
            if param.options and value not in param.options:
                validation_result["valid"] = False
                validation_result["errors"].append(
                    f"Parameter {param.name} must be one of: {', '.join(param.options)}"
                )
    
    return validation_result


# Import models for type hints
from ..models.services import (
    WhisperModel,
    SDModel,
    LLMModel,
    FFmpegCodec,
    FFmpegPreset,
    BlenderEngine,
    BlenderFormat,
)
