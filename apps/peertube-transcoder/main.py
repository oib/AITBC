"""
AITBC PeerTube Transcoding Service
Wraps PeerTube runner for VOD transcoding tasks.
Port: 8220
"""

import hashlib
import json
import os

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel


class TranscodeRequest(BaseModel):
    video_url: str
    target_resolution: str = "1080p"
    target_codec: str = "h264"
    audio_codec: str = "aac"
    output_format: str = "mp4"


app = FastAPI(title="AITBC PeerTube Transcoding Service", version="1.0.0")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "peertube-transcoder"}


@app.post("/transcode")
async def transcode_video(req: TranscodeRequest):
    """Run PeerTube runner transcoding task.
    Returns transcoded video URL, duration, and result_hash for proof of work."""
    # For now, this is a stub — actual implementation would:
    # 1. Call peertube-runner to register job with PeerTube instance
    # 2. Monitor transcoding progress
    # 3. Return transcoded video URL, duration, file size
    # 4. Return result_hash of transcoding metadata

    # Stub response for testing
    result = {
        "transcoded_url": f"{req.video_url}.transcoded.{req.output_format}",
        "duration_seconds": 300.5,
        "file_size_mb": 125.3,
        "resolution": req.target_resolution,
        "codec": req.target_codec,
        "elapsed_seconds": 45.2,
    }
    result_hash = hashlib.sha256(json.dumps({
        'video_url': req.video_url,
        'transcoded_url': result['transcoded_url'],
        'duration': result['duration_seconds'],
    }, sort_keys=True).encode()).hexdigest()

    return {
        **result,
        "result_hash": result_hash,
        "video_url": req.video_url,
    }


if __name__ == "__main__":
    port = int(os.getenv("TRANSCODER_PORT", "8220"))
    uvicorn.run(app, host="0.0.0.0", port=port)
