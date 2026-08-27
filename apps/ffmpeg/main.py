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

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.health_checks import create_simple_health_response  # noqa: E402

configure_logging(level="INFO", service_name="ffmpeg", to_file=True)
logger = get_logger(__name__)

_device = os.getenv("FFMPEG_GPU_DEVICE", "0")
_hw_accel = os.getenv("FFMPEG_HW_ACCEL", "cuda")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FFmpeg service"""
    # Verify FFmpeg with GPU support is available
    try:
        result = subprocess.run(["ffmpeg", "-hwaccels"], capture_output=True, text=True, timeout=5)
        if _hw_accel not in result.stdout:
            logger.warning(f"{_hw_accel} hardware acceleration not available in FFmpeg")
        else:
            logger.info(f"FFmpeg service ready with {_hw_accel} hardware acceleration")
    except Exception as e:
        logger.warning(f"FFmpeg not available: {e}")
    yield


app = FastAPI(title="AITBC FFmpeg Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint"""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        return create_simple_health_response(
            "ffmpeg",
            status="ok",
            gpu_device=_device,
            hw_accel=_hw_accel,
            ready=result.returncode == 0,
        )
    except Exception as e:
        return create_simple_health_response(
            "ffmpeg",
            status="error",
            error=str(e),
            ready=False,
        )


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
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


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
            logger.exception("Unhandled exception")

            raise HTTPException(status_code=503, detail="Internal server error")
    except Exception as e:
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=503, detail="Internal server error") from e

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

        # Map requested codec to an FFmpeg encoder name.
        # `codec` from the CLI is a short label like "h264" or "hevc"; the actual
        # encoder depends on the accelerator (nvenc for NVIDIA cuda, vaapi for AMD/Intel, etc.).
        codec_key = codec.lower()
        if _hw_accel == "cuda":
            encoder = f"{codec_key}_nvenc"
        elif _hw_accel == "vaapi":
            encoder = f"{codec_key}_vaapi"
        elif _hw_accel == "qsv":
            encoder = f"{codec_key}_qsv"
        elif codec_key == "h264":
            encoder = "libx264"
        elif codec_key == "hevc":
            encoder = "libx265"
        else:
            encoder = codec_key

        # Ensure bitrate has a valid unit (k/M) and compute the VBV buffer size.
        bitrate_value = bitrate.strip()
        if not bitrate_value[-1].isalpha():
            bitrate_value = f"{bitrate_value}M"
        # bufsize: use the numeric value, defaulting to the same unit as the rate.
        numeric = "".join(c for c in bitrate_value if c.isdigit() or c == ".")
        unit = bitrate_value[-1].lower() if bitrate_value[-1].isalpha() else "m"
        bufsize = f"{numeric}{unit}"

        # Build FFmpeg command. Hardware-accelerated decode + encode when possible.
        cmd = [
            "ffmpeg",
            "-hwaccel",
            _hw_accel,
            "-i",
            input_path,
            "-c:v",
            encoder,
            "-preset",
            "p6" if "_nvenc" in encoder else "medium",
            "-b:v",
            bitrate_value,
            "-maxrate",
            bitrate_value,
            "-bufsize",
            bufsize,
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
            logger.exception("Unhandled exception")

            raise HTTPException(status_code=500, detail="Internal server error")

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
    host = os.getenv("FFMPEG_BIND_HOST", "0.0.0.0")  # nosec B104 - intentional service bind-all; AITBC's systemd-only (Docker-free) services bind broadly by design, real boundary is the firewall/reverse-proxy layer
    port = int(os.getenv("FFMPEG_BIND_PORT", os.getenv("FFMPEG_PORT", "8230")))

    uvicorn.run(app, host=host, port=port, log_level="critical", access_log=False)
