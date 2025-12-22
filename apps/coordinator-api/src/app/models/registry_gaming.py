"""
Gaming & entertainment service definitions
"""

from typing import Dict, List, Any, Union
from .registry import (
    ServiceDefinition,
    ServiceCategory,
    ParameterDefinition,
    ParameterType,
    HardwareRequirement,
    PricingTier,
    PricingModel
)


GAMING_SERVICES = {
    "cloud_gaming": ServiceDefinition(
        id="cloud_gaming",
        name="Cloud Gaming Server",
        category=ServiceCategory.GAMING_ENTERTAINMENT,
        description="Host cloud gaming sessions with GPU streaming",
        icon="🎮",
        input_parameters=[
            ParameterDefinition(
                name="game",
                type=ParameterType.STRING,
                required=True,
                description="Game title or executable"
            ),
            ParameterDefinition(
                name="resolution",
                type=ParameterType.ENUM,
                required=True,
                description="Streaming resolution",
                options=["720p", "1080p", "1440p", "4k"]
            ),
            ParameterDefinition(
                name="fps",
                type=ParameterType.INTEGER,
                required=False,
                description="Target frame rate",
                default=60,
                options=[30, 60, 120, 144]
            ),
            ParameterDefinition(
                name="session_duration",
                type=ParameterType.INTEGER,
                required=True,
                description="Session duration in minutes",
                min_value=15,
                max_value=480
            ),
            ParameterDefinition(
                name="codec",
                type=ParameterType.ENUM,
                required=False,
                description="Streaming codec",
                default="h264",
                options=["h264", "h265", "av1", "vp9"]
            ),
            ParameterDefinition(
                name="region",
                type=ParameterType.STRING,
                required=False,
                description="Preferred server region"
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "stream_url": {"type": "string"},
                "session_id": {"type": "string"},
                "latency_ms": {"type": "integer"},
                "quality_metrics": {"type": "object"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3080"),
            HardwareRequirement(component="vram", min_value=8, recommended=16, unit="GB"),
            HardwareRequirement(component="network", min_value="100Mbps", recommended="1Gbps"),
            HardwareRequirement(component="cpu", min_value=8, recommended=16, unit="cores"),
            HardwareRequirement(component="ram", min_value=16, recommended=32, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=1, min_charge=0.5),
            PricingTier(name="1080p", model=PricingModel.PER_HOUR, unit_price=1.5, min_charge=0.75),
            PricingTier(name="4k", model=PricingModel.PER_HOUR, unit_price=3, min_charge=1.5)
        ],
        capabilities=["low-latency", "game-streaming", "multiplayer", "saves"],
        tags=["gaming", "cloud", "streaming", "nvidia", "gamepass"],
        max_concurrent=1,
        timeout_seconds=28800  # 8 hours
    ),
    
    "game_asset_baking": ServiceDefinition(
        id="game_asset_baking",
        name="Game Asset Baking",
        category=ServiceCategory.GAMING_ENTERTAINMENT,
        description="Optimize and bake game assets (textures, meshes, materials)",
        icon="🎨",
        input_parameters=[
            ParameterDefinition(
                name="asset_type",
                type=ParameterType.ENUM,
                required=True,
                description="Asset type",
                options=["texture", "mesh", "material", "animation", "terrain"]
            ),
            ParameterDefinition(
                name="input_assets",
                type=ParameterType.ARRAY,
                required=True,
                description="Input asset files",
                items={"type": "string"}
            ),
            ParameterDefinition(
                name="target_platform",
                type=ParameterType.ENUM,
                required=True,
                description="Target platform",
                options=["pc", "mobile", "console", "web", "vr"]
            ),
            ParameterDefinition(
                name="optimization_level",
                type=ParameterType.ENUM,
                required=False,
                description="Optimization level",
                default="balanced",
                options=["fast", "balanced", "maximum"]
            ),
            ParameterDefinition(
                name="texture_formats",
                type=ParameterType.ARRAY,
                required=False,
                description="Output texture formats",
                default=["dds", "astc"],
                items={"type": "string"}
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "baked_assets": {"type": "array"},
                "compression_stats": {"type": "object"},
                "optimization_report": {"type": "object"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3080"),
            HardwareRequirement(component="vram", min_value=8, recommended=16, unit="GB"),
            HardwareRequirement(component="ram", min_value=16, recommended=32, unit="GB"),
            HardwareRequirement(component="storage", min_value=50, recommended=500, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_asset", model=PricingModel.PER_UNIT, unit_price=0.01, min_charge=0.1),
            PricingTier(name="per_texture", model=PricingModel.PER_UNIT, unit_price=0.005, min_charge=0.05),
            PricingTier(name="per_mesh", model=PricingModel.PER_UNIT, unit_price=0.02, min_charge=0.1)
        ],
        capabilities=["texture-compression", "mesh-optimization", "lod-generation", "platform-specific"],
        tags=["gamedev", "assets", "optimization", "textures", "meshes"],
        max_concurrent=5,
        timeout_seconds=1800
    ),
    
    "physics_simulation": ServiceDefinition(
        id="physics_simulation",
        name="Game Physics Simulation",
        category=ServiceCategory.GAMING_ENTERTAINMENT,
        description="Run physics simulations for game development",
        icon="⚛️",
        input_parameters=[
            ParameterDefinition(
                name="engine",
                type=ParameterType.ENUM,
                required=True,
                description="Physics engine",
                options=["physx", "havok", "bullet", "box2d", "chipmunk"]
            ),
            ParameterDefinition(
                name="simulation_type",
                type=ParameterType.ENUM,
                required=True,
                description="Simulation type",
                options=["rigid-body", "soft-body", "fluid", "cloth", "destruction"]
            ),
            ParameterDefinition(
                name="scene_file",
                type=ParameterType.FILE,
                required=False,
                description="Scene or level file"
            ),
            ParameterDefinition(
                name="parameters",
                type=ParameterType.OBJECT,
                required=True,
                description="Physics parameters"
            ),
            ParameterDefinition(
                name="simulation_time",
                type=ParameterType.FLOAT,
                required=True,
                description="Simulation duration in seconds",
                min_value=0.1
            ),
            ParameterDefinition(
                name="record_frames",
                type=ParameterType.BOOLEAN,
                required=False,
                description="Record animation frames",
                default=False
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "simulation_data": {"type": "array"},
                "animation_url": {"type": "string"},
                "physics_stats": {"type": "object"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3080"),
            HardwareRequirement(component="vram", min_value=8, recommended=16, unit="GB"),
            HardwareRequirement(component="cpu", min_value=8, recommended=16, unit="cores"),
            HardwareRequirement(component="ram", min_value=16, recommended=32, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=1, min_charge=0.5),
            PricingTier(name="per_frame", model=PricingModel.PER_UNIT, unit_price=0.001, min_charge=0.1),
            PricingTier(name="complex", model=PricingModel.PER_HOUR, unit_price=2, min_charge=1)
        ],
        capabilities=["gpu-physics", "particle-systems", "destruction", "cloth"],
        tags=["physics", "gamedev", "simulation", "physx", "havok"],
        max_concurrent=3,
        timeout_seconds=3600
    ),
    
    "vr_ar_rendering": ServiceDefinition(
        id="vr_ar_rendering",
        name="VR/AR Rendering",
        category=ServiceCategory.GAMING_ENTERTAINMENT,
        description="Real-time 3D rendering for VR/AR applications",
        icon="🥽",
        input_parameters=[
            ParameterDefinition(
                name="platform",
                type=ParameterType.ENUM,
                required=True,
                description="Target platform",
                options=["oculus", "vive", "hololens", "magic-leap", "cardboard", "webxr"]
            ),
            ParameterDefinition(
                name="scene_file",
                type=ParameterType.FILE,
                required=True,
                description="3D scene file"
            ),
            ParameterDefinition(
                name="render_quality",
                type=ParameterType.ENUM,
                required=False,
                description="Render quality",
                default="high",
                options=["low", "medium", "high", "ultra"]
            ),
            ParameterDefinition(
                name="stereo_mode",
                type=ParameterType.BOOLEAN,
                required=False,
                description="Stereo rendering",
                default=True
            ),
            ParameterDefinition(
                name="target_fps",
                type=ParameterType.INTEGER,
                required=False,
                description="Target frame rate",
                default=90,
                options=[60, 72, 90, 120, 144]
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "rendered_frames": {"type": "array"},
                "performance_metrics": {"type": "object"},
                "vr_package": {"type": "string"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3080"),
            HardwareRequirement(component="vram", min_value=8, recommended=16, unit="GB"),
            HardwareRequirement(component="cpu", min_value=8, recommended=16, unit="cores"),
            HardwareRequirement(component="ram", min_value=16, recommended=32, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_minute", model=PricingModel.PER_UNIT, unit_price=0.02, min_charge=0.5),
            PricingTier(name="per_frame", model=PricingModel.PER_UNIT, unit_price=0.001, min_charge=0.1),
            PricingTier(name="real-time", model=PricingModel.PER_HOUR, unit_price=5, min_charge=1)
        ],
        capabilities=["stereo-rendering", "real-time", "low-latency", "tracking"],
        tags=["vr", "ar", "rendering", "3d", "immersive"],
        max_concurrent=2,
        timeout_seconds=3600
    )
}
