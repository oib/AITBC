"""
Service configuration router for pool hub
"""

from typing import Dict, List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db, get_miner_id
from ..models import Miner, ServiceConfig, ServiceType
from ..schemas import ServiceConfigCreate, ServiceConfigUpdate, ServiceConfigResponse

router = APIRouter(prefix="/services", tags=["services"])


@router.get("/", response_model=List[ServiceConfigResponse])
async def list_service_configs(
    db: Session = Depends(get_db),
    miner_id: str = Depends(get_miner_id)
) -> List[ServiceConfigResponse]:
    """List all service configurations for the miner"""
    stmt = select(ServiceConfig).where(ServiceConfig.miner_id == miner_id)
    configs = db.execute(stmt).scalars().all()
    
    return [ServiceConfigResponse.from_orm(config) for config in configs]


@router.get("/{service_type}", response_model=ServiceConfigResponse)
async def get_service_config(
    service_type: str,
    db: Session = Depends(get_db),
    miner_id: str = Depends(get_miner_id)
) -> ServiceConfigResponse:
    """Get configuration for a specific service"""
    stmt = select(ServiceConfig).where(
        ServiceConfig.miner_id == miner_id,
        ServiceConfig.service_type == service_type
    )
    config = db.execute(stmt).scalar_one_or_none()
    
    if not config:
        # Return default config
        return ServiceConfigResponse(
            service_type=service_type,
            enabled=False,
            config={},
            pricing={},
            capabilities=[],
            max_concurrent=1
        )
    
    return ServiceConfigResponse.from_orm(config)


@router.post("/{service_type}", response_model=ServiceConfigResponse)
async def create_or_update_service_config(
    service_type: str,
    config_data: ServiceConfigCreate,
    db: Session = Depends(get_db),
    miner_id: str = Depends(get_miner_id)
) -> ServiceConfigResponse:
    """Create or update service configuration"""
    # Validate service type
    if service_type not in [s.value for s in ServiceType]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid service type: {service_type}"
        )
    
    # Check if config exists
    stmt = select(ServiceConfig).where(
        ServiceConfig.miner_id == miner_id,
        ServiceConfig.service_type == service_type
    )
    existing = db.execute(stmt).scalar_one_or_none()
    
    if existing:
        # Update existing
        existing.enabled = config_data.enabled
        existing.config = config_data.config
        existing.pricing = config_data.pricing
        existing.capabilities = config_data.capabilities
        existing.max_concurrent = config_data.max_concurrent
        db.commit()
        db.refresh(existing)
        config = existing
    else:
        # Create new
        config = ServiceConfig(
            miner_id=miner_id,
            service_type=service_type,
            enabled=config_data.enabled,
            config=config_data.config,
            pricing=config_data.pricing,
            capabilities=config_data.capabilities,
            max_concurrent=config_data.max_concurrent
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    
    return ServiceConfigResponse.from_orm(config)


@router.patch("/{service_type}", response_model=ServiceConfigResponse)
async def patch_service_config(
    service_type: str,
    config_data: ServiceConfigUpdate,
    db: Session = Depends(get_db),
    miner_id: str = Depends(get_miner_id)
) -> ServiceConfigResponse:
    """Partially update service configuration"""
    stmt = select(ServiceConfig).where(
        ServiceConfig.miner_id == miner_id,
        ServiceConfig.service_type == service_type
    )
    config = db.execute(stmt).scalar_one_or_none()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service configuration not found"
        )
    
    # Update only provided fields
    if config_data.enabled is not None:
        config.enabled = config_data.enabled
    if config_data.config is not None:
        config.config = config_data.config
    if config_data.pricing is not None:
        config.pricing = config_data.pricing
    if config_data.capabilities is not None:
        config.capabilities = config_data.capabilities
    if config_data.max_concurrent is not None:
        config.max_concurrent = config_data.max_concurrent
    
    db.commit()
    db.refresh(config)
    
    return ServiceConfigResponse.from_orm(config)


@router.delete("/{service_type}")
async def delete_service_config(
    service_type: str,
    db: Session = Depends(get_db),
    miner_id: str = Depends(get_miner_id)
) -> Dict[str, Any]:
    """Delete service configuration"""
    stmt = select(ServiceConfig).where(
        ServiceConfig.miner_id == miner_id,
        ServiceConfig.service_type == service_type
    )
    config = db.execute(stmt).scalar_one_or_none()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service configuration not found"
        )
    
    db.delete(config)
    db.commit()
    
    return {"message": f"Service configuration for {service_type} deleted"}


@router.get("/templates/{service_type}")
async def get_service_template(service_type: str) -> Dict[str, Any]:
    """Get default configuration template for a service"""
    templates = {
        "whisper": {
            "config": {
                "models": ["tiny", "base", "small", "medium", "large"],
                "default_model": "base",
                "max_file_size_mb": 500,
                "supported_formats": ["mp3", "wav", "m4a", "flac"]
            },
            "pricing": {
                "per_minute": 0.001,
                "min_charge": 0.01
            },
            "capabilities": ["transcribe", "translate"],
            "max_concurrent": 2
        },
        "stable_diffusion": {
            "config": {
                "models": ["stable-diffusion-1.5", "stable-diffusion-2.1", "sdxl"],
                "default_model": "stable-diffusion-1.5",
                "max_resolution": "1024x1024",
                "max_images_per_request": 4
            },
            "pricing": {
                "per_image": 0.01,
                "per_step": 0.001
            },
            "capabilities": ["txt2img", "img2img"],
            "max_concurrent": 1
        },
        "llm_inference": {
            "config": {
                "models": ["llama-7b", "llama-13b", "mistral-7b", "mixtral-8x7b"],
                "default_model": "llama-7b",
                "max_tokens": 4096,
                "context_length": 4096
            },
            "pricing": {
                "per_1k_tokens": 0.001,
                "min_charge": 0.01
            },
            "capabilities": ["generate", "stream"],
            "max_concurrent": 2
        },
        "ffmpeg": {
            "config": {
                "supported_codecs": ["h264", "h265", "vp9"],
                "max_resolution": "4K",
                "max_file_size_gb": 10,
                "gpu_acceleration": True
            },
            "pricing": {
                "per_minute": 0.005,
                "per_gb": 0.01
            },
            "capabilities": ["transcode", "resize", "compress"],
            "max_concurrent": 1
        },
        "blender": {
            "config": {
                "engines": ["cycles", "eevee"],
                "default_engine": "cycles",
                "max_samples": 4096,
                "max_resolution": "4K"
            },
            "pricing": {
                "per_frame": 0.01,
                "per_hour": 0.5
            },
            "capabilities": ["render", "animation"],
            "max_concurrent": 1
        }
    }
    
    if service_type not in templates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown service type: {service_type}"
        )
    
    return templates[service_type]


@router.post("/validate/{service_type}")
async def validate_service_config(
    service_type: str,
    config_data: Dict[str, Any],
    db: Session = Depends(get_db),
    miner_id: str = Depends(get_miner_id)
) -> Dict[str, Any]:
    """Validate service configuration against miner capabilities"""
    # Get miner info
    stmt = select(Miner).where(Miner.miner_id == miner_id)
    miner = db.execute(stmt).scalar_one_or_none()
    
    if not miner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Miner not found"
        )
    
    # Validate based on service type
    validation_result = {
        "valid": True,
        "warnings": [],
        "errors": []
    }
    
    if service_type == "stable_diffusion":
        # Check VRAM requirements
        max_resolution = config_data.get("config", {}).get("max_resolution", "1024x1024")
        if "4K" in max_resolution and miner.gpu_vram_gb < 16:
            validation_result["warnings"].append("4K resolution requires at least 16GB VRAM")
        
        if miner.gpu_vram_gb < 8:
            validation_result["errors"].append("Stable Diffusion requires at least 8GB VRAM")
            validation_result["valid"] = False
    
    elif service_type == "llm_inference":
        # Check model size vs VRAM
        models = config_data.get("config", {}).get("models", [])
        for model in models:
            if "70b" in model.lower() and miner.gpu_vram_gb < 64:
                validation_result["warnings"].append(f"{model} requires 64GB VRAM")
    
    elif service_type == "blender":
        # Check if GPU is supported
        engine = config_data.get("config", {}).get("default_engine", "cycles")
        if engine == "cycles" and "nvidia" not in miner.tags.get("gpu", "").lower():
            validation_result["warnings"].append("Cycles engine works best with NVIDIA GPUs")
    
    return validation_result
