"""
Whisper speech recognition plugin
"""

import asyncio
import os
import tempfile
from typing import Dict, Any, List
import time

from .base import GPUPlugin, PluginResult
from .exceptions import PluginExecutionError


class WhisperPlugin(GPUPlugin):
    """Plugin for Whisper speech recognition"""
    
    def __init__(self):
        super().__init__()
        self.service_id = "whisper"
        self.name = "Whisper Speech Recognition"
        self.version = "1.0.0"
        self.description = "Transcribe and translate audio files using OpenAI Whisper"
        self.capabilities = ["transcribe", "translate"]
        self._model_cache = {}
    
    def setup(self) -> None:
        """Initialize Whisper dependencies"""
        super().setup()
        
        # Check for whisper installation
        try:
            import whisper
            self.whisper = whisper
        except ImportError:
            raise PluginExecutionError("Whisper not installed. Install with: pip install openai-whisper")
        
        # Check for ffmpeg
        import subprocess
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise PluginExecutionError("FFmpeg not found. Install FFmpeg for audio processing")
    
    def validate_request(self, request: Dict[str, Any]) -> List[str]:
        """Validate Whisper request parameters"""
        errors = []
        
        # Check required parameters
        if "audio_url" not in request and "audio_file" not in request:
            errors.append("Either 'audio_url' or 'audio_file' must be provided")
        
        # Validate model
        model = request.get("model", "base")
        valid_models = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]
        if model not in valid_models:
            errors.append(f"Invalid model. Must be one of: {', '.join(valid_models)}")
        
        # Validate task
        task = request.get("task", "transcribe")
        if task not in ["transcribe", "translate"]:
            errors.append("Task must be 'transcribe' or 'translate'")
        
        # Validate language
        if "language" in request:
            language = request["language"]
            if not isinstance(language, str) or len(language) != 2:
                errors.append("Language must be a 2-letter language code (e.g., 'en', 'es')")
        
        return errors
    
    def get_hardware_requirements(self) -> Dict[str, Any]:
        """Get hardware requirements for Whisper"""
        return {
            "gpu": "recommended",
            "vram_gb": 2,
            "ram_gb": 4,
            "storage_gb": 1
        }
    
    async def execute(self, request: Dict[str, Any]) -> PluginResult:
        """Execute Whisper transcription"""
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
            model_name = request.get("model", "base")
            task = request.get("task", "transcribe")
            language = request.get("language")
            temperature = request.get("temperature", 0.0)
            
            # Load or get cached model
            model = await self._load_model(model_name)
            
            # Get audio file
            audio_path = await self._get_audio_file(request)
            
            # Transcribe
            loop = asyncio.get_event_loop()
            
            if task == "translate":
                result = await loop.run_in_executor(
                    None,
                    lambda: model.transcribe(
                        audio_path,
                        task="translate",
                        temperature=temperature
                    )
                )
            else:
                result = await loop.run_in_executor(
                    None,
                    lambda: model.transcribe(
                        audio_path,
                        language=language,
                        temperature=temperature
                    )
                )
            
            # Clean up
            if audio_path != request.get("audio_file"):
                os.unlink(audio_path)
            
            execution_time = time.time() - start_time
            
            return PluginResult(
                success=True,
                data={
                    "text": result["text"],
                    "language": result.get("language"),
                    "segments": result.get("segments", [])
                },
                metrics={
                    "model": model_name,
                    "task": task,
                    "audio_duration": result.get("duration"),
                    "processing_time": execution_time,
                    "real_time_factor": result.get("duration", 0) / execution_time if execution_time > 0 else 0
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
        """Load Whisper model with caching"""
        if model_name not in self._model_cache:
            loop = asyncio.get_event_loop()
            model = await loop.run_in_executor(
                None,
                lambda: self.whisper.load_model(model_name)
            )
            self._model_cache[model_name] = model
        
        return self._model_cache[model_name]
    
    async def _get_audio_file(self, request: Dict[str, Any]) -> str:
        """Get audio file from URL or direct file path"""
        if "audio_file" in request:
            return request["audio_file"]
        
        # Download from URL
        audio_url = request["audio_url"]
        
        # Use requests to download
        import requests
        
        response = requests.get(audio_url, stream=True)
        response.raise_for_status()
        
        # Save to temporary file
        suffix = self._get_audio_suffix(audio_url)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
            return f.name
    
    def _get_audio_suffix(self, url: str) -> str:
        """Get file extension from URL"""
        if url.endswith('.mp3'):
            return '.mp3'
        elif url.endswith('.wav'):
            return '.wav'
        elif url.endswith('.m4a'):
            return '.m4a'
        elif url.endswith('.flac'):
            return '.flac'
        else:
            return '.mp3'  # Default
    
    async def health_check(self) -> bool:
        """Check Whisper health"""
        try:
            # Check if we can load the tiny model
            await self._load_model("tiny")
            return True
        except Exception:
            return False
    
    def cleanup(self) -> None:
        """Cleanup resources"""
        self._model_cache.clear()
