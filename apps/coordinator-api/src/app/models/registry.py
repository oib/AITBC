"""
Dynamic service registry models for AITBC
"""

from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator


class ServiceCategory(str, Enum):
    """Service categories"""
    AI_ML = "ai_ml"
    MEDIA_PROCESSING = "media_processing"
    SCIENTIFIC_COMPUTING = "scientific_computing"
    DATA_ANALYTICS = "data_analytics"
    GAMING_ENTERTAINMENT = "gaming_entertainment"
    DEVELOPMENT_TOOLS = "development_tools"


class ParameterType(str, Enum):
    """Parameter types"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    FILE = "file"
    ENUM = "enum"


class PricingModel(str, Enum):
    """Pricing models"""
    PER_UNIT = "per_unit"  # per image, per minute, per token
    PER_HOUR = "per_hour"
    PER_GB = "per_gb"
    PER_FRAME = "per_frame"
    FIXED = "fixed"
    CUSTOM = "custom"


class ParameterDefinition(BaseModel):
    """Parameter definition schema"""
    name: str = Field(..., description="Parameter name")
    type: ParameterType = Field(..., description="Parameter type")
    required: bool = Field(True, description="Whether parameter is required")
    description: str = Field(..., description="Parameter description")
    default: Optional[Any] = Field(None, description="Default value")
    min_value: Optional[Union[int, float]] = Field(None, description="Minimum value")
    max_value: Optional[Union[int, float]] = Field(None, description="Maximum value")
    options: Optional[List[Union[str, int]]] = Field(None, description="Available options for enum type")
    validation: Optional[Dict[str, Any]] = Field(None, description="Custom validation rules")


class HardwareRequirement(BaseModel):
    """Hardware requirement definition"""
    component: str = Field(..., description="Component type (gpu, cpu, ram, etc.)")
    min_value: Union[str, int, float] = Field(..., description="Minimum requirement")
    recommended: Optional[Union[str, int, float]] = Field(None, description="Recommended value")
    unit: Optional[str] = Field(None, description="Unit (GB, MB, cores, etc.)")


class PricingTier(BaseModel):
    """Pricing tier definition"""
    name: str = Field(..., description="Tier name")
    model: PricingModel = Field(..., description="Pricing model")
    unit_price: float = Field(..., ge=0, description="Price per unit")
    min_charge: Optional[float] = Field(None, ge=0, description="Minimum charge")
    currency: str = Field("AITBC", description="Currency code")
    description: Optional[str] = Field(None, description="Tier description")


class ServiceDefinition(BaseModel):
    """Complete service definition"""
    id: str = Field(..., description="Unique service identifier")
    name: str = Field(..., description="Human-readable service name")
    category: ServiceCategory = Field(..., description="Service category")
    description: str = Field(..., description="Service description")
    version: str = Field("1.0.0", description="Service version")
    icon: Optional[str] = Field(None, description="Icon emoji or URL")
    
    # Input/Output
    input_parameters: List[ParameterDefinition] = Field(..., description="Input parameters")
    output_schema: Dict[str, Any] = Field(..., description="Output schema")
    
    # Hardware requirements
    requirements: List[HardwareRequirement] = Field(..., description="Hardware requirements")
    
    # Pricing
    pricing: List[PricingTier] = Field(..., description="Available pricing tiers")
    
    # Capabilities
    capabilities: List[str] = Field(default_factory=list, description="Service capabilities")
    tags: List[str] = Field(default_factory=list, description="Search tags")
    
    # Limits
    max_concurrent: int = Field(1, ge=1, le=100, description="Max concurrent jobs")
    timeout_seconds: int = Field(3600, ge=60, description="Default timeout")
    
    # Metadata
    provider: Optional[str] = Field(None, description="Service provider")
    documentation_url: Optional[str] = Field(None, description="Documentation URL")
    example_usage: Optional[Dict[str, Any]] = Field(None, description="Example usage")
    
    @validator('id')
    def validate_id(cls, v):
        if not v or not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Service ID must contain only alphanumeric characters, hyphens, and underscores')
        return v.lower()


class ServiceRegistry(BaseModel):
    """Service registry containing all available services"""
    version: str = Field("1.0.0", description="Registry version")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Last update time")
    services: Dict[str, ServiceDefinition] = Field(..., description="Service definitions by ID")
    
    def get_service(self, service_id: str) -> Optional[ServiceDefinition]:
        """Get service by ID"""
        return self.services.get(service_id)
    
    def get_services_by_category(self, category: ServiceCategory) -> List[ServiceDefinition]:
        """Get all services in a category"""
        return [s for s in self.services.values() if s.category == category]
    
    def search_services(self, query: str) -> List[ServiceDefinition]:
        """Search services by name, description, or tags"""
        query = query.lower()
        results = []
        
        for service in self.services.values():
            if (query in service.name.lower() or 
                query in service.description.lower() or
                any(query in tag.lower() for tag in service.tags)):
                results.append(service)
        
        return results


# Predefined service templates
AI_ML_SERVICES = {
    "llm_inference": ServiceDefinition(
        id="llm_inference",
        name="LLM Inference",
        category=ServiceCategory.AI_ML,
        description="Run inference on large language models",
        icon="🤖",
        input_parameters=[
            ParameterDefinition(
                name="model",
                type=ParameterType.ENUM,
                required=True,
                description="Model to use for inference",
                options=["llama-7b", "llama-13b", "llama-70b", "mistral-7b", "mixtral-8x7b", "codellama-7b", "codellama-13b", "codellama-34b", "falcon-7b", "falcon-40b"]
            ),
            ParameterDefinition(
                name="prompt",
                type=ParameterType.STRING,
                required=True,
                description="Input prompt text",
                min_value=1,
                max_value=10000
            ),
            ParameterDefinition(
                name="max_tokens",
                type=ParameterType.INTEGER,
                required=False,
                description="Maximum tokens to generate",
                default=256,
                min_value=1,
                max_value=4096
            ),
            ParameterDefinition(
                name="temperature",
                type=ParameterType.FLOAT,
                required=False,
                description="Sampling temperature",
                default=0.7,
                min_value=0.0,
                max_value=2.0
            ),
            ParameterDefinition(
                name="stream",
                type=ParameterType.BOOLEAN,
                required=False,
                description="Stream response",
                default=False
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "tokens_used": {"type": "integer"},
                "finish_reason": {"type": "string"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-4090"),
            HardwareRequirement(component="vram", min_value=8, recommended=24, unit="GB"),
            HardwareRequirement(component="cuda", min_value="11.8")
        ],
        pricing=[
            PricingTier(name="basic", model=PricingModel.PER_UNIT, unit_price=0.001, min_charge=0.01),
            PricingTier(name="premium", model=PricingModel.PER_UNIT, unit_price=0.002, min_charge=0.01)
        ],
        capabilities=["generate", "stream", "chat", "completion"],
        tags=["llm", "text", "generation", "ai", "nlp"],
        max_concurrent=2,
        timeout_seconds=300
    ),
    
    "image_generation": ServiceDefinition(
        id="image_generation",
        name="Image Generation",
        category=ServiceCategory.AI_ML,
        description="Generate images from text prompts using diffusion models",
        icon="🎨",
        input_parameters=[
            ParameterDefinition(
                name="model",
                type=ParameterType.ENUM,
                required=True,
                description="Image generation model",
                options=["stable-diffusion-1.5", "stable-diffusion-2.1", "stable-diffusion-xl", "sdxl-turbo", "dall-e-2", "dall-e-3", "midjourney-v5"]
            ),
            ParameterDefinition(
                name="prompt",
                type=ParameterType.STRING,
                required=True,
                description="Text prompt for image generation",
                max_value=1000
            ),
            ParameterDefinition(
                name="negative_prompt",
                type=ParameterType.STRING,
                required=False,
                description="Negative prompt",
                max_value=1000
            ),
            ParameterDefinition(
                name="width",
                type=ParameterType.INTEGER,
                required=False,
                description="Image width",
                default=512,
                options=[256, 512, 768, 1024, 1536, 2048]
            ),
            ParameterDefinition(
                name="height",
                type=ParameterType.INTEGER,
                required=False,
                description="Image height",
                default=512,
                options=[256, 512, 768, 1024, 1536, 2048]
            ),
            ParameterDefinition(
                name="num_images",
                type=ParameterType.INTEGER,
                required=False,
                description="Number of images to generate",
                default=1,
                min_value=1,
                max_value=4
            ),
            ParameterDefinition(
                name="steps",
                type=ParameterType.INTEGER,
                required=False,
                description="Number of inference steps",
                default=20,
                min_value=1,
                max_value=100
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "images": {"type": "array", "items": {"type": "string"}},
                "parameters": {"type": "object"},
                "generation_time": {"type": "number"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-4090"),
            HardwareRequirement(component="vram", min_value=4, recommended=16, unit="GB"),
            HardwareRequirement(component="cuda", min_value="11.8")
        ],
        pricing=[
            PricingTier(name="standard", model=PricingModel.PER_UNIT, unit_price=0.01, min_charge=0.01),
            PricingTier(name="hd", model=PricingModel.PER_UNIT, unit_price=0.02, min_charge=0.02),
            PricingTier(name="4k", model=PricingModel.PER_UNIT, unit_price=0.05, min_charge=0.05)
        ],
        capabilities=["txt2img", "img2img", "inpainting", "outpainting"],
        tags=["image", "generation", "diffusion", "ai", "art"],
        max_concurrent=1,
        timeout_seconds=600
    ),
    
    "video_generation": ServiceDefinition(
        id="video_generation",
        name="Video Generation",
        category=ServiceCategory.AI_ML,
        description="Generate videos from text or images",
        icon="🎬",
        input_parameters=[
            ParameterDefinition(
                name="model",
                type=ParameterType.ENUM,
                required=True,
                description="Video generation model",
                options=["sora", "runway-gen2", "pika-labs", "stable-video-diffusion", "make-a-video"]
            ),
            ParameterDefinition(
                name="prompt",
                type=ParameterType.STRING,
                required=True,
                description="Text prompt for video generation",
                max_value=500
            ),
            ParameterDefinition(
                name="duration_seconds",
                type=ParameterType.INTEGER,
                required=False,
                description="Video duration in seconds",
                default=4,
                min_value=1,
                max_value=30
            ),
            ParameterDefinition(
                name="fps",
                type=ParameterType.INTEGER,
                required=False,
                description="Frames per second",
                default=24,
                options=[12, 24, 30]
            ),
            ParameterDefinition(
                name="resolution",
                type=ParameterType.ENUM,
                required=False,
                description="Video resolution",
                default="720p",
                options=["480p", "720p", "1080p", "4k"]
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "video_url": {"type": "string"},
                "thumbnail_url": {"type": "string"},
                "duration": {"type": "number"},
                "resolution": {"type": "string"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="a100"),
            HardwareRequirement(component="vram", min_value=16, recommended=40, unit="GB"),
            HardwareRequirement(component="cuda", min_value="11.8")
        ],
        pricing=[
            PricingTier(name="short", model=PricingModel.PER_UNIT, unit_price=0.1, min_charge=0.1),
            PricingTier(name="medium", model=PricingModel.PER_UNIT, unit_price=0.25, min_charge=0.25),
            PricingTier(name="long", model=PricingModel.PER_UNIT, unit_price=0.5, min_charge=0.5)
        ],
        capabilities=["txt2video", "img2video", "video-editing"],
        tags=["video", "generation", "ai", "animation"],
        max_concurrent=1,
        timeout_seconds=1800
    ),
    
    "speech_recognition": ServiceDefinition(
        id="speech_recognition",
        name="Speech Recognition",
        category=ServiceCategory.AI_ML,
        description="Transcribe audio to text using speech recognition models",
        icon="🎙️",
        input_parameters=[
            ParameterDefinition(
                name="model",
                type=ParameterType.ENUM,
                required=True,
                description="Speech recognition model",
                options=["whisper-tiny", "whisper-base", "whisper-small", "whisper-medium", "whisper-large", "whisper-large-v2", "whisper-large-v3"]
            ),
            ParameterDefinition(
                name="audio_file",
                type=ParameterType.FILE,
                required=True,
                description="Audio file to transcribe"
            ),
            ParameterDefinition(
                name="language",
                type=ParameterType.ENUM,
                required=False,
                description="Audio language",
                default="auto",
                options=["auto", "en", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh", "ar", "hi"]
            ),
            ParameterDefinition(
                name="task",
                type=ParameterType.ENUM,
                required=False,
                description="Task type",
                default="transcribe",
                options=["transcribe", "translate"]
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "language": {"type": "string"},
                "segments": {"type": "array"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3060"),
            HardwareRequirement(component="vram", min_value=1, recommended=4, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_minute", model=PricingModel.PER_UNIT, unit_price=0.001, min_charge=0.01)
        ],
        capabilities=["transcribe", "translate", "timestamp", "speaker-diarization"],
        tags=["speech", "audio", "transcription", "whisper"],
        max_concurrent=2,
        timeout_seconds=600
    ),
    
    "computer_vision": ServiceDefinition(
        id="computer_vision",
        name="Computer Vision",
        category=ServiceCategory.AI_ML,
        description="Analyze images with computer vision models",
        icon="👁️",
        input_parameters=[
            ParameterDefinition(
                name="task",
                type=ParameterType.ENUM,
                required=True,
                description="Vision task",
                options=["object-detection", "classification", "face-recognition", "segmentation", "ocr"]
            ),
            ParameterDefinition(
                name="model",
                type=ParameterType.ENUM,
                required=True,
                description="Vision model",
                options=["yolo-v8", "resnet-50", "efficientnet", "vit", "face-net", "tesseract"]
            ),
            ParameterDefinition(
                name="image",
                type=ParameterType.FILE,
                required=True,
                description="Input image"
            ),
            ParameterDefinition(
                name="confidence_threshold",
                type=ParameterType.FLOAT,
                required=False,
                description="Confidence threshold",
                default=0.5,
                min_value=0.0,
                max_value=1.0
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "detections": {"type": "array"},
                "labels": {"type": "array"},
                "confidence_scores": {"type": "array"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3060"),
            HardwareRequirement(component="vram", min_value=2, recommended=8, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_image", model=PricingModel.PER_UNIT, unit_price=0.005, min_charge=0.01)
        ],
        capabilities=["detection", "classification", "recognition", "segmentation", "ocr"],
        tags=["vision", "image", "analysis", "ai", "detection"],
        max_concurrent=4,
        timeout_seconds=120
    ),
    
    "recommendation_system": ServiceDefinition(
        id="recommendation_system",
        name="Recommendation System",
        category=ServiceCategory.AI_ML,
        description="Generate personalized recommendations",
        icon="🎯",
        input_parameters=[
            ParameterDefinition(
                name="model_type",
                type=ParameterType.ENUM,
                required=True,
                description="Recommendation model type",
                options=["collaborative", "content-based", "hybrid", "deep-learning"]
            ),
            ParameterDefinition(
                name="user_id",
                type=ParameterType.STRING,
                required=True,
                description="User identifier"
            ),
            ParameterDefinition(
                name="item_data",
                type=ParameterType.ARRAY,
                required=True,
                description="Item catalog data"
            ),
            ParameterDefinition(
                name="num_recommendations",
                type=ParameterType.INTEGER,
                required=False,
                description="Number of recommendations",
                default=10,
                min_value=1,
                max_value=100
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "recommendations": {"type": "array"},
                "scores": {"type": "array"},
                "explanation": {"type": "string"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3080"),
            HardwareRequirement(component="vram", min_value=4, recommended=12, unit="GB"),
            HardwareRequirement(component="ram", min_value=16, recommended=32, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_request", model=PricingModel.PER_UNIT, unit_price=0.01, min_charge=0.01),
            PricingTier(name="bulk", model=PricingModel.PER_UNIT, unit_price=0.005, min_charge=0.1)
        ],
        capabilities=["personalization", "real-time", "batch", "ab-testing"],
        tags=["recommendation", "personalization", "ml", "ecommerce"],
        max_concurrent=10,
        timeout_seconds=60
    )
}

# Create global service registry instance
service_registry = ServiceRegistry(services=AI_ML_SERVICES)
