"""
Stable Diffusion image generation plugin
"""

import asyncio
import base64
import io
from typing import Dict, Any, List
import time
import numpy as np

from .base import GPUPlugin, PluginResult
from .exceptions import PluginExecutionError


class StableDiffusionPlugin(GPUPlugin):
    """Plugin for Stable Diffusion image generation"""
    
    def __init__(self):
        super().__init__()
        self.service_id = "stable_diffusion"
        self.name = "Stable Diffusion"
        self.version = "1.0.0"
        self.description = "Generate images from text prompts using Stable Diffusion"
        self.capabilities = ["txt2img", "img2img"]
        self._model_cache = {}
    
    def setup(self) -> None:
        """Initialize Stable Diffusion dependencies"""
        super().setup()
        
        # Check for diffusers installation
        try:
            from diffusers import StableDiffusionPipeline, StableDiffusionImg2ImgPipeline
            self.diffusers = StableDiffusionPipeline
            self.img2img_pipe = StableDiffusionImg2ImgPipeline
        except ImportError:
            raise PluginExecutionError("Diffusers not installed. Install with: pip install diffusers transformers accelerate")
        
        # Check for torch
        try:
            import torch
            self.torch = torch
        except ImportError:
            raise PluginExecutionError("PyTorch not installed. Install with: pip install torch")
        
        # Check for PIL
        try:
            from PIL import Image
            self.Image = Image
        except ImportError:
            raise PluginExecutionError("PIL not installed. Install with: pip install Pillow")
    
    def validate_request(self, request: Dict[str, Any]) -> List[str]:
        """Validate Stable Diffusion request parameters"""
        errors = []
        
        # Check required parameters
        if "prompt" not in request:
            errors.append("'prompt' is required")
        
        # Validate model
        model = request.get("model", "runwayml/stable-diffusion-v1-5")
        valid_models = [
            "runwayml/stable-diffusion-v1-5",
            "stabilityai/stable-diffusion-2-1",
            "stabilityai/stable-diffusion-xl-base-1.0"
        ]
        if model not in valid_models:
            errors.append(f"Invalid model. Must be one of: {', '.join(valid_models)}")
        
        # Validate dimensions
        width = request.get("width", 512)
        height = request.get("height", 512)
        
        if not isinstance(width, int) or width < 256 or width > 1024:
            errors.append("Width must be an integer between 256 and 1024")
        if not isinstance(height, int) or height < 256 or height > 1024:
            errors.append("Height must be an integer between 256 and 1024")
        
        # Validate steps
        steps = request.get("steps", 20)
        if not isinstance(steps, int) or steps < 1 or steps > 100:
            errors.append("Steps must be an integer between 1 and 100")
        
        # Validate guidance scale
        guidance_scale = request.get("guidance_scale", 7.5)
        if not isinstance(guidance_scale, (int, float)) or guidance_scale < 1.0 or guidance_scale > 20.0:
            errors.append("Guidance scale must be between 1.0 and 20.0")
        
        # Check img2img requirements
        if request.get("task") == "img2img":
            if "init_image" not in request:
                errors.append("'init_image' is required for img2img task")
            strength = request.get("strength", 0.8)
            if not isinstance(strength, (int, float)) or strength < 0.0 or strength > 1.0:
                errors.append("Strength must be between 0.0 and 1.0")
        
        return errors
    
    def get_hardware_requirements(self) -> Dict[str, Any]:
        """Get hardware requirements for Stable Diffusion"""
        return {
            "gpu": "required",
            "vram_gb": 6,
            "ram_gb": 8,
            "cuda": "required"
        }
    
    async def execute(self, request: Dict[str, Any]) -> PluginResult:
        """Execute Stable Diffusion generation"""
        start_time = time.time()
        
        try:
            # Validate request
            errors = self.validate_request(request)
            if errors:
                return PluginResult(
                    success=False,
                    error=f"Validation failed: {'; '.join(errors)}"
                )
            
            # Get parameters
            prompt = request["prompt"]
            negative_prompt = request.get("negative_prompt", "")
            model_name = request.get("model", "runwayml/stable-diffusion-v1-5")
            width = request.get("width", 512)
            height = request.get("height", 512)
            steps = request.get("steps", 20)
            guidance_scale = request.get("guidance_scale", 7.5)
            num_images = request.get("num_images", 1)
            seed = request.get("seed")
            task = request.get("task", "txt2img")
            
            # Load model
            pipe = await self._load_model(model_name)
            
            # Generate images
            loop = asyncio.get_event_loop()
            
            if task == "img2img":
                # Handle img2img
                init_image_data = request["init_image"]
                init_image = self._decode_image(init_image_data)
                strength = request.get("strength", 0.8)
                
                images = await loop.run_in_executor(
                    None,
                    lambda: pipe(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        image=init_image,
                        strength=strength,
                        num_inference_steps=steps,
                        guidance_scale=guidance_scale,
                        num_images_per_prompt=num_images,
                        generator=self._get_generator(seed)
                    ).images
                )
            else:
                # Handle txt2img
                images = await loop.run_in_executor(
                    None,
                    lambda: pipe(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        width=width,
                        height=height,
                        num_inference_steps=steps,
                        guidance_scale=guidance_scale,
                        num_images_per_prompt=num_images,
                        generator=self._get_generator(seed)
                    ).images
                )
            
            # Encode images to base64
            encoded_images = []
            for img in images:
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                encoded_images.append(base64.b64encode(buffer.getvalue()).decode())
            
            execution_time = time.time() - start_time
            
            return PluginResult(
                success=True,
                data={
                    "images": encoded_images,
                    "count": len(images),
                    "parameters": {
                        "prompt": prompt,
                        "width": width,
                        "height": height,
                        "steps": steps,
                        "guidance_scale": guidance_scale,
                        "seed": seed
                    }
                },
                metrics={
                    "model": model_name,
                    "task": task,
                    "images_generated": len(images),
                    "generation_time": execution_time,
                    "time_per_image": execution_time / len(images)
                },
                execution_time=execution_time
            )
            
        except Exception as e:
            return PluginResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    async def _load_model(self, model_name: str):
        """Load Stable Diffusion model with caching"""
        if model_name not in self._model_cache:
            loop = asyncio.get_event_loop()
            
            # Determine device
            device = "cuda" if self.torch.cuda.is_available() else "cpu"
            
            # Load with attention slicing for memory efficiency
            pipe = await loop.run_in_executor(
                None,
                lambda: self.diffusers.from_pretrained(
                    model_name,
                    torch_dtype=self.torch.float16 if device == "cuda" else self.torch.float32,
                    safety_checker=None,
                    requires_safety_checker=False
                )
            )
            
            pipe = pipe.to(device)
            
            # Enable memory optimizations
            if device == "cuda":
                pipe.enable_attention_slicing()
                if self.vram_gb < 8:
                    pipe.enable_model_cpu_offload()
            
            self._model_cache[model_name] = pipe
        
        return self._model_cache[model_name]
    
    def _decode_image(self, image_data: str) -> 'Image':
        """Decode base64 image"""
        if image_data.startswith('data:image'):
            # Remove data URL prefix
            image_data = image_data.split(',')[1]
        
        image_bytes = base64.b64decode(image_data)
        return self.Image.open(io.BytesIO(image_bytes))
    
    def _get_generator(self, seed: Optional[int]):
        """Get torch generator for reproducible results"""
        if seed is not None:
            return self.torch.Generator().manual_seed(seed)
        return None
    
    async def health_check(self) -> bool:
        """Check Stable Diffusion health"""
        try:
            # Try to load a small model
            pipe = await self._load_model("runwayml/stable-diffusion-v1-5")
            return pipe is not None
        except Exception:
            return False
    
    def cleanup(self) -> None:
        """Cleanup resources"""
        # Move models to CPU and clear cache
        for pipe in self._model_cache.values():
            if hasattr(pipe, 'to'):
                pipe.to("cpu")
        self._model_cache.clear()
        
        # Clear GPU cache
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()
