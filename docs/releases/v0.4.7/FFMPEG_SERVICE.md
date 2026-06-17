# FFmpeg Video Processing Service - v0.4.7

**Release**: v0.4.7
**Date**: June 5, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.7 introduces a new FFmpeg video processing service with GPU acceleration, enabling GPU-accelerated video processing as a metered service.

## Features

### Service Endpoints
- `GET /health` — Service health check
- `GET /capabilities` — List supported codecs, formats, GPU info
- `POST /process` — Process video with GPU acceleration

### Capabilities Endpoint
```bash
curl http://localhost:8230/capabilities
```
Returns:
```json
{
  "gpu": {
    "name": "NVIDIA GeForce RTX 4060 Ti",
    "memory": "16380 MiB"
  },
  "hw_accel": "cuda",
  "supported_encoders": ["..."],
  "gpu_device": "0"
}
```

### Process Endpoint
```bash
curl -X POST http://localhost:8230/process \
  -F "file=@input.mp4" \
  -F "output_format=mp4" \
  -F "codec=h264" \
  -F "resolution=1080p" \
  -F "bitrate=5M"
```
Returns:
```json
{
  "status": "completed",
  "output_path": "/tmp/...",
  "file_size_bytes": 12345678,
  "processing_time_seconds": 45.67,
  "processing_time_hours": 0.0127,
  "codec": "h264",
  "resolution": "1080p",
  "bitrate": "5M",
  "result_hash": "abc123...",
  "gpu_device": "0",
  "hw_accel": "cuda"
}
```

### CLI Command
```bash
# Register FFmpeg offer
aitbc market offer ffmpeg default 0.15 --unit per_processing_hour

# Process video
aitbc market process <offer_id> input.mp4 --format mp4 --codec h264 --resolution 1080p --bitrate 5M
```

### On-Chain Proof of Work
FFmpeg service returns `result_hash` (SHA256 of output file). The `market process` command posts a `software_job` transaction on-chain with:
- job_id, offer_id, result_hash, actual_processing_hours, actual_cost

### API Gateway Routing
Requests to `/v1/ffmpeg/*` are proxied to `http://localhost:8230/*` by the API Gateway.

## Configuration

### Environment Variables (`/etc/aitbc/ffmpeg.env`)
```bash
FFMPEG_PORT=8230
FFMPEG_GPU_DEVICE=0
FFMPEG_HW_ACCEL=cuda
```

### Systemd Service (`/etc/systemd/system/aitbc-ffmpeg.service`)
```ini
[Unit]
Description=AITBC FFmpeg Video Processing Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aitbc
EnvironmentFile=/etc/aitbc/ffmpeg.env
ExecStart=/opt/aitbc/venv/bin/python /opt/aitbc/apps/ffmpeg-service/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Results

- ✅ GPU-accelerated video processing (NVENC/NVDEC)
- ✅ FastAPI service at port 8230
- ✅ Health and capabilities endpoints
- ✅ Video processing with format, codec, resolution, bitrate options
- ✅ Metered pricing based on processing time
- ✅ On-chain proof of work via result hash
- ✅ Routed through API Gateway at `/v1/ffmpeg/*`
- ✅ Systemd service configuration

---

*Last Updated: 2026-06-05*
