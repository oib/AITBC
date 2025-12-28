"""
Service schemas for common GPU workloads
"""

from typing import Any, Dict, List, Optional, Union
from enum import Enum
from pydantic import BaseModel, Field, validator
import re


class ServiceType(str, Enum):
    """Supported service types"""
    WHISPER = "whisper"
    STABLE_DIFFUSION = "stable_diffusion"
    LLM_INFERENCE = "llm_inference"
    FFMPEG = "ffmpeg"
    BLENDER = "blender"


# Whisper Service Schemas
class WhisperModel(str, Enum):
    """Supported Whisper models"""
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    LARGE_V2 = "large-v2"
    LARGE_V3 = "large-v3"


class WhisperLanguage(str, Enum):
    """Supported languages"""
    AUTO = "auto"
    EN = "en"
    ES = "es"
    FR = "fr"
    DE = "de"
    IT = "it"
    PT = "pt"
    RU = "ru"
    JA = "ja"
    KO = "ko"
    ZH = "zh"


class WhisperTask(str, Enum):
    """Whisper task types"""
    TRANSCRIBE = "transcribe"
    TRANSLATE = "translate"


class WhisperRequest(BaseModel):
    """Whisper transcription request"""
    audio_url: str = Field(..., description="URL of audio file to transcribe")
    model: WhisperModel = Field(WhisperModel.BASE, description="Whisper model to use")
    language: WhisperLanguage = Field(WhisperLanguage.AUTO, description="Source language")
    task: WhisperTask = Field(WhisperTask.TRANSCRIBE, description="Task to perform")
    temperature: float = Field(0.0, ge=0.0, le=1.0, description="Sampling temperature")
    best_of: int = Field(5, ge=1, le=10, description="Number of candidates")
    beam_size: int = Field(5, ge=1, le=10, description="Beam size for decoding")
    patience: float = Field(1.0, ge=0.0, le=2.0, description="Beam search patience")
    suppress_tokens: Optional[List[int]] = Field(None, description="Tokens to suppress")
    initial_prompt: Optional[str] = Field(None, description="Initial prompt for context")
    condition_on_previous_text: bool = Field(True, description="Condition on previous text")
    fp16: bool = Field(True, description="Use FP16 for faster inference")
    verbose: bool = Field(False, description="Include verbose output")
    
    def get_constraints(self) -> Dict[str, Any]:
        """Get hardware constraints for this request"""
        vram_requirements = {
            WhisperModel.TINY: 1,
            WhisperModel.BASE: 1,
            WhisperModel.SMALL: 2,
            WhisperModel.MEDIUM: 5,
            WhisperModel.LARGE: 10,
            WhisperModel.LARGE_V2: 10,
            WhisperModel.LARGE_V3: 10,
        }
        
        return {
            "models": ["whisper"],
            "min_vram_gb": vram_requirements[self.model],
            "gpu": "nvidia",  # Whisper requires CUDA
        }


# Stable Diffusion Service Schemas
class SDModel(str, Enum):
    """Supported Stable Diffusion models"""
    SD_1_5 = "stable-diffusion-1.5"
    SD_2_1 = "stable-diffusion-2.1"
    SDXL = "stable-diffusion-xl"
    SDXL_TURBO = "sdxl-turbo"
    SDXL_REFINER = "sdxl-refiner"


class SDSize(str, Enum):
    """Standard image sizes"""
    SQUARE_512 = "512x512"
    PORTRAIT_512 = "512x768"
    LANDSCAPE_512 = "768x512"
    SQUARE_768 = "768x768"
    PORTRAIT_768 = "768x1024"
    LANDSCAPE_768 = "1024x768"
    SQUARE_1024 = "1024x1024"
    PORTRAIT_1024 = "1024x1536"
    LANDSCAPE_1024 = "1536x1024"


class StableDiffusionRequest(BaseModel):
    """Stable Diffusion image generation request"""
    prompt: str = Field(..., min_length=1, max_length=1000, description="Text prompt")
    negative_prompt: Optional[str] = Field(None, max_length=1000, description="Negative prompt")
    model: SDModel = Field(SDModel.SD_1_5, description="Model to use")
    size: SDSize = Field(SDSize.SQUARE_512, description="Image size")
    num_images: int = Field(1, ge=1, le=4, description="Number of images to generate")
    num_inference_steps: int = Field(20, ge=1, le=100, description="Number of inference steps")
    guidance_scale: float = Field(7.5, ge=1.0, le=20.0, description="Guidance scale")
    seed: Optional[Union[int, List[int]]] = Field(None, description="Random seed(s)")
    scheduler: str = Field("DPMSolverMultistepScheduler", description="Scheduler to use")
    enable_safety_checker: bool = Field(True, description="Enable safety checker")
    lora: Optional[str] = Field(None, description="LoRA model to use")
    lora_scale: float = Field(1.0, ge=0.0, le=2.0, description="LoRA strength")
    
    @validator('seed')
    def validate_seed(cls, v):
        if v is not None and isinstance(v, list):
            if len(v) > 4:
                raise ValueError("Maximum 4 seeds allowed")
        return v
    
    def get_constraints(self) -> Dict[str, Any]:
        """Get hardware constraints for this request"""
        vram_requirements = {
            SDModel.SD_1_5: 4,
            SDModel.SD_2_1: 4,
            SDModel.SDXL: 8,
            SDModel.SDXL_TURBO: 8,
            SDModel.SDXL_REFINER: 8,
        }
        
        size_map = {
            "512": 512,
            "768": 768,
            "1024": 1024,
            "1536": 1536,
        }
        
        # Extract max dimension from size
        max_dim = max(size_map[s.split('x')[0]] for s in SDSize)
        
        return {
            "models": ["stable-diffusion"],
            "min_vram_gb": vram_requirements[self.model],
            "gpu": "nvidia",  # SD requires CUDA
            "cuda": "11.8",  # Minimum CUDA version
        }


# LLM Inference Service Schemas
class LLMModel(str, Enum):
    """Supported LLM models"""
    LLAMA_7B = "llama-7b"
    LLAMA_13B = "llama-13b"
    LLAMA_70B = "llama-70b"
    MISTRAL_7B = "mistral-7b"
    MIXTRAL_8X7B = "mixtral-8x7b"
    CODELLAMA_7B = "codellama-7b"
    CODELLAMA_13B = "codellama-13b"
    CODELLAMA_34B = "codellama-34b"


class LLMRequest(BaseModel):
    """LLM inference request"""
    model: LLMModel = Field(..., description="Model to use")
    prompt: str = Field(..., min_length=1, max_length=10000, description="Input prompt")
    max_tokens: int = Field(256, ge=1, le=4096, description="Maximum tokens to generate")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: float = Field(0.9, ge=0.0, le=1.0, description="Top-p sampling")
    top_k: int = Field(40, ge=0, le=100, description="Top-k sampling")
    repetition_penalty: float = Field(1.1, ge=0.0, le=2.0, description="Repetition penalty")
    stop_sequences: Optional[List[str]] = Field(None, description="Stop sequences")
    stream: bool = Field(False, description="Stream response")
    
    def get_constraints(self) -> Dict[str, Any]:
        """Get hardware constraints for this request"""
        vram_requirements = {
            LLMModel.LLAMA_7B: 8,
            LLMModel.LLAMA_13B: 16,
            LLMModel.LLAMA_70B: 64,
            LLMModel.MISTRAL_7B: 8,
            LLMModel.MIXTRAL_8X7B: 48,
            LLMModel.CODELLAMA_7B: 8,
            LLMModel.CODELLAMA_13B: 16,
            LLMModel.CODELLAMA_34B: 32,
        }
        
        return {
            "models": ["llm"],
            "min_vram_gb": vram_requirements[self.model],
            "gpu": "nvidia",  # LLMs require CUDA
            "cuda": "11.8",
        }


# FFmpeg Service Schemas
class FFmpegCodec(str, Enum):
    """Supported video codecs"""
    H264 = "h264"
    H265 = "h265"
    VP9 = "vp9"
    AV1 = "av1"


class FFmpegPreset(str, Enum):
    """Encoding presets"""
    ULTRAFAST = "ultrafast"
    SUPERFAST = "superfast"
    VERYFAST = "veryfast"
    FASTER = "faster"
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    SLOWER = "slower"
    VERYSLOW = "veryslow"


class FFmpegRequest(BaseModel):
    """FFmpeg video processing request"""
    input_url: str = Field(..., description="URL of input video")
    output_format: str = Field("mp4", description="Output format")
    codec: FFmpegCodec = Field(FFmpegCodec.H264, description="Video codec")
    preset: FFmpegPreset = Field(FFmpegPreset.MEDIUM, description="Encoding preset")
    crf: int = Field(23, ge=0, le=51, description="Constant rate factor")
    resolution: Optional[str] = Field(None, pattern=r"^\d+x\d+$", description="Output resolution (e.g., 1920x1080)")
    bitrate: Optional[str] = Field(None, pattern=r"^\d+[kM]?$", description="Target bitrate")
    fps: Optional[int] = Field(None, ge=1, le=120, description="Output frame rate")
    audio_codec: str = Field("aac", description="Audio codec")
    audio_bitrate: str = Field("128k", description="Audio bitrate")
    custom_args: Optional[List[str]] = Field(None, description="Custom FFmpeg arguments")
    
    def get_constraints(self) -> Dict[str, Any]:
        """Get hardware constraints for this request"""
        # NVENC support for H.264/H.265
        if self.codec in [FFmpegCodec.H264, FFmpegCodec.H265]:
            return {
                "models": ["ffmpeg"],
                "gpu": "nvidia",  # NVENC requires NVIDIA
                "min_vram_gb": 4,
            }
        else:
            return {
                "models": ["ffmpeg"],
                "gpu": "any",  # CPU encoding possible
            }


# Blender Service Schemas
class BlenderEngine(str, Enum):
    """Blender render engines"""
    CYCLES = "cycles"
    EEVEE = "eevee"
    EEVEE_NEXT = "eevee-next"


class BlenderFormat(str, Enum):
    """Output formats"""
    PNG = "png"
    JPG = "jpg"
    EXR = "exr"
    BMP = "bmp"
    TIFF = "tiff"


class BlenderRequest(BaseModel):
    """Blender rendering request"""
    blend_file_url: str = Field(..., description="URL of .blend file")
    engine: BlenderEngine = Field(BlenderEngine.CYCLES, description="Render engine")
    format: BlenderFormat = Field(BlenderFormat.PNG, description="Output format")
    resolution_x: int = Field(1920, ge=1, le=65536, description="Image width")
    resolution_y: int = Field(1080, ge=1, le=65536, description="Image height")
    resolution_percentage: int = Field(100, ge=1, le=100, description="Resolution scale")
    samples: int = Field(128, ge=1, le=10000, description="Samples (Cycles only)")
    frame_start: int = Field(1, ge=1, description="Start frame")
    frame_end: int = Field(1, ge=1, description="End frame")
    frame_step: int = Field(1, ge=1, description="Frame step")
    denoise: bool = Field(True, description="Enable denoising")
    transparent: bool = Field(False, description="Transparent background")
    custom_args: Optional[List[str]] = Field(None, description="Custom Blender arguments")
    
    @validator('frame_end')
    def validate_frame_range(cls, v, values):
        if 'frame_start' in values and v < values['frame_start']:
            raise ValueError("frame_end must be >= frame_start")
        return v
    
    def get_constraints(self) -> Dict[str, Any]:
        """Get hardware constraints for this request"""
        # Calculate VRAM based on resolution and samples
        pixel_count = self.resolution_x * self.resolution_y
        samples_multiplier = 1 if self.engine == BlenderEngine.EEVEE else self.samples / 100
        
        estimated_vram = int((pixel_count * samples_multiplier) / (1024 * 1024))
        
        return {
            "models": ["blender"],
            "min_vram_gb": max(4, estimated_vram),
            "gpu": "nvidia" if self.engine == BlenderEngine.CYCLES else "any",
        }


# Unified Service Request
class ServiceRequest(BaseModel):
    """Unified service request wrapper"""
    service_type: ServiceType = Field(..., description="Type of service")
    request_data: Dict[str, Any] = Field(..., description="Service-specific request data")
    
    def get_service_request(self) -> Union[
        WhisperRequest,
        StableDiffusionRequest,
        LLMRequest,
        FFmpegRequest,
        BlenderRequest
    ]:
        """Parse and return typed service request"""
        service_classes = {
            ServiceType.WHISPER: WhisperRequest,
            ServiceType.STABLE_DIFFUSION: StableDiffusionRequest,
            ServiceType.LLM_INFERENCE: LLMRequest,
            ServiceType.FFMPEG: FFmpegRequest,
            ServiceType.BLENDER: BlenderRequest,
        }
        
        service_class = service_classes[self.service_type]
        return service_class(**self.request_data)


# Service Response Schemas
class ServiceResponse(BaseModel):
    """Base service response"""
    job_id: str = Field(..., description="Job ID")
    service_type: ServiceType = Field(..., description="Service type")
    status: str = Field(..., description="Job status")
    estimated_completion: Optional[str] = Field(None, description="Estimated completion time")


class WhisperResponse(BaseModel):
    """Whisper transcription response"""
    text: str = Field(..., description="Transcribed text")
    language: str = Field(..., description="Detected language")
    segments: Optional[List[Dict[str, Any]]] = Field(None, description="Transcription segments")


class StableDiffusionResponse(BaseModel):
    """Stable Diffusion image generation response"""
    images: List[str] = Field(..., description="Generated image URLs")
    parameters: Dict[str, Any] = Field(..., description="Generation parameters")
    nsfw_content_detected: List[bool] = Field(..., description="NSFW detection results")


class LLMResponse(BaseModel):
    """LLM inference response"""
    text: str = Field(..., description="Generated text")
    finish_reason: str = Field(..., description="Reason for generation stop")
    tokens_used: int = Field(..., description="Number of tokens used")


class FFmpegResponse(BaseModel):
    """FFmpeg processing response"""
    output_url: str = Field(..., description="URL of processed video")
    metadata: Dict[str, Any] = Field(..., description="Video metadata")
    duration: float = Field(..., description="Video duration")


class BlenderResponse(BaseModel):
    """Blender rendering response"""
    images: List[str] = Field(..., description="Rendered image URLs")
    metadata: Dict[str, Any] = Field(..., description="Render metadata")
    render_time: float = Field(..., description="Render time in seconds")
