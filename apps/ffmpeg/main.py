from typing import Annotated

"""
AITBC FFmpeg Video Processing Service
FastAPI service wrapping FFmpeg with GPU acceleration (NVENC/NVDEC)
Port: 8230
"""

import hashlib
import os
import subprocess
import tempfile
import time
from contextlib import asynccontextmanager

import uvicorn  # noqa: E402
from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

_device = os.getenv("FFMPEG_GPU_DEVICE", "0")
_hw_accel = os.getenv("FFMPEG_HW_ACCEL", "cuda")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FFmpeg service"""
    # Verify FFmpeg with GPU support is available
    try:
        result = subprocess.run(["ffmpeg", "-hwaccels"], capture_output=True, text=True, timeout=5)
        if _hw_accel not in result.stdout:
            print(f"Warning: {_hw_accel} hardware acceleration not available in FFmpeg")
        else:
            print(f"FFmpeg service ready with {_hw_accel} hardware acceleration")
    except Exception as e:
        print(f"Warning: FFmpeg not available: {e}")
    yield


app = FastAPI(title="AITBC FFmpeg Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint"""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        return {
            "status": "ok",
            "service": "ffmpeg",
            "gpu_device": _device,
            "hw_accel": _hw_accel,
            "ready": result.returncode == 0,
        }
    except Exception as e:
        return {
            "status": "error",
            "service": "ffmpeg",
            "error": str(e),
            "ready": False,
        }


@app.get("/capabilities")
async def capabilities():
    """List supported codecs, formats, and GPU info"""
    try:
        # Get GPU info
        gpu_info = {}
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                gpu_info = {
                    "name": result.stdout.strip().split(",")[0],
                    "memory": result.stdout.strip().split(",")[1] if "," in result.stdout else "Unknown",
                }
        except Exception:
            pass

        # Get supported encoders
        encoders = []
        try:
            result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                # Parse encoders (focus on hardware encoders)
                for line in result.stdout.split("\n"):
                    if "h264" in line.lower() or "hevc" in line.lower():
                        encoders.append(line.strip())
        except Exception:
            pass

        return {
            "gpu": gpu_info,
            "hw_accel": _hw_accel,
            "supported_encoders": encoders[:20],  # Limit to first 20
            "gpu_device": _device,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get capabilities: {e}") from e


@app.post("/process")
async def process_video(
    file: Annotated[UploadFile, File(...)],
    output_format: str = Form(default="mp4"),
    codec: str = Form(default="h264"),
    resolution: str = Form(default="1080p"),
    bitrate: str = Form(default="5M"),
):
    """Process video with GPU acceleration"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Validate GPU acceleration is available
    try:
        result = subprocess.run(["ffmpeg", "-hwaccels"], capture_output=True, text=True, timeout=5)
        if _hw_accel not in result.stdout:
            raise HTTPException(status_code=503, detail=f"Hardware acceleration {_hw_accel} not available")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"FFmpeg not available: {e}") from e

    # Create temporary files
    suffix = os.path.splitext(file.filename or "video.mp4")[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as input_tmp:
        input_tmp.write(await file.read())
        input_path = input_tmp.name

    output_suffix = f".{output_format}"
    with tempfile.NamedTemporaryFile(suffix=output_suffix, delete=False) as output_tmp:
        output_path = output_tmp.name

    try:
        t_start = time.time()

        # Build FFmpeg command with GPU acceleration
        cmd = [
            "ffmpeg",
            "-hwaccel",
            _hw_accel,
            "-i",
            input_path,
            "-c:v",
            f"{_hw_accel}_{codec}",
            "-preset",
            "p6",  # Slow preset for quality
            "-b:v",
            bitrate,
            "-maxrate",
            bitrate,
            "-bufsize",
            f"{bitrate}M",
        ]

        # Add resolution scaling if specified
        if resolution == "1080p":
            cmd.extend(["-vf", "scale=1920:1080"])
        elif resolution == "720p":
            cmd.extend(["-vf", "scale=1280:720"])
        elif resolution == "480p":
            cmd.extend(["-vf", "scale=854:480"])

        cmd.extend(["-y", output_path])

        # Run FFmpeg
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
        )

        elapsed = round(time.time() - t_start, 2)

        if process.returncode != 0:
            raise HTTPException(status_code=500, detail=f"FFmpeg processing failed: {process.stderr}")

        # Calculate result hash
        with open(output_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # Get file size
        file_size = os.path.getsize(output_path)

        return JSONResponse(
            {
                "status": "completed",
                "output_path": output_path,
                "file_size_bytes": file_size,
                "processing_time_seconds": elapsed,
                "processing_time_hours": round(elapsed / 3600, 4),
                "codec": codec,
                "resolution": resolution,
                "bitrate": bitrate,
                "result_hash": file_hash,
                "gpu_device": _device,
                "hw_accel": _hw_accel,
            }
        )

    finally:
        # Cleanup input file
        if os.path.exists(input_path):
            os.unlink(input_path)
        # Note: output file is kept for the caller to retrieve
        # Caller should delete it after use


if __name__ == "__main__":
    import os

    # Standardized environment variable naming: SERVICE_BIND_HOST and SERVICE_BIND_PORT
    host = os.getenv("FFMPEG_BIND_HOST", "0.0.0.0")
    port = int(os.getenv("FFMPEG_BIND_PORT", os.getenv("FFMPEG_PORT", "8230")))

    uvicorn.run(app, host=host, port=port)
