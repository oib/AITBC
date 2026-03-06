"""
Service registry router for dynamic service management
"""

from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, status
from ..models.registry import (
    ServiceRegistry,
    ServiceDefinition,
    ServiceCategory
)
from ..models.registry_media import MEDIA_PROCESSING_SERVICES
from ..models.registry_scientific import SCIENTIFIC_COMPUTING_SERVICES
from ..models.registry_data import DATA_ANALYTICS_SERVICES
from ..models.registry_gaming import GAMING_SERVICES
from ..models.registry_devtools import DEVTOOLS_SERVICES
from ..models.registry import AI_ML_SERVICES

router = APIRouter(prefix="/registry", tags=["service-registry"])

# Initialize service registry with all services
def create_service_registry() -> ServiceRegistry:
    """Create and populate the service registry"""
    all_services = {}
    
    # Add all service categories
    all_services.update(AI_ML_SERVICES)
    all_services.update(MEDIA_PROCESSING_SERVICES)
    all_services.update(SCIENTIFIC_COMPUTING_SERVICES)
    all_services.update(DATA_ANALYTICS_SERVICES)
    all_services.update(GAMING_SERVICES)
    all_services.update(DEVTOOLS_SERVICES)
    
    return ServiceRegistry(
        version="1.0.0",
        services=all_services
    )

# Global registry instance
service_registry = create_service_registry()


@router.get("/", response_model=ServiceRegistry)
async def get_registry() -> ServiceRegistry:
    """Get the complete service registry"""
    return service_registry


@router.get("/services", response_model=List[ServiceDefinition])
async def list_services(
    category: Optional[ServiceCategory] = None,
    search: Optional[str] = None
) -> List[ServiceDefinition]:
    """List all available services with optional filtering"""
    services = list(service_registry.services.values())
    
    # Filter by category
    if category:
        services = [s for s in services if s.category == category]
    
    # Search by name, description, or tags
    if search:
        search = search.lower()
        services = [
            s for s in services
            if (search in s.name.lower() or
                search in s.description.lower() or
                any(search in tag.lower() for tag in s.tags))
        ]
    
    return services


@router.get("/services/{service_id}", response_model=ServiceDefinition)
async def get_service(service_id: str) -> ServiceDefinition:
    """Get a specific service definition"""
    service = service_registry.get_service(service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service {service_id} not found"
        )
    return service


@router.get("/categories", response_model=List[Dict[str, Any]])
async def list_categories() -> List[Dict[str, Any]]:
    """List all service categories with counts"""
    category_counts = {}
    for service in service_registry.services.values():
        category = service.category.value
        if category not in category_counts:
            category_counts[category] = 0
        category_counts[category] += 1
    
    return [
        {"category": cat, "count": count}
        for cat, count in category_counts.items()
    ]


@router.get("/categories/{category}", response_model=List[ServiceDefinition])
async def get_services_by_category(category: ServiceCategory) -> List[ServiceDefinition]:
    """Get all services in a specific category"""
    return service_registry.get_services_by_category(category)


@router.get("/services/{service_id}/schema")
async def get_service_schema(service_id: str) -> Dict[str, Any]:
    """Get JSON schema for a service's input parameters"""
    service = service_registry.get_service(service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service {service_id} not found"
        )
    
    # Convert input parameters to JSON schema
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
    
    return {
        "type": "object",
        "properties": properties,
        "required": required
    }


@router.get("/services/{service_id}/requirements")
async def get_service_requirements(service_id: str) -> Dict[str, Any]:
    """Get hardware requirements for a service"""
    service = service_registry.get_service(service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service {service_id} not found"
        )
    
    return {
        "requirements": [
            {
                "component": req.component,
                "minimum": req.min_value,
                "recommended": req.recommended,
                "unit": req.unit
            }
            for req in service.requirements
        ]
    }


@router.get("/services/{service_id}/pricing")
async def get_service_pricing(service_id: str) -> Dict[str, Any]:
    """Get pricing information for a service"""
    service = service_registry.get_service(service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service {service_id} not found"
        )
    
    return {
        "pricing": [
            {
                "tier": tier.name,
                "model": tier.model.value,
                "unit_price": tier.unit_price,
                "min_charge": tier.min_charge,
                "currency": tier.currency,
                "description": tier.description
            }
            for tier in service.pricing
        ]
    }


@router.post("/services/validate")
async def validate_service_request(
    service_id: str,
    request_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate a service request against the service schema"""
    service = service_registry.get_service(service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service {service_id} not found"
        )
    
    # Validate request data
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


@router.get("/stats")
async def get_registry_stats() -> Dict[str, Any]:
    """Get registry statistics"""
    total_services = len(service_registry.services)
    category_counts = {}
    
    for service in service_registry.services.values():
        category = service.category.value
        if category not in category_counts:
            category_counts[category] = 0
        category_counts[category] += 1
    
    # Count unique pricing models
    pricing_models = set()
    for service in service_registry.services.values():
        for tier in service.pricing:
            pricing_models.add(tier.model.value)
    
    return {
        "total_services": total_services,
        "categories": category_counts,
        "pricing_models": list(pricing_models),
        "last_updated": service_registry.last_updated.isoformat()
    }
