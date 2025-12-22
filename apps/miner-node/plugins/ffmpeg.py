"""
FFmpeg video processing plugin
"""

import asyncio
import os
import subprocess
import tempfile
from typing import Dict, Any, List
import time

from .base import ServicePlugin, PluginResult
from .exceptions import PluginExecutionError


class FFmpegPlugin(ServicePlugin):
    """Plugin for FFmpeg video processing"""
    
    def __init__(self):
        super().__init__()
        self.service_id = "ffmpeg"
        self.name = "FFmpeg Video Processing"
        self.version = "1.0.0"
        self.description = "Transcode and process video files using FFmpeg"
        self.capabilities = ["transcode", "resize", "compress", "convert"]
    
    def setup(self) -> None:
        """Initialize FFmpeg dependencies"""
        # Check for ffmpeg installation
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            self.ffmpeg_path = "ffmpeg"
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise PluginExecutionError("FFmpeg not found. Install FFmpeg for video processing")
        
        # Check for NVIDIA GPU support
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                check=True
            )
            self.gpu_acceleration = "h264_nvenc" in result.stdout
        except subprocess.CalledProcessError:
            self.gpu_acceleration = False
    
    def validate_request(self, request: Dict[str, Any]) -> List[str]:
        """Validate FFmpeg request parameters"""
        errors = []
        
        # Check required parameters
        if "input_url" not in request and "input_file" not in request:
            errors.append("Either 'input_url' or 'input_file' must be provided")
        
        # Validate output format
        output_format = request.get("output_format", "mp4")
        valid_formats = ["mp4", "avi", "mov", "mkv", "webm", "flv"]
        if output_format not in valid_formats:
            errors.append(f"Invalid output format. Must be one of: {', '.join(valid_formats)}")
        
        # Validate codec
        codec = request.get("codec", "h264")
        valid_codecs = ["h264", "h265", "vp9", "av1", "mpeg4"]
        if codec not in valid_codecs:
            errors.append(f"Invalid codec. Must be one of: {', '.join(valid_codecs)}")
        
        # Validate resolution
        resolution = request.get("resolution")
        if resolution:
            valid_resolutions = ["720p", "1080p", "1440p", "4K", "8K"]
            if resolution not in valid_resolutions:
                errors.append(f"Invalid resolution. Must be one of: {', '.join(valid_resolutions)}")
        
        # Validate bitrate
        bitrate = request.get("bitrate")
        if bitrate:
            if not isinstance(bitrate, str) or not bitrate.endswith(("k", "M")):
                errors.append("Bitrate must end with 'k' or 'M' (e.g., '1000k', '5M')")
        
        # Validate frame rate
        fps = request.get("fps")
        if fps:
            if not isinstance(fps, (int, float)) or fps < 1 or fps > 120:
                errors.append("FPS must be between 1 and 120")
        
        return errors
    
    def get_hardware_requirements(self) -> Dict[str, Any]:
        """Get hardware requirements for FFmpeg"""
        return {
            "gpu": "optional",
            "vram_gb": 2,
            "ram_gb": 8,
            "storage_gb": 10
        }
    
    async def execute(self, request: Dict[str, Any]) -> PluginResult:
        """Execute FFmpeg processing"""
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
            input_source = request.get("input_url") or request.get("input_file")
            output_format = request.get("output_format", "mp4")
            codec = request.get("codec", "h264")
            resolution = request.get("resolution")
            bitrate = request.get("bitrate")
            fps = request.get("fps")
            gpu_acceleration = request.get("gpu_acceleration", self.gpu_acceleration)
            
            # Get input file
            input_file = await self._get_input_file(input_source)
            
            # Build FFmpeg command
            cmd = self._build_ffmpeg_command(
                input_file=input_file,
                output_format=output_format,
                codec=codec,
                resolution=resolution,
                bitrate=bitrate,
                fps=fps,
                gpu_acceleration=gpu_acceleration
            )
            
            # Execute FFmpeg
            output_file = await self._execute_ffmpeg(cmd)
            
            # Get output file info
            output_info = await self._get_video_info(output_file)
            
            # Clean up input file if downloaded
            if input_source != request.get("input_file"):
                os.unlink(input_file)
            
            execution_time = time.time() - start_time
            
            return PluginResult(
                success=True,
                data={
                    "output_file": output_file,
                    "output_info": output_info,
                    "parameters": {
                        "codec": codec,
                        "resolution": resolution,
                        "bitrate": bitrate,
                        "fps": fps,
                        "gpu_acceleration": gpu_acceleration
                    }
                },
                metrics={
                    "input_size": os.path.getsize(input_file),
                    "output_size": os.path.getsize(output_file),
                    "compression_ratio": os.path.getsize(output_file) / os.path.getsize(input_file),
                    "processing_time": execution_time,
                    "real_time_factor": output_info.get("duration", 0) / execution_time if execution_time > 0 else 0
                },
                execution_time=execution_time
            )
            
        except Exception as e:
            return PluginResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    async def _get_input_file(self, source: str) -> str:
        """Get input file from URL or path"""
        if source.startswith(("http://", "https://")):
            # Download from URL
            import requests
            
            response = requests.get(source, stream=True)
            response.raise_for_status()
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                return f.name
        else:
            # Local file
            if not os.path.exists(source):
                raise PluginExecutionError(f"Input file not found: {source}")
            return source
    
    def _build_ffmpeg_command(
        self,
        input_file: str,
        output_format: str,
        codec: str,
        resolution: Optional[str],
        bitrate: Optional[str],
        fps: Optional[float],
        gpu_acceleration: bool
    ) -> List[str]:
        """Build FFmpeg command"""
        cmd = [self.ffmpeg_path, "-i", input_file]
        
        # Add codec
        if gpu_acceleration and codec == "h264":
            cmd.extend(["-c:v", "h264_nvenc"])
            cmd.extend(["-preset", "fast"])
        elif gpu_acceleration and codec == "h265":
            cmd.extend(["-c:v", "hevc_nvenc"])
            cmd.extend(["-preset", "fast"])
        else:
            cmd.extend(["-c:v", codec])
        
        # Add resolution
        if resolution:
            resolution_map = {
                "720p": ("1280", "720"),
                "1080p": ("1920", "1080"),
                "1440p": ("2560", "1440"),
                "4K": ("3840", "2160"),
                "8K": ("7680", "4320")
            }
            width, height = resolution_map.get(resolution, (None, None))
            if width and height:
                cmd.extend(["-s", f"{width}x{height}"])
        
        # Add bitrate
        if bitrate:
            cmd.extend(["-b:v", bitrate])
            cmd.extend(["-b:a", "128k"])  # Audio bitrate
        
        # Add FPS
        if fps:
            cmd.extend(["-r", str(fps)])
        
        # Add audio codec
        cmd.extend(["-c:a", "aac"])
        
        # Output file
        output_file = tempfile.mktemp(suffix=f".{output_format}")
        cmd.append(output_file)
        
        return cmd
    
    async def _execute_ffmpeg(self, cmd: List[str]) -> str:
        """Execute FFmpeg command"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "FFmpeg failed"
            raise PluginExecutionError(f"FFmpeg error: {error_msg}")
        
        # Output file is the last argument
        return cmd[-1]
    
    async def _get_video_info(self, video_file: str) -> Dict[str, Any]:
        """Get video file information"""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_file
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            return {}
        
        import json
        probe_data = json.loads(stdout.decode())
        
        # Extract relevant info
        video_stream = next(
            (s for s in probe_data.get("streams", []) if s.get("codec_type") == "video"),
            {}
        )
        
        return {
            "duration": float(probe_data.get("format", {}).get("duration", 0)),
            "size": int(probe_data.get("format", {}).get("size", 0)),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "fps": eval(video_stream.get("r_frame_rate", "0/1")),
            "codec": video_stream.get("codec_name"),
            "bitrate": int(probe_data.get("format", {}).get("bit_rate", 0))
        }
    
    async def health_check(self) -> bool:
        """Check FFmpeg health"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False
