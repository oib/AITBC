"""
Validation router for service configuration validation
"""

from typing import Dict, List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_miner_from_token
from ..models import Miner
from ..services.validation import HardwareValidator, ValidationResult

router = APIRouter(tags=["validation"])
validator = HardwareValidator()


@router.post("/validation/service/{service_id}")
async def validate_service(
    service_id: str,
    config: Dict[str, Any],
    miner: Miner = Depends(get_miner_from_token)
) -> Dict[str, Any]:
    """Validate if miner can run a specific service with given configuration"""
    
    result = await validator.validate_service_for_miner(miner, service_id, config)
    
    return {
        "valid": result.valid,
        "errors": result.errors,
        "warnings": result.warnings,
        "score": result.score,
        "missing_requirements": result.missing_requirements,
        "performance_impact": result.performance_impact
    }


@router.get("/validation/compatible-services")
async def get_compatible_services(
    miner: Miner = Depends(get_miner_from_token)
) -> List[Dict[str, Any]]:
    """Get list of services compatible with miner hardware, sorted by compatibility score"""
    
    compatible = await validator.get_compatible_services(miner)
    
    return [
        {
            "service_id": service_id,
            "compatibility_score": score,
            "grade": _get_grade_from_score(score)
        }
        for service_id, score in compatible
    ]


@router.post("/validation/batch")
async def validate_multiple_services(
    validations: List[Dict[str, Any]],
    miner: Miner = Depends(get_miner_from_token)
) -> List[Dict[str, Any]]:
    """Validate multiple service configurations in batch"""
    
    results = []
    
    for validation in validations:
        service_id = validation.get("service_id")
        config = validation.get("config", {})
        
        if not service_id:
            results.append({
                "service_id": service_id,
                "valid": False,
                "errors": ["Missing service_id"]
            })
            continue
        
        result = await validator.validate_service_for_miner(miner, service_id, config)
        
        results.append({
            "service_id": service_id,
            "valid": result.valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "score": result.score,
            "performance_impact": result.performance_impact
        })
    
    return results


@router.get("/validation/hardware-profile")
async def get_hardware_profile(
    miner: Miner = Depends(get_miner_from_token)
) -> Dict[str, Any]:
    """Get miner's hardware profile with capabilities assessment"""
    
    # Get compatible services to assess capabilities
    compatible = await validator.get_compatible_services(miner)
    
    # Analyze hardware capabilities
    profile = {
        "miner_id": miner.id,
        "hardware": {
            "gpu": {
                "name": miner.gpu_name,
                "vram_gb": miner.gpu_vram_gb,
                "available": miner.gpu_name is not None
            },
            "cpu": {
                "cores": miner.cpu_cores
            },
            "ram": {
                "gb": miner.ram_gb
            },
            "capabilities": miner.capabilities,
            "tags": miner.tags
        },
        "assessment": {
            "total_services": len(compatible),
            "highly_compatible": len([s for s in compatible if s[1] >= 80]),
            "moderately_compatible": len([s for s in compatible if 50 <= s[1] < 80]),
            "barely_compatible": len([s for s in compatible if s[1] < 50]),
            "best_categories": _get_best_categories(compatible)
        },
        "recommendations": _generate_recommendations(miner, compatible)
    }
    
    return profile


def _get_grade_from_score(score: int) -> str:
    """Convert compatibility score to letter grade"""
    if score >= 90:
        return "A+"
    elif score >= 80:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 60:
        return "C"
    elif score >= 50:
        return "D"
    else:
        return "F"


def _get_best_categories(compatible: List[tuple]) -> List[str]:
    """Get the categories with highest compatibility"""
    # This would need category info from registry
    # For now, return placeholder
    return ["AI/ML", "Media Processing"]


def _generate_recommendations(miner: Miner, compatible: List[tuple]) -> List[str]:
    """Generate hardware upgrade recommendations"""
    recommendations = []
    
    # Check VRAM
    if miner.gpu_vram_gb < 8:
        recommendations.append("Upgrade GPU to at least 8GB VRAM for better AI/ML performance")
    elif miner.gpu_vram_gb < 16:
        recommendations.append("Consider upgrading to 16GB+ VRAM for optimal performance")
    
    # Check CPU
    if miner.cpu_cores < 8:
        recommendations.append("More CPU cores would improve parallel processing")
    
    # Check RAM
    if miner.ram_gb < 16:
        recommendations.append("Upgrade to 16GB+ RAM for better multitasking")
    
    # Check capabilities
    if "cuda" not in [c.lower() for c in miner.capabilities]:
        recommendations.append("CUDA support would enable more GPU services")
    
    # Based on compatible services
    if len(compatible) < 10:
        recommendations.append("Hardware upgrade recommended to access more services")
    elif len(compatible) > 20:
        recommendations.append("Your hardware is well-suited for a wide range of services")
    
    return recommendations
