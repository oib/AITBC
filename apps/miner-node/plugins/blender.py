"""
Blender 3D rendering plugin
"""

import asyncio
import os
import subprocess
import tempfile
import json
from typing import Dict, Any, List, Optional
import time

from .base import GPUPlugin, PluginResult
from .exceptions import PluginExecutionError


class BlenderPlugin(GPUPlugin):
    """Plugin for Blender 3D rendering"""
    
    def __init__(self):
        super().__init__()
        self.service_id = "blender"
        self.name = "Blender Rendering"
        self.version = "1.0.0"
        self.description = "Render 3D scenes using Blender"
        self.capabilities = ["render", "animation", "cycles", "eevee"]
    
    def setup(self) -> None:
        """Initialize Blender dependencies"""
        super().setup()
        
        # Check for Blender installation
        try:
            result = subprocess.run(
                ["blender", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            self.blender_path = "blender"
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise PluginExecutionError("Blender not found. Install Blender for 3D rendering")
        
        # Check for bpy module (Python API)
        try:
            import bpy
            self.bpy_available = True
        except ImportError:
            self.bpy_available = False
            print("Warning: bpy module not available. Some features may be limited.")
    
    def validate_request(self, request: Dict[str, Any]) -> List[str]:
        """Validate Blender request parameters"""
        errors = []
        
        # Check required parameters
        if "blend_file" not in request and "scene_data" not in request:
            errors.append("Either 'blend_file' or 'scene_data' must be provided")
        
        # Validate engine
        engine = request.get("engine", "cycles")
        valid_engines = ["cycles", "eevee", "workbench"]
        if engine not in valid_engines:
            errors.append(f"Invalid engine. Must be one of: {', '.join(valid_engines)}")
        
        # Validate resolution
        resolution_x = request.get("resolution_x", 1920)
        resolution_y = request.get("resolution_y", 1080)
        
        if not isinstance(resolution_x, int) or resolution_x < 1 or resolution_x > 65536:
            errors.append("resolution_x must be an integer between 1 and 65536")
        if not isinstance(resolution_y, int) or resolution_y < 1 or resolution_y > 65536:
            errors.append("resolution_y must be an integer between 1 and 65536")
        
        # Validate samples
        samples = request.get("samples", 128)
        if not isinstance(samples, int) or samples < 1 or samples > 10000:
            errors.append("samples must be an integer between 1 and 10000")
        
        # Validate frame range for animation
        if request.get("animation", False):
            frame_start = request.get("frame_start", 1)
            frame_end = request.get("frame_end", 250)
            
            if not isinstance(frame_start, int) or frame_start < 1:
                errors.append("frame_start must be >= 1")
            if not isinstance(frame_end, int) or frame_end < frame_start:
                errors.append("frame_end must be >= frame_start")
        
        return errors
    
    def get_hardware_requirements(self) -> Dict[str, Any]:
        """Get hardware requirements for Blender"""
        return {
            "gpu": "recommended",
            "vram_gb": 4,
            "ram_gb": 16,
            "cuda": "recommended"
        }
    
    async def execute(self, request: Dict[str, Any]) -> PluginResult:
        """Execute Blender rendering"""
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
            blend_file = request.get("blend_file")
            scene_data = request.get("scene_data")
            engine = request.get("engine", "cycles")
            resolution_x = request.get("resolution_x", 1920)
            resolution_y = request.get("resolution_y", 1080)
            samples = request.get("samples", 128)
            animation = request.get("animation", False)
            frame_start = request.get("frame_start", 1)
            frame_end = request.get("frame_end", 250)
            output_format = request.get("output_format", "png")
            gpu_acceleration = request.get("gpu_acceleration", self.gpu_available)
            
            # Prepare input file
            input_file = await self._prepare_input_file(blend_file, scene_data)
            
            # Build Blender command
            cmd = self._build_blender_command(
                input_file=input_file,
                engine=engine,
                resolution_x=resolution_x,
                resolution_y=resolution_y,
                samples=samples,
                animation=animation,
                frame_start=frame_start,
                frame_end=frame_end,
                output_format=output_format,
                gpu_acceleration=gpu_acceleration
            )
            
            # Execute Blender
            output_files = await self._execute_blender(cmd, animation, frame_start, frame_end)
            
            # Get render statistics
            render_stats = await self._get_render_stats(output_files[0] if output_files else None)
            
            # Clean up input file if created from scene data
            if scene_data:
                os.unlink(input_file)
            
            execution_time = time.time() - start_time
            
            return PluginResult(
                success=True,
                data={
                    "output_files": output_files,
                    "count": len(output_files),
                    "animation": animation,
                    "parameters": {
                        "engine": engine,
                        "resolution": f"{resolution_x}x{resolution_y}",
                        "samples": samples,
                        "gpu_acceleration": gpu_acceleration
                    }
                },
                metrics={
                    "engine": engine,
                    "frames_rendered": len(output_files),
                    "render_time": execution_time,
                    "time_per_frame": execution_time / len(output_files) if output_files else 0,
                    "samples_per_second": (samples * len(output_files)) / execution_time if execution_time > 0 else 0,
                    "render_stats": render_stats
                },
                execution_time=execution_time
            )
            
        except Exception as e:
            return PluginResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    async def _prepare_input_file(self, blend_file: Optional[str], scene_data: Optional[Dict]) -> str:
        """Prepare input .blend file"""
        if blend_file:
            # Use provided file
            if not os.path.exists(blend_file):
                raise PluginExecutionError(f"Blend file not found: {blend_file}")
            return blend_file
        elif scene_data:
            # Create blend file from scene data
            if not self.bpy_available:
                raise PluginExecutionError("Cannot create scene without bpy module")
            
            # Create a temporary Python script to generate the scene
            script = tempfile.mktemp(suffix=".py")
            output_blend = tempfile.mktemp(suffix=".blend")
            
            with open(script, "w") as f:
                f.write(f"""
import bpy
import json

# Load scene data
scene_data = json.loads('''{json.dumps(scene_data)}''')

# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Create scene from data
# This is a simplified example - in practice, you'd parse the scene_data
# and create appropriate objects, materials, lights, etc.

# Save blend file
bpy.ops.wm.save_as_mainfile(filepath='{output_blend}')
""")
            
            # Run Blender to create the scene
            cmd = [self.blender_path, "--background", "--python", script]
            process = await asyncio.create_subprocess_exec(*cmd)
            await process.communicate()
            
            # Clean up script
            os.unlink(script)
            
            return output_blend
        else:
            raise PluginExecutionError("Either blend_file or scene_data must be provided")
    
    def _build_blender_command(
        self,
        input_file: str,
        engine: str,
        resolution_x: int,
        resolution_y: int,
        samples: int,
        animation: bool,
        frame_start: int,
        frame_end: int,
        output_format: str,
        gpu_acceleration: bool
    ) -> List[str]:
        """Build Blender command"""
        cmd = [
            self.blender_path,
            "--background",
            input_file,
            "--render-engine", engine,
            "--render-format", output_format.upper()
        ]
        
        # Add Python script for settings
        script = tempfile.mktemp(suffix=".py")
        with open(script, "w") as f:
            f.write(f"""
import bpy

# Set resolution
bpy.context.scene.render.resolution_x = {resolution_x}
bpy.context.scene.render.resolution_y = {resolution_y}

# Set samples for Cycles
if bpy.context.scene.render.engine == 'CYCLES':
    bpy.context.scene.cycles.samples = {samples}
    
    # Enable GPU rendering if available
    if {str(gpu_acceleration).lower()}:
        bpy.context.scene.cycles.device = 'GPU'
        preferences = bpy.context.preferences
        cycles_preferences = preferences.addons['cycles'].preferences
        cycles_preferences.compute_device_type = 'CUDA'
        cycles_preferences.get_devices()
        for device in cycles_preferences.devices:
            device.use = True

# Set frame range for animation
if {str(animation).lower()}:
    bpy.context.scene.frame_start = {frame_start}
    bpy.context.scene.frame_end = {frame_end}

# Set output path
bpy.context.scene.render.filepath = '{tempfile.mkdtemp()}/render_'

# Save settings
bpy.ops.wm.save_mainfile()
""")
        
        cmd.extend(["--python", script])
        
        # Add render command
        if animation:
            cmd.extend(["-a"])  # Render animation
        else:
            cmd.extend(["-f", "1"])  # Render single frame
        
        return cmd
    
    async def _execute_blender(
        self, 
        cmd: List[str], 
        animation: bool, 
        frame_start: int, 
        frame_end: int
    ) -> List[str]:
        """Execute Blender command"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Blender failed"
            raise PluginExecutionError(f"Blender error: {error_msg}")
        
        # Find output files
        output_dir = tempfile.mkdtemp()
        output_pattern = os.path.join(output_dir, "render_*")
        
        if animation:
            # Animation creates multiple files
            import glob
            output_files = glob.glob(output_pattern)
            output_files.sort()  # Ensure frame order
        else:
            # Single frame
            output_files = [glob.glob(output_pattern)[0]]
        
        return output_files
    
    async def _get_render_stats(self, output_file: Optional[str]) -> Dict[str, Any]:
        """Get render statistics"""
        if not output_file or not os.path.exists(output_file):
            return {}
        
        # Get file size and basic info
        file_size = os.path.getsize(output_file)
        
        # Try to get image dimensions
        try:
            from PIL import Image
            with Image.open(output_file) as img:
                width, height = img.size
        except:
            width = height = None
        
        return {
            "file_size": file_size,
            "width": width,
            "height": height,
            "format": os.path.splitext(output_file)[1][1:].upper()
        }
    
    async def health_check(self) -> bool:
        """Check Blender health"""
        try:
            result = subprocess.run(
                ["blender", "--version"],
                capture_output=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False
