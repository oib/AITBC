"""
Media processing service definitions
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


MEDIA_PROCESSING_SERVICES = {
    "video_transcoding": ServiceDefinition(
        id="video_transcoding",
        name="Video Transcoding",
        category=ServiceCategory.MEDIA_PROCESSING,
        description="Transcode videos between formats using FFmpeg with GPU acceleration",
        icon="🎬",
        input_parameters=[
            ParameterDefinition(
                name="input_video",
                type=ParameterType.FILE,
                required=True,
                description="Input video file"
            ),
            ParameterDefinition(
                name="output_format",
                type=ParameterType.ENUM,
                required=True,
                description="Output video format",
                options=["mp4", "webm", "avi", "mov", "mkv", "flv"]
            ),
            ParameterDefinition(
                name="codec",
                type=ParameterType.ENUM,
                required=False,
                description="Video codec",
                default="h264",
                options=["h264", "h265", "vp9", "av1", "mpeg4"]
            ),
            ParameterDefinition(
                name="resolution",
                type=ParameterType.STRING,
                required=False,
                description="Output resolution (e.g., 1920x1080)",
                validation={"pattern": r"^\d+x\d+$"}
            ),
            ParameterDefinition(
                name="bitrate",
                type=ParameterType.STRING,
                required=False,
                description="Target bitrate (e.g., 5M, 2500k)",
                validation={"pattern": r"^\d+[kM]?$"}
            ),
            ParameterDefinition(
                name="fps",
                type=ParameterType.INTEGER,
                required=False,
                description="Output frame rate",
                min_value=1,
                max_value=120
            ),
            ParameterDefinition(
                name="gpu_acceleration",
                type=ParameterType.BOOLEAN,
                required=False,
                description="Use GPU acceleration",
                default=True
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "output_url": {"type": "string"},
                "metadata": {"type": "object"},
                "duration": {"type": "number"},
                "file_size": {"type": "integer"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="any", recommended="nvidia"),
            HardwareRequirement(component="vram", min_value=2, recommended=8, unit="GB"),
            HardwareRequirement(component="ram", min_value=8, recommended=16, unit="GB"),
            HardwareRequirement(component="storage", min_value=50, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_minute", model=PricingModel.PER_UNIT, unit_price=0.005, min_charge=0.01),
            PricingTier(name="per_gb", model=PricingModel.PER_GB, unit_price=0.01, min_charge=0.01),
            PricingTier(name="4k_premium", model=PricingModel.PER_UNIT, unit_price=0.02, min_charge=0.05)
        ],
        capabilities=["transcode", "compress", "resize", "format-convert"],
        tags=["video", "ffmpeg", "transcoding", "encoding", "gpu"],
        max_concurrent=2,
        timeout_seconds=3600
    ),
    
    "video_streaming": ServiceDefinition(
        id="video_streaming",
        name="Live Video Streaming",
        category=ServiceCategory.MEDIA_PROCESSING,
        description="Real-time video transcoding for adaptive bitrate streaming",
        icon="📡",
        input_parameters=[
            ParameterDefinition(
                name="stream_url",
                type=ParameterType.STRING,
                required=True,
                description="Input stream URL"
            ),
            ParameterDefinition(
                name="output_formats",
                type=ParameterType.ARRAY,
                required=True,
                description="Output formats for adaptive streaming",
                default=["720p", "1080p", "4k"]
            ),
            ParameterDefinition(
                name="duration_minutes",
                type=ParameterType.INTEGER,
                required=False,
                description="Streaming duration in minutes",
                default=60,
                min_value=1,
                max_value=480
            ),
            ParameterDefinition(
                name="protocol",
                type=ParameterType.ENUM,
                required=False,
                description="Streaming protocol",
                default="hls",
                options=["hls", "dash", "rtmp", "webrtc"]
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "stream_url": {"type": "string"},
                "playlist_url": {"type": "string"},
                "bitrates": {"type": "array"},
                "duration": {"type": "number"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3080"),
            HardwareRequirement(component="vram", min_value=8, recommended=16, unit="GB"),
            HardwareRequirement(component="network", min_value="1Gbps", recommended="10Gbps"),
            HardwareRequirement(component="ram", min_value=16, recommended=32, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_minute", model=PricingModel.PER_UNIT, unit_price=0.01, min_charge=0.5),
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=0.5, min_charge=0.5)
        ],
        capabilities=["live-transcoding", "adaptive-bitrate", "multi-format", "low-latency"],
        tags=["streaming", "live", "transcoding", "real-time"],
        max_concurrent=5,
        timeout_seconds=28800  # 8 hours
    ),
    
    "3d_rendering": ServiceDefinition(
        id="3d_rendering",
        name="3D Rendering",
        category=ServiceCategory.MEDIA_PROCESSING,
        description="Render 3D scenes using Blender, Unreal Engine, or V-Ray",
        icon="🎭",
        input_parameters=[
            ParameterDefinition(
                name="engine",
                type=ParameterType.ENUM,
                required=True,
                description="Rendering engine",
                options=["blender-cycles", "blender-eevee", "unreal-engine", "v-ray", "octane"]
            ),
            ParameterDefinition(
                name="scene_file",
                type=ParameterType.FILE,
                required=True,
                description="3D scene file (.blend, .ueproject, etc)"
            ),
            ParameterDefinition(
                name="resolution_x",
                type=ParameterType.INTEGER,
                required=False,
                description="Output width",
                default=1920,
                min_value=1,
                max_value=8192
            ),
            ParameterDefinition(
                name="resolution_y",
                type=ParameterType.INTEGER,
                required=False,
                description="Output height",
                default=1080,
                min_value=1,
                max_value=8192
            ),
            ParameterDefinition(
                name="samples",
                type=ParameterType.INTEGER,
                required=False,
                description="Samples per pixel (path tracing)",
                default=128,
                min_value=1,
                max_value=10000
            ),
            ParameterDefinition(
                name="frame_start",
                type=ParameterType.INTEGER,
                required=False,
                description="Start frame for animation",
                default=1,
                min_value=1
            ),
            ParameterDefinition(
                name="frame_end",
                type=ParameterType.INTEGER,
                required=False,
                description="End frame for animation",
                default=1,
                min_value=1
            ),
            ParameterDefinition(
                name="output_format",
                type=ParameterType.ENUM,
                required=False,
                description="Output image format",
                default="png",
                options=["png", "jpg", "exr", "bmp", "tiff", "hdr"]
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "rendered_images": {"type": "array"},
                "metadata": {"type": "object"},
                "render_time": {"type": "number"},
                "frame_count": {"type": "integer"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-4090"),
            HardwareRequirement(component="vram", min_value=8, recommended=24, unit="GB"),
            HardwareRequirement(component="ram", min_value=16, recommended=64, unit="GB"),
            HardwareRequirement(component="cpu", min_value=8, recommended=16, unit="cores")
        ],
        pricing=[
            PricingTier(name="per_frame", model=PricingModel.PER_FRAME, unit_price=0.01, min_charge=0.1),
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=0.5, min_charge=0.5),
            PricingTier(name="4k_premium", model=PricingModel.PER_FRAME, unit_price=0.05, min_charge=0.5)
        ],
        capabilities=["path-tracing", "ray-tracing", "animation", "gpu-render"],
        tags=["3d", "rendering", "blender", "unreal", "v-ray"],
        max_concurrent=2,
        timeout_seconds=7200
    ),
    
    "image_processing": ServiceDefinition(
        id="image_processing",
        name="Batch Image Processing",
        category=ServiceCategory.MEDIA_PROCESSING,
        description="Process images in bulk with filters, effects, and format conversion",
        icon="🖼️",
        input_parameters=[
            ParameterDefinition(
                name="images",
                type=ParameterType.ARRAY,
                required=True,
                description="Array of image files or URLs"
            ),
            ParameterDefinition(
                name="operations",
                type=ParameterType.ARRAY,
                required=True,
                description="Processing operations to apply",
                items={
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "params": {"type": "object"}
                    }
                }
            ),
            ParameterDefinition(
                name="output_format",
                type=ParameterType.ENUM,
                required=False,
                description="Output format",
                default="jpg",
                options=["jpg", "png", "webp", "avif", "tiff", "bmp"]
            ),
            ParameterDefinition(
                name="quality",
                type=ParameterType.INTEGER,
                required=False,
                description="Output quality (1-100)",
                default=90,
                min_value=1,
                max_value=100
            ),
            ParameterDefinition(
                name="resize",
                type=ParameterType.STRING,
                required=False,
                description="Resize dimensions (e.g., 1920x1080, 50%)",
                validation={"pattern": r"^\d+x\d+|^\d+%$"}
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "processed_images": {"type": "array"},
                "count": {"type": "integer"},
                "total_size": {"type": "integer"},
                "processing_time": {"type": "number"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="any", recommended="nvidia"),
            HardwareRequirement(component="vram", min_value=1, recommended=4, unit="GB"),
            HardwareRequirement(component="ram", min_value=4, recommended=16, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_image", model=PricingModel.PER_UNIT, unit_price=0.001, min_charge=0.01),
            PricingTier(name="bulk_100", model=PricingModel.PER_UNIT, unit_price=0.0005, min_charge=0.05),
            PricingTier(name="bulk_1000", model=PricingModel.PER_UNIT, unit_price=0.0002, min_charge=0.2)
        ],
        capabilities=["resize", "filter", "format-convert", "batch", "watermark"],
        tags=["image", "processing", "batch", "filter", "conversion"],
        max_concurrent=10,
        timeout_seconds=600
    ),
    
    "audio_processing": ServiceDefinition(
        id="audio_processing",
        name="Audio Processing",
        category=ServiceCategory.MEDIA_PROCESSING,
        description="Process audio files with effects, noise reduction, and format conversion",
        icon="🎵",
        input_parameters=[
            ParameterDefinition(
                name="audio_file",
                type=ParameterType.FILE,
                required=True,
                description="Input audio file"
            ),
            ParameterDefinition(
                name="operations",
                type=ParameterType.ARRAY,
                required=True,
                description="Audio operations to apply",
                items={
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "params": {"type": "object"}
                    }
                }
            ),
            ParameterDefinition(
                name="output_format",
                type=ParameterType.ENUM,
                required=False,
                description="Output format",
                default="mp3",
                options=["mp3", "wav", "flac", "aac", "ogg", "m4a"]
            ),
            ParameterDefinition(
                name="sample_rate",
                type=ParameterType.INTEGER,
                required=False,
                description="Output sample rate",
                default=44100,
                options=[22050, 44100, 48000, 96000, 192000]
            ),
            ParameterDefinition(
                name="bitrate",
                type=ParameterType.INTEGER,
                required=False,
                description="Output bitrate (kbps)",
                default=320,
                options=[128, 192, 256, 320, 512, 1024]
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "output_url": {"type": "string"},
                "metadata": {"type": "object"},
                "duration": {"type": "number"},
                "file_size": {"type": "integer"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="any", recommended="nvidia"),
            HardwareRequirement(component="ram", min_value=2, recommended=8, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_minute", model=PricingModel.PER_UNIT, unit_price=0.002, min_charge=0.01),
            PricingTier(name="per_effect", model=PricingModel.PER_UNIT, unit_price=0.005, min_charge=0.01)
        ],
        capabilities=["noise-reduction", "effects", "format-convert", "enhancement"],
        tags=["audio", "processing", "effects", "noise-reduction"],
        max_concurrent=5,
        timeout_seconds=300
    )
}
