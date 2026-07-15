"""
Services router for specific GPU workloads
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from aitbc.rate_limiting import rate_limit

from ....auth import ClientDep
from ....models.services import (
    BlenderEngine,
    BlenderRequest,
    FFmpegCodec,
    FFmpegRequest,
    LLMModel,
    LLMRequest,
    SDModel,
    ServiceResponse,
    ServiceType,
    StableDiffusionRequest,
    WhisperModel,
    WhisperRequest,
    WhisperTask,
)
from ....schemas import JobCreate
from ....services import JobService
from ....storage import get_session


router = APIRouter(tags=["services"])


# Whisper endpoints
@router.post(
    "/services/whisper/transcribe",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Transcribe audio using Whisper",
)
@rate_limit(rate=20, per=60)
async def whisper_transcribe(
    request: Request,
    whisper_request: WhisperRequest,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> ServiceResponse:
    """Transcribe audio file using Whisper"""

    job_payload = {
        "service_type": ServiceType.WHISPER.value,
        "service_request": whisper_request.model_dump(),
    }

    job_create = JobCreate(payload=job_payload, constraints=whisper_request.get_constraints(), ttl_seconds=900)

    service = JobService(session)
    job = service.create_job(user["sub"], job_create)

    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.WHISPER,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat(),
    )


@router.post(
    "/services/whisper/translate",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Translate audio using Whisper",
)
@rate_limit(rate=20, per=60)
async def whisper_translate(
    request: Request,
    whisper_request: WhisperRequest,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> ServiceResponse:
    """Translate audio file using Whisper"""
    # Force task to be translate
    whisper_request.task = WhisperTask.TRANSLATE

    job_payload = {
        "service_type": ServiceType.WHISPER.value,
        "service_request": whisper_request.model_dump(),
    }

    job_create = JobCreate(payload=job_payload, constraints=whisper_request.get_constraints(), ttl_seconds=900)

    service = JobService(session)
    job = service.create_job(user["sub"], job_create)

    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.WHISPER,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat(),
    )


# Stable Diffusion endpoints
@router.post(
    "/services/stable-diffusion/generate",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate images using Stable Diffusion",
)
@rate_limit(rate=20, per=60)
async def stable_diffusion_generate(
    request: Request,
    sd_request: StableDiffusionRequest,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> ServiceResponse:
    """Generate images using Stable Diffusion"""

    job_payload = {
        "service_type": ServiceType.STABLE_DIFFUSION.value,
        "service_request": sd_request.model_dump(),
    }

    job_create = JobCreate(
        payload=job_payload,
        constraints=sd_request.get_constraints(),
        ttl_seconds=600,  # 10 minutes for image generation
    )

    service = JobService(session)
    job = service.create_job(user["sub"], job_create)

    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.STABLE_DIFFUSION,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat(),
    )


@router.post(
    "/services/stable-diffusion/img2img",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Image-to-image generation",
)
@rate_limit(rate=20, per=60)
async def stable_diffusion_img2img(
    request: Request,
    sd_request: StableDiffusionRequest,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> ServiceResponse:
    """Image-to-image generation using Stable Diffusion"""
    # Add img2img specific parameters
    request_data = sd_request.model_dump()
    request_data["mode"] = "img2img"

    job_payload = {
        "service_type": ServiceType.STABLE_DIFFUSION.value,
        "service_request": request_data,
    }

    job_create = JobCreate(payload=job_payload, constraints=sd_request.get_constraints(), ttl_seconds=600)

    service = JobService(session)
    job = service.create_job(user["sub"], job_create)

    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.STABLE_DIFFUSION,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat(),
    )


# LLM Inference endpoints
@router.post(
    "/services/llm/inference", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED, summary="Run LLM inference"
)
@rate_limit(rate=20, per=60)
async def llm_inference(
    request: Request,
    llm_request: LLMRequest,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> ServiceResponse:
    """Run inference on a language model"""

    job_payload = {
        "service_type": ServiceType.LLM_INFERENCE.value,
        "service_request": llm_request.model_dump(),
    }

    job_create = JobCreate(
        payload=job_payload,
        constraints=llm_request.get_constraints(),
        ttl_seconds=300,  # 5 minutes for text generation
    )

    service = JobService(session)
    job = service.create_job(user["sub"], job_create)

    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.LLM_INFERENCE,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat(),
    )


@router.post("/services/llm/stream", summary="Stream LLM inference")
@rate_limit(rate=20, per=60)
async def llm_stream(
    request: Request,
    llm_request: LLMRequest,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> ServiceResponse:
    """Stream LLM inference response"""
    # Force streaming mode
    llm_request.stream = True

    job_payload = {
        "service_type": ServiceType.LLM_INFERENCE.value,
        "service_request": llm_request.model_dump(),
    }

    job_create = JobCreate(payload=job_payload, constraints=llm_request.get_constraints(), ttl_seconds=300)

    service = JobService(session)
    job = service.create_job(user["sub"], job_create)

    # Return streaming response
    # This would implement WebSocket or Server-Sent Events
    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.LLM_INFERENCE,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat(),
    )


# FFmpeg endpoints
@router.post(
    "/services/ffmpeg/transcode",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Transcode video using FFmpeg",
)
@rate_limit(rate=20, per=60)
async def ffmpeg_transcode(
    request: Request,
    ffmpeg_request: FFmpegRequest,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> ServiceResponse:
    """Transcode video using FFmpeg"""

    job_payload = {
        "service_type": ServiceType.FFMPEG.value,
        "service_request": ffmpeg_request.model_dump(),
    }

    # Adjust TTL based on video length (would need to probe video)
    job_create = JobCreate(
        payload=job_payload,
        constraints=ffmpeg_request.get_constraints(),
        ttl_seconds=1800,  # 30 minutes for video transcoding
    )

    service = JobService(session)
    job = service.create_job(user["sub"], job_create)

    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.FFMPEG,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat(),
    )


# Blender endpoints
@router.post(
    "/services/blender/render",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Render using Blender",
)
@rate_limit(rate=20, per=60)
async def blender_render(
    request: Request,
    blender_request: BlenderRequest,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> ServiceResponse:
    """Render scene using Blender"""

    job_payload = {
        "service_type": ServiceType.BLENDER.value,
        "service_request": blender_request.model_dump(),
    }

    # Adjust TTL based on frame count
    frame_count = blender_request.frame_end - blender_request.frame_start + 1
    estimated_time = frame_count * 30  # 30 seconds per frame estimate
    ttl_seconds = max(600, estimated_time)  # Minimum 10 minutes

    job_create = JobCreate(payload=job_payload, constraints=blender_request.get_constraints(), ttl_seconds=ttl_seconds)

    service = JobService(session)
    job = service.create_job(user["sub"], job_create)

    return ServiceResponse(
        job_id=job.job_id,
        service_type=ServiceType.BLENDER,
        status=job.state.value,
        estimated_completion=job.expires_at.isoformat(),
    )


# Utility endpoints
@router.get("/services", summary="List available services")
@rate_limit(rate=200, per=60)
async def list_services(request: Request) -> dict[str, Any]:
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
                },
            },
            {
                "type": ServiceType.STABLE_DIFFUSION.value,
                "name": "Stable Diffusion",
                "description": "Generate images from text prompts",
                "models": [m.value for m in SDModel],
                "constraints": {
                    "gpu": "nvidia",
                    "min_vram_gb": 4,
                },
            },
            {
                "type": ServiceType.LLM_INFERENCE.value,
                "name": "LLM Inference",
                "description": "Run inference on large language models",
                "models": [m.value for m in LLMModel],
                "constraints": {
                    "gpu": "nvidia",
                    "min_vram_gb": 8,
                },
            },
            {
                "type": ServiceType.FFMPEG.value,
                "name": "FFmpeg Video Processing",
                "description": "Transcode and process video files",
                "codecs": [c.value for c in FFmpegCodec],
                "constraints": {
                    "gpu": "any",
                    "min_vram_gb": 0,
                },
            },
            {
                "type": ServiceType.BLENDER.value,
                "name": "Blender Rendering",
                "description": "Render 3D scenes using Blender",
                "engines": [e.value for e in BlenderEngine],
                "constraints": {
                    "gpu": "any",
                    "min_vram_gb": 4,
                },
            },
        ]
    }
